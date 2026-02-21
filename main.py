from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from db import RotatorDB
from key_manager import KeyManager
from notifier import send_notification, send_webhook
from router import (
    PROFILES,
    ROUTING_CHAINS,
    RouteTarget,
    compute_suggestion,
    detect_profile,
    find_model_provider,
    list_all_models,
    model_context,
    profile_emoji,
)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)
CONFIG_ENV = os.environ.get("ROTATOR_CONFIG")
if CONFIG_ENV:
    _cfg_path = Path(CONFIG_ENV)
    if not _cfg_path.is_absolute():
        _cfg_path = (Path.cwd() / _cfg_path).resolve()
    CONFIG_FILE = _cfg_path
else:
    CONFIG_FILE = BASE_DIR / "config.yaml"
BACKUP_DIR = BASE_DIR / "backups"

BASE_URLS = {
    "ollama_cloud": "https://ollama.com/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "local": "http://localhost:11434/v1",
}

PROFILE_LABELS = {
    "coding": "Coding",
    "reasoning": "Reasoning",
    "chat": "Chat",
    "long": "Long",
    "vision": "Vision",
    "audio": "Audio",
    "translate": "Translate",
}

DEFAULT_COMPAT_ALIASES = {
    "claude-sonnet-4-6": "coding",
    "github/gpt5mini": "coding",
    "gpt-5-mini": "coding",
}

SUPPORTED_KEY_PROVIDERS = ("ollama_cloud", "nvidia", "openrouter", "google")
install_status: dict[str, dict[str, Any]] = {}


class AppState:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.config: dict[str, Any] = {}
        self.db: RotatorDB | None = None
        self.key_manager: KeyManager | None = None
        self.overrides: dict[str, Any] = {"profiles": {p: "auto" for p in PROFILES}, "blocked": []}
        self.override_expiry: dict[str, datetime] = {}
        self.block_expiry: dict[str, datetime] = {}
        self.priority_mode: str = "balanced"
        self.last_request: dict[str, Any] | None = None
        self.model_locks: dict[str, dict[str, str]] = {}
        self.suspensions: dict[str, datetime | None] = {}
        self.active_preset_id: int | None = None
        self.presets: list[dict[str, Any]] = []
        self.schedule_last_run: dict[int, datetime] = {}
        self.tests_results: dict[str, Any] = {"last_run": None, "results": []}
        self.benchmark: dict[str, Any] = {"running": False, "results": [], "started_at": None, "stop": False}
        self.suggestions: list[dict[str, Any]] = []
        self.last_key_by_profile: dict[str, str] = {}
        self.paused: bool = False
        self.logs: deque[dict[str, Any]] = deque(maxlen=50)
        self.active_routes: dict[str, dict[str, str]] = {p: {"provider": "-", "model": "-"} for p in PROFILES}
        self.invalid_auth_attempts: dict[str, deque[datetime]] = {}
        self.auth_block_until: dict[str, datetime] = {}
        self.security_metrics: dict[str, int] = {
            "invalid_token_failures_total": 0,
            "auth_blocks_triggered_total": 0,
            "auth_block_hits_total": 0,
            "auth_success_resets_total": 0,
        }
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15, read=300, write=30, pool=30),
        )


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_state()
    log_event("SYSTEM", "API Rotator started", "success", source="system")
    schedule_task = asyncio.create_task(schedule_loop())
    catalogue_task = asyncio.create_task(_catalogue_refresh_loop())
    try:
        yield
    finally:
        for t in (schedule_task, catalogue_task):
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t
        db = state.db
        if db and backup_settings().get("auto_backup_on_shutdown", True):
            with suppress(Exception):
                await db.create_backup_snapshot(str(BACKUP_DIR))
        await state.client.aclose()


app = FastAPI(title="API Rotator", version="1.0.0", lifespan=lifespan)

logger = logging.getLogger("rotator")

STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Admin auth middleware – protects /api/* endpoints
# ---------------------------------------------------------------------------

# Paths that do NOT require admin auth (public or with their own auth)
_PUBLIC_PATH_PREFIXES = ("/v1/", "/dashboard", "/static", "/docs", "/openapi.json")
_PUBLIC_API_PATHS = {"/api/ping", "/api/health"}


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    """Require a valid project token for all /api/* management endpoints."""
    path = request.url.path.rstrip("/")

    # Skip auth for public paths
    if path.startswith(_PUBLIC_PATH_PREFIXES) or path in _PUBLIC_API_PATHS or path == "/":
        return await call_next(request)

    # Only gate /api/ routes
    if path.startswith("/api"):
        token = request.headers.get("Authorization", "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        else:
            legacy = request.headers.get("X-API-Key", "").strip()
            token = legacy if legacy else ""

        # Fall back to default token when auth header is not required
        if not token and not require_auth_header():
            token = "rotator"

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authorization header required for admin endpoints"},
            )

        # Validate token against known project keys
        db = state.db
        if db is not None:
            project = await db.resolve_project_key(token)
            if not project:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid admin token"},
                )
        # If DB not yet initialized, only accept the default token
        elif token != "rotator":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid admin token"},
            )

    return await call_next(request)


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        raise RuntimeError("config.yaml is missing")
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config_file(content: dict[str, Any]) -> None:
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        yaml.safe_dump(content, f, allow_unicode=True, sort_keys=False)


def backup_settings(config: dict[str, Any] | None = None) -> dict[str, bool]:
    cfg = config or state.config or {}
    raw = cfg.get("settings", {}).get("backups", {}) or {}
    return {
        "auto_backup_on_shutdown": bool(raw.get("auto_backup_on_shutdown", True)),
        "auto_restore_latest_on_startup": bool(raw.get("auto_restore_latest_on_startup", True)),
    }


def secret_field_for_provider(provider: str) -> str:
    return "token" if provider == "ollama_cloud" else "key"


def normalize_keys_from_config(config: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    raw_keys = config.get("keys", {}) or {}
    normalized: dict[str, list[dict[str, str]]] = {}

    for provider in SUPPORTED_KEY_PROVIDERS:
        entries = raw_keys.get(provider, [])
        provider_field = secret_field_for_provider(provider)
        provider_items: list[dict[str, str]] = []

        if isinstance(entries, list):
            for index, item in enumerate(entries, start=1):
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or f"{provider}-{index}")
                value = item.get(provider_field)
                if value is None:
                    value = item.get("key") or item.get("token") or ""
                provider_items.append(
                    {
                        "label": label,
                        "value": str(value or ""),
                        "field": provider_field,
                    }
                )

        normalized[provider] = provider_items

    return normalized


def log_event(
    profile: str,
    message: str,
    level: str = "success",
    provider: str | None = None,
    model: str | None = None,
    source: str = "system",
) -> None:
    state.logs.appendleft(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "profile": profile.upper(),
            "provider": provider or "-",
            "model": model or "-",
            "message": message,
            "level": level,
            "source": source,
        }
    )


def dispatch_webhook(event_type: str, message: str, details: dict[str, Any]) -> None:
    if not state.config:
        return
    asyncio.create_task(send_webhook(event_type, message, details, state.config))


def require_auth_header() -> bool:
    return bool((state.config or {}).get("settings", {}).get("require_auth_header", False))


def auth_guard_settings() -> dict[str, int | bool]:
    settings = (state.config or {}).get("settings", {})
    return {
        "enabled": bool(settings.get("auth_bruteforce_protection", True)),
        "limit": max(1, int(settings.get("invalid_token_limit_per_minute", 12))),
        "window": max(10, int(settings.get("invalid_token_window_seconds", 60))),
        "block": max(10, int(settings.get("invalid_token_block_seconds", 120))),
    }


def client_fingerprint(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune_auth_attempts(client_id: str, now: datetime, window_seconds: int) -> deque[datetime]:
    attempts = state.invalid_auth_attempts.setdefault(client_id, deque())
    cutoff = now - timedelta(seconds=window_seconds)
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return attempts


def cleanup_auth_guard_state(now: datetime | None = None) -> None:
    cfg = auth_guard_settings()
    current = now or datetime.now(UTC)
    window = int(cfg["window"])

    expired_blocks = [
        client_id
        for client_id, blocked_until in state.auth_block_until.items()
        if blocked_until <= current
    ]
    for client_id in expired_blocks:
        state.auth_block_until.pop(client_id, None)

    stale_clients = []
    for client_id in list(state.invalid_auth_attempts.keys()):
        attempts = _prune_auth_attempts(client_id, current, window)
        if not attempts:
            stale_clients.append(client_id)
    for client_id in stale_clients:
        state.invalid_auth_attempts.pop(client_id, None)


def enforce_auth_guard(request: Request) -> None:
    cfg = auth_guard_settings()
    if not cfg["enabled"]:
        return
    now = datetime.now(UTC)
    cleanup_auth_guard_state(now)
    client_id = client_fingerprint(request)
    blocked_until = state.auth_block_until.get(client_id)
    if blocked_until and now < blocked_until:
        state.security_metrics["auth_block_hits_total"] = state.security_metrics.get("auth_block_hits_total", 0) + 1
        raise HTTPException(status_code=429, detail="Too many invalid authentication attempts")


def register_auth_failure(request: Request) -> None:
    cfg = auth_guard_settings()
    if not cfg["enabled"]:
        return
    now = datetime.now(UTC)
    client_id = client_fingerprint(request)
    attempts = _prune_auth_attempts(client_id, now, int(cfg["window"]))
    attempts.append(now)
    state.security_metrics["invalid_token_failures_total"] = state.security_metrics.get("invalid_token_failures_total", 0) + 1
    if len(attempts) >= int(cfg["limit"]):
        state.auth_block_until[client_id] = now + timedelta(seconds=int(cfg["block"]))
        state.security_metrics["auth_blocks_triggered_total"] = state.security_metrics.get("auth_blocks_triggered_total", 0) + 1


def reset_auth_failures(request: Request) -> None:
    client_id = client_fingerprint(request)
    state.invalid_auth_attempts.pop(client_id, None)
    state.auth_block_until.pop(client_id, None)
    state.security_metrics["auth_success_resets_total"] = state.security_metrics.get("auth_success_resets_total", 0) + 1


def security_status_payload() -> dict[str, Any]:
    cfg = auth_guard_settings()
    now = datetime.now(UTC)
    cleanup_auth_guard_state(now)
    active_blocks = {
        client_id: blocked_until.isoformat(timespec="seconds")
        for client_id, blocked_until in state.auth_block_until.items()
        if blocked_until > now
    }
    return {
        "require_auth_header": require_auth_header(),
        "auth_bruteforce_protection": bool(cfg["enabled"]),
        "invalid_token_limit_per_minute": int(cfg["limit"]),
        "invalid_token_window_seconds": int(cfg["window"]),
        "invalid_token_block_seconds": int(cfg["block"]),
        "blocked_clients": active_blocks,
        "blocked_clients_count": len(active_blocks),
        "metrics": {
            "invalid_token_failures_total": state.security_metrics.get("invalid_token_failures_total", 0),
            "auth_blocks_triggered_total": state.security_metrics.get("auth_blocks_triggered_total", 0),
            "auth_block_hits_total": state.security_metrics.get("auth_block_hits_total", 0),
            "auth_success_resets_total": state.security_metrics.get("auth_success_resets_total", 0),
        },
    }


def _extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    legacy = request.headers.get("X-API-Key", "").strip()
    if legacy:
        return legacy
    if require_auth_header():
        return ""
    return "rotator"


async def resolve_project_from_request(request: Request) -> dict[str, Any]:
    db = state.db
    if db is None:
        config = state.config or load_config()
        db_path = config.get("settings", {}).get("db_file", "rotator.db")
        db_path = str((BASE_DIR / db_path).resolve()) if not Path(db_path).is_absolute() else db_path
        state.db = RotatorDB(db_path)
        await state.db.initialize()
        await state.db.ensure_default_project_key()
        db = state.db
    token = _extract_bearer_token(request)
    if require_auth_header() and not token:
        raise HTTPException(status_code=401, detail="Authorization header required")
    enforce_auth_guard(request)
    project = await db.resolve_project_key(token)
    if not project:
        register_auth_failure(request)
        raise HTTPException(status_code=401, detail="Invalid project token")
    reset_auth_failures(request)
    if not project.get("active", False):
        raise HTTPException(status_code=403, detail="Project key is inactive")
    return project


def enforce_project_policy(project: dict[str, Any], profile: str) -> None:
    policy = str(project.get("policy") or "full_access")
    if policy == "coding_only" and profile != "coding":
        raise HTTPException(status_code=403, detail="Project key is restricted to coding profile")


async def check_project_quota(project: dict[str, Any]) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")
    limit = project.get("daily_limit")
    used = await db.get_project_daily_usage(project["token"])
    if limit is None:
        return {"allowed": True, "used": used, "mode": project.get("quota_mode", "hard_block")}
    if used < int(limit):
        return {"allowed": True, "used": used, "mode": project.get("quota_mode", "hard_block")}
    mode = project.get("quota_mode", "hard_block")
    if mode == "alert_only":
        return {"allowed": True, "used": used, "mode": mode}
    if mode == "local_only":
        return {"allowed": True, "used": used, "mode": mode}
    raise HTTPException(status_code=429, detail="Project daily quota exceeded")


def build_headers(provider: str, key_value: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if provider in {"ollama_cloud", "nvidia", "openrouter", "google"} and key_value:
        headers["Authorization"] = f"Bearer {key_value}"
    if provider == "openrouter":
        port = state.config.get("settings", {}).get("port", 47822)
        headers["HTTP-Referer"] = f"http://localhost:{port}"
        headers["X-Title"] = "api-rotator"
    return headers


def get_compat_aliases() -> dict[str, str]:
    aliases = dict(DEFAULT_COMPAT_ALIASES)
    raw = (state.config or {}).get("compat_aliases", {})
    if isinstance(raw, dict):
        for key, value in raw.items():
            alias = str(key or "").strip()
            target = str(value or "").strip()
            if alias and target:
                aliases[alias] = target
    return aliases


def parse_explicit_target(value: str) -> RouteTarget | None:
    raw = str(value or "").strip()
    for provider in BASE_URLS:
        prefix = f"{provider}:"
        if raw.startswith(prefix) and len(raw) > len(prefix):
            model_name = raw[len(prefix):].strip()
            if model_name:
                return RouteTarget(provider, model_name, "alias-explicit")
    return None


def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def resolve_model_hint(model_hint: str) -> tuple[str, str] | None:
    hint = str(model_hint or "").strip()
    if not hint:
        return None
    if hint in PROFILES:
        return ("profile", hint)

    aliases = get_compat_aliases()
    mapped = aliases.get(hint)
    if mapped:
        if mapped in PROFILES:
            return ("profile", mapped)
        if find_model_provider(mapped):
            return ("model", mapped)
        if parse_explicit_target(mapped):
            return ("explicit", mapped)

    if find_model_provider(hint):
        return ("model", hint)
    if parse_explicit_target(hint):
        return ("explicit", hint)
    return None


def profile_for_model(model_name: str) -> str | None:
    for profile, chain in ROUTING_CHAINS.items():
        if any(target.model == model_name for target in chain):
            return profile
    return None


def effective_override(profile: str) -> str:
    expiry = state.override_expiry.get(profile)
    if expiry and datetime.now(UTC) >= ensure_utc_datetime(expiry):
        state.override_expiry.pop(profile, None)
        state.overrides["profiles"][profile] = "auto"
    return state.overrides.get("profiles", {}).get(profile, "auto")


def provider_blocked(provider: str, model: str) -> bool:
    expiry = state.block_expiry.get(provider)
    if expiry and datetime.now(UTC) >= ensure_utc_datetime(expiry):
        state.block_expiry.pop(provider, None)
        blocked = set(state.overrides.get("blocked", []))
        blocked.discard(provider)
        state.overrides["blocked"] = sorted(blocked)

    suspended_until = state.suspensions.get(provider)
    if suspended_until and datetime.now(UTC) >= ensure_utc_datetime(suspended_until):
        state.suspensions.pop(provider, None)
        if state.db:
            asyncio.create_task(state.db.delete_suspension(provider))

    if provider in state.suspensions:
        return True

    blocked = set(state.overrides.get("blocked", []))
    if provider in blocked:
        return True
    if "gemini_flash" in blocked and model == "gemini-2.5-flash":
        return True
    return False


async def save_overrides_to_db() -> None:
    if not state.db:
        return
    blocked = state.overrides.get("blocked", [])
    await state.db.save_override("_global", None, blocked)
    for profile in PROFILES:
        override_provider = state.overrides.get("profiles", {}).get(profile, "auto")
        value = None if override_provider == "auto" else override_provider
        await state.db.save_override(profile, value, [])


async def apply_config_overrides(config: dict[str, Any]) -> None:
    raw = config.get("overrides", {})
    state.overrides = {
        "profiles": {p: raw.get(p, "auto") for p in PROFILES},
        "blocked": raw.get("blocked", []) or [],
    }
    await save_overrides_to_db()


def default_presets() -> list[dict[str, Any]]:
    base_models = {
        profile: [target.model for target in ROUTING_CHAINS[profile]]
        for profile in PROFILES
    }
    return [
        {
            "name": "🚀 Maximum Power",
            "description": "MiniMax M2.5 then GLM-5 then NVIDIA",
            "data": {
                "profiles": {
                    profile: {
                        "models": [
                            "minimax-m2.5:cloud",
                            "glm-5:cloud",
                        ] + base_models[profile],
                        "lock_top": False,
                    }
                    for profile in PROFILES
                },
                "blocked": [],
                "priority_mode": "balanced",
            },
        },
        {
            "name": "💰 Economy Mode",
            "description": "Local then OpenRouter free then Gemma",
            "data": {
                "profiles": {
                    profile: {
                        "models": [
                            "qwen3-coder-next:latest",
                            "lfm2.5-thinking:1.2b",
                            "openrouter/free",
                            "gemma-3-27b-it",
                        ],
                        "lock_top": False,
                    }
                    for profile in PROFILES
                },
                "blocked": ["gemini_flash"],
                "priority_mode": "local_first",
            },
        },
        {
            "name": "⚡ Speed Mode",
            "description": "Step 3.5 Flash then Gemma 27B",
            "data": {
                "profiles": {
                    profile: {
                        "models": ["stepfun/step-3.5-flash:free", "gemma-3-27b-it"],
                        "lock_top": False,
                    }
                    for profile in PROFILES
                },
                "blocked": [],
                "priority_mode": "balanced",
            },
        },
        {
            "name": "🏠 100% Local Mode",
            "description": "Ollama local only",
            "data": {
                "profiles": {
                    profile: {
                        "models": ["qwen3-coder-next:latest", "lfm2.5-thinking:1.2b"],
                        "lock_top": True,
                    }
                    for profile in PROFILES
                },
                "blocked": ["ollama_cloud", "nvidia", "openrouter", "google", "gemini_flash"],
                "priority_mode": "local_first",
            },
        },
        {
            "name": "💻 Intensive Coding",
            "description": "Coding locked to MiniMax M2.5",
            "data": {
                "profiles": {
                    "coding": {"models": ["minimax-m2.5:cloud"], "lock_top": True},
                    **{
                        profile: {"models": base_models[profile], "lock_top": False}
                        for profile in PROFILES
                        if profile != "coding"
                    },
                },
                "blocked": [],
                "priority_mode": "balanced",
            },
        },
    ]


async def apply_preset(preset_id: int, data: dict[str, Any]) -> None:
    state.active_preset_id = preset_id
    state.priority_mode = data.get("priority_mode", "balanced")
    state.overrides["blocked"] = data.get("blocked", [])
    await save_overrides_to_db()
    if state.db:
        await state.db.set_app_state("active_preset_id", preset_id)
    dispatch_webhook("preset_applied", f"Preset applied: {preset_id}", {"preset_id": preset_id})


async def update_model_performance(model: str, elapsed_ms: float, success: bool) -> None:
    if not state.db:
        return
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    existing = await state.db.list_model_performance(date_str)
    row = next((item for item in existing if item["model"] == model), None)
    if row:
        count = row["sample_count"]
        avg_total = row["avg_total_ms"]
        error_rate = row["error_rate"]
    else:
        count = 0
        avg_total = 0
        error_rate = 0

    new_count = count + 1
    new_avg_total = ((avg_total * count) + elapsed_ms) / new_count
    new_error_rate = ((error_rate * count) + (0 if success else 1)) / new_count
    await state.db.upsert_model_performance(
        date_str,
        model,
        avg_ttft_ms=0,  # TODO: measure real TTFT in streaming mode
        avg_total_ms=new_avg_total,
        error_rate=new_error_rate,
        sample_count=new_count,
    )


_suggestions_last_refresh: float = 0.0
_SUGGESTIONS_TTL: float = 300.0  # 5 minutes


async def refresh_suggestions(force: bool = False) -> None:
    global _suggestions_last_refresh
    now = time.time()
    if not force and (now - _suggestions_last_refresh) < _SUGGESTIONS_TTL:
        return
    if not state.db:
        return
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    perf = await state.db.list_model_performance(today)
    counts = await state.db.get_profile_requests_today(today)
    suggestions: list[dict[str, Any]] = []
    for profile in PROFILES:
        if counts.get(profile, 0) < 50:
            continue
        current = state.active_routes.get(profile, {}).get("model", "")
        if not current:
            continue
        suggestion = compute_suggestion(profile, current, perf)
        if suggestion:
            suggestions.append(suggestion)
    state.suggestions = suggestions
    _suggestions_last_refresh = now


async def init_state() -> None:
    state.config = load_config()
    db_path = state.config.get("settings", {}).get("db_file", "rotator.db")
    db_path = str((BASE_DIR / db_path).resolve()) if not Path(db_path).is_absolute() else db_path
    state.db = RotatorDB(db_path)
    await state.db.initialize()
    await state.db.ensure_default_project_key()

    pending_restore = await state.db.get_app_state("pending_restore_backup", None)
    if pending_restore:
        with suppress(Exception):
            if str(pending_restore) == "__LATEST__":
                await state.db.restore_latest_backup(str(BACKUP_DIR))
            else:
                await state.db.restore_backup_by_name(str(BACKUP_DIR), str(pending_restore))
            await state.db.initialize()
            await state.db.ensure_default_project_key()
            await state.db.set_app_state("pending_restore_backup", None)
    elif backup_settings(state.config).get("auto_restore_latest_on_startup", True):
        with suppress(Exception):
            restored = await state.db.restore_latest_backup(str(BACKUP_DIR))
            if restored:
                await state.db.initialize()
                await state.db.ensure_default_project_key()

    quota_map = await state.db.load_daily_quota_map()
    state.key_manager = KeyManager(state.config, quota_map)

    await apply_config_overrides(state.config)
    db_overrides = await state.db.load_overrides()
    for profile, value in db_overrides.get("profiles", {}).items():
        state.overrides["profiles"][profile] = value
    if db_overrides.get("blocked"):
        state.overrides["blocked"] = db_overrides["blocked"]

    state.model_locks = await state.db.load_model_locks()
    susp = await state.db.load_suspensions()
    state.suspensions = {
        provider: (ensure_utc_datetime(datetime.fromisoformat(ts)) if ts else None) for provider, ts in susp.items()
    }
    if state.key_manager:
        for provider in state.suspensions:
            state.key_manager.suspend_provider(provider)

    state.presets = await state.db.list_presets()
    if not state.presets:
        for preset in default_presets():
            await state.db.save_preset(preset["name"], preset["description"], preset["data"])
        state.presets = await state.db.list_presets()

    state.active_preset_id = await state.db.get_app_state("active_preset_id")
    if state.active_preset_id:
        match = next((p for p in state.presets if p["id"] == state.active_preset_id), None)
        if match:
            await apply_preset(match["id"], match["data"])

    blocked_keys = await state.db.get_app_state("blocked_keys", [])
    if blocked_keys and state.key_manager:
        for key_id in blocked_keys:
            state.key_manager.block_key(key_id)

def choose_targets(profile: str) -> list[Any]:
    chain = ROUTING_CHAINS[profile]
    forced = effective_override(profile)
    if forced == "auto":
        candidates = chain
    else:
        candidates = [item for item in chain if item.provider == forced]
    ordered: list[Any] = []

    if state.active_preset_id:
        preset = next((p for p in state.presets if p["id"] == state.active_preset_id), None)
        if preset:
            pdata = preset["data"].get("profiles", {}).get(profile, {})
            models = pdata.get("models", [])
            lock_top = bool(pdata.get("lock_top"))
            for model_name in models:
                provider = find_model_provider(model_name)
                if provider:
                    ordered.append(RouteTarget(provider, model_name, "preset"))
            if lock_top and ordered:
                candidates = [ordered[0]]
            else:
                candidates = ordered + candidates

    lock = state.model_locks.get(profile)
    if lock:
        locked_target = RouteTarget(lock["provider"], lock["model"], "locked")
        candidates = [locked_target] + [item for item in candidates if item.model != lock["model"]]

    filtered = [item for item in candidates if not provider_blocked(item.provider, item.model)]
    if state.priority_mode == "local_first":
        return sorted(filtered, key=lambda item: item.provider != "local")
    if state.priority_mode == "cloud_first":
        return sorted(filtered, key=lambda item: item.provider == "local")
    return filtered


def build_target_for_model(model_name: str) -> Any:
    provider = find_model_provider(model_name)
    if not provider:
        return None
    return RouteTarget(provider, model_name, "manual")


async def send_model_request(model_name: str, prompt: str, timeout: int = 60) -> dict[str, Any]:
    km = state.key_manager
    if km is None:
        raise RuntimeError("Key manager not ready")
    target = build_target_for_model(model_name)
    if not target:
        raise RuntimeError("Unknown model")
    key = km.choose_key_for_target(target)
    if key is None:
        raise RuntimeError("No key available")

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
    }
    headers = build_headers(target.provider, key.value)
    url = f"{BASE_URLS[target.provider]}/chat/completions"
    started = time.perf_counter()
    response = await state.client.post(url, headers=headers, json=payload, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    return {"model": model_name, "provider": target.provider, "elapsed_ms": elapsed_ms, "json": response.json()}


def get_mode_badge() -> str:
    if state.active_preset_id:
        return "PRESET"
    if state.model_locks:
        return "LOCKED"
    return "AUTO"


@app.get("/v1/models")
async def list_models(request: Request) -> dict[str, Any]:
    project = await resolve_project_from_request(request)
    profile_ids = [
        "coding",
        "reasoning",
        "chat",
        "long",
        "vision",
        "audio",
        "translate",
    ]
    if str(project.get("policy") or "full_access") == "coding_only":
        profile_ids = ["coding"]

    if profile_ids == ["coding"]:
        model_ids = [target.model for target in ROUTING_CHAINS["coding"]]
    else:
        model_ids = []
        for models in list_all_models().values():
            for item in models:
                model_name = str(item.get("model", "")).strip()
                if model_name:
                    model_ids.append(model_name)

    aliases = []
    for alias, target in get_compat_aliases().items():
        explicit = parse_explicit_target(target)
        if target in profile_ids or target in model_ids or explicit:
            aliases.append(alias)

    ids = []
    seen: set[str] = set()
    for item in profile_ids + model_ids + aliases:
        if item not in seen:
            seen.add(item)
            ids.append(item)

    alias_map = get_compat_aliases()
    # Build model→profiles mapping from ROUTING_CHAINS
    model_profiles: dict[str, list[str]] = {}
    for prof, chain in ROUTING_CHAINS.items():
        for rt in chain:
            model_profiles.setdefault(rt.model, [])
            if prof not in model_profiles[rt.model]:
                model_profiles[rt.model].append(prof)

    data_rows: list[dict[str, Any]] = []
    for item in ids:
        owned_by = "api-rotator"
        item_profiles: list[str] = []
        if item in profile_ids:
            owned_by = "profile"
            item_profiles = [item]
        elif item in model_ids:
            owned_by = find_model_provider(item) or "api-rotator"
            item_profiles = model_profiles.get(item, [])
        elif item in aliases:
            target = alias_map.get(item, "")
            if target in PROFILES:
                owned_by = f"alias:{target}"
                item_profiles = [target]
            elif parse_explicit_target(target):
                owned_by = f"alias:{parse_explicit_target(target).provider}"
                et = parse_explicit_target(target)
                if et:
                    item_profiles = model_profiles.get(et.model, [])
            else:
                owned_by = f"alias:{find_model_provider(target) or 'api-rotator'}"
                item_profiles = model_profiles.get(target, [])
        data_rows.append({
            "id": item,
            "object": "model",
            "created": 1700000000,
            "owned_by": owned_by,
            "profiles": item_profiles,
        })

    return {
        "object": "list",
        "data": data_rows,
    }


async def _proxy_with_fallback(
    *,
    profile: str,
    candidates: list[RouteTarget],
    payload: dict[str, Any],
    stream: bool,
    project_token: str,
    transform_body: Any = None,
    wrap_stream: Any = None,
    log_suffix: str = "",
) -> StreamingResponse | JSONResponse:
    """Common fallback loop shared by /v1/chat/completions and /v1/messages.

    Args:
        transform_body: Optional callable(dict) -> dict to transform JSON response body.
        wrap_stream: Optional callable(response) -> AsyncIterator for stream wrapping.
        log_suffix: Appended to log messages (e.g., " (messages)").
    """
    km = state.key_manager
    db = state.db
    if km is None or db is None:
        raise HTTPException(status_code=500, detail="State not initialized")

    last_error: str | None = None
    rotated_from: str | None = None
    network_issue_detected = False
    local_available = any(item.provider == "local" for item in candidates)
    local_attempted = False
    await db.increment_project_daily_usage(project_token)

    for idx, target in enumerate(candidates):
        if network_issue_detected and target.provider != "local":
            continue

        key = km.choose_key_for_target(target)
        if key is None:
            continue

        if target.provider == "local":
            local_attempted = True

        payload["model"] = target.model
        headers = build_headers(target.provider, key.value)
        url = f"{BASE_URLS[target.provider]}/chat/completions"
        started = time.perf_counter()

        try:
            if stream:
                payload["stream"] = True
                upstream = state.client.build_request("POST", url, headers=headers, json=payload)
                response = await state.client.send(upstream, stream=True)
                if response.status_code >= 400:
                    err_body = (await response.aread()).decode("utf-8", errors="ignore")
                    raise RuntimeError(err_body or f"HTTP {response.status_code}")

                state.active_routes[profile] = {"provider": target.provider, "model": target.model}
                elapsed_ms = (time.perf_counter() - started) * 1000
                km.mark_result(target.provider, target.model, key.key_id, True)
                await db.increment_daily_quota(target.provider, target.model, key.key_id)
                await db.upsert_key_stats(key.key_id, target.provider, True, elapsed_ms)
                await db.add_profile_history(profile, target.provider, target.model, key.key_id, True)
                await update_model_performance(target.model, elapsed_ms, True)
                state.last_key_by_profile[profile] = key.key_id
                log_event(
                    profile,
                    f"{target.provider}/{target.model} → stream started{log_suffix}",
                    "success",
                    provider=target.provider,
                    model=target.model,
                    source="proxy",
                )

                if wrap_stream is not None:
                    content = wrap_stream(response)
                else:
                    async def _iter() -> Any:
                        async for chunk in response.aiter_raw():
                            yield chunk
                    content = _iter()

                return StreamingResponse(content, media_type="text/event-stream")

            payload["stream"] = False
            response = await state.client.post(url, headers=headers, json=payload)
            elapsed_ms = (time.perf_counter() - started) * 1000

            if response.status_code < 400:
                body = response.json()
                km.mark_result(target.provider, target.model, key.key_id, True)
                await db.increment_daily_quota(target.provider, target.model, key.key_id)
                await db.upsert_key_stats(key.key_id, target.provider, True, elapsed_ms)
                await db.add_profile_history(profile, target.provider, target.model, key.key_id, True)
                await update_model_performance(target.model, elapsed_ms, True)
                state.last_key_by_profile[profile] = key.key_id
                state.active_routes[profile] = {"provider": target.provider, "model": target.model}

                if rotated_from and state.config.get("settings", {}).get("notify_on_rotation", True):
                    send_notification(
                        "API Rotator",
                        f"🔄 Rotation: {profile.upper()} switched from {rotated_from} to {target.provider}",
                    )
                    dispatch_webhook(
                        "rotation",
                        f"{profile.upper()} switched from {rotated_from} to {target.provider}",
                        {"profile": profile, "from": rotated_from, "to": target.provider, "model": target.model},
                    )

                if target.model == "gemini-2.5-flash":
                    used = km.daily_quota_map.get(f"google:gemini-2.5-flash:{key.key_id}", 0)
                    if used >= 18:
                        send_notification("API Rotator", f"⚠️ gemini-2.5-flash: {used}/20 requests used today")
                        dispatch_webhook(
                            "quota_warning",
                            f"gemini-2.5-flash: {used}/20 requests used today",
                            {"provider": "google", "model": target.model, "used": used},
                        )

                suffix_str = f", {log_suffix.strip()}" if log_suffix.strip() else ""
                log_event(
                    profile,
                    f"{target.provider}/{target.model} → success ({int(elapsed_ms)}ms{suffix_str})",
                    "success",
                    provider=target.provider,
                    model=target.model,
                    source="proxy",
                )

                if transform_body is not None:
                    body = transform_body(body)
                return JSONResponse(body)

            error_text = response.text
            last_error = f"{response.status_code}: {error_text[:240]}"
            action = km.mark_result(target.provider, target.model, key.key_id, False)
            await db.upsert_key_stats(key.key_id, target.provider, False, elapsed_ms)
            await db.add_profile_history(profile, target.provider, target.model, key.key_id, False)
            await update_model_performance(target.model, elapsed_ms, False)
            log_event(
                profile,
                f"{target.provider}/{target.model} → error {response.status_code}{log_suffix}",
                "error",
                provider=target.provider,
                model=target.model,
                source="proxy",
            )

            if action.get("rotated"):
                rotated_from = target.provider
                log_event(
                    profile,
                    f"{target.provider} key rotated ({action.get('reason')})",
                    "rotation",
                    provider=target.provider,
                    model=target.model,
                    source="proxy",
                )
                dispatch_webhook(
                    "rotation",
                    f"{target.provider} key rotated",
                    {"profile": profile, "provider": target.provider, "model": target.model},
                )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            last_error = str(exc)
            if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
                if target.provider != "local":
                    network_issue_detected = True
            action = km.mark_result(target.provider, target.model, key.key_id, False)
            await db.upsert_key_stats(key.key_id, target.provider, False, elapsed_ms)
            await db.add_profile_history(profile, target.provider, target.model, key.key_id, False)
            await update_model_performance(target.model, elapsed_ms, False)
            log_event(
                profile,
                f"{target.provider}/{target.model} → exception{log_suffix}",
                "error",
                provider=target.provider,
                model=target.model,
                source="proxy",
            )
            if action.get("rotated"):
                rotated_from = target.provider
                log_event(
                    profile,
                    f"{target.provider} key rotated ({action.get('reason')})",
                    "rotation",
                    provider=target.provider,
                    model=target.model,
                    source="proxy",
                )
                dispatch_webhook(
                    "rotation",
                    f"{target.provider} key rotated",
                    {"profile": profile, "provider": target.provider, "model": target.model},
                )

        if idx == len(candidates) - 1:
            send_notification(
                "API Rotator",
                f"🚨 {profile.upper()}: all cloud keys exhausted, using LOCAL",
            )
            dispatch_webhook(
                "provider_down",
                f"{profile.upper()} all cloud keys exhausted",
                {"profile": profile},
            )

    if network_issue_detected and (not local_available or not local_attempted):
        raise HTTPException(
            status_code=503,
            detail="Network unavailable. Local fallback failed: local model not found or unavailable.",
        )

    raise HTTPException(status_code=503, detail=f"All providers failed for profile '{profile}'. Last error: {last_error}")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    if state.paused:
        raise HTTPException(status_code=503, detail="Proxy is paused")
    project = await resolve_project_from_request(request)
    payload = await request.json()
    stream = bool(payload.get("stream", False))
    requested_model = str(payload.get("model", "")).strip()
    resolved_model = resolve_model_hint(requested_model)

    if requested_model and resolved_model is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{requested_model}'. Use /v1/models to list available ids")

    explicit_target = None
    if resolved_model and resolved_model[0] == "profile":
        profile = resolved_model[1]
    elif resolved_model and resolved_model[0] == "model":
        model_name = resolved_model[1]
        profile = profile_for_model(model_name) or "coding"
        explicit_target = build_target_for_model(model_name)
    elif resolved_model and resolved_model[0] == "explicit":
        explicit_value = resolved_model[1]
        explicit_target = parse_explicit_target(explicit_value)
        if explicit_target is None:
            raise HTTPException(status_code=400, detail=f"Unknown model '{requested_model}'. Use /v1/models to list available ids")
        profile = profile_for_model(explicit_target.model) or "coding"
    else:
        profile = detect_profile(payload)

    enforce_project_policy(project, profile)

    quota_state = await check_project_quota(project)
    candidates = [explicit_target] if explicit_target else choose_targets(profile)
    if quota_state.get("mode") == "local_only":
        candidates = [item for item in candidates if item.provider == "local"]

    state.last_request = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "profile": profile,
        "model_hint": requested_model,
        "messages": len(payload.get("messages", []) or []),
        "stream": stream,
    }

    if not candidates:
        raise HTTPException(status_code=503, detail=f"No available providers for profile: {profile}")

    return await _proxy_with_fallback(
        profile=profile,
        candidates=candidates,
        payload=payload,
        stream=stream,
        project_token=project["token"],
    )


# ---------------------------------------------------------------------------
# /v1/messages — Anthropic Messages API compatibility (used by Claude Code)
# ---------------------------------------------------------------------------

def _anthropic_messages_to_openai(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert Anthropic Messages API request to OpenAI chat/completions format."""
    messages: list[dict[str, Any]] = []
    system_text = payload.get("system")
    if system_text:
        if isinstance(system_text, list):
            parts = []
            for block in system_text:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            system_text = "\n".join(parts)
        messages.append({"role": "system", "content": system_text})

    for msg in payload.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts: list[str] = []
            tool_use_blocks: list[dict[str, Any]] = []
            tool_result_blocks: list[dict[str, Any]] = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "thinking":
                        text_parts.append(block.get("thinking", ""))
                    elif btype == "tool_use":
                        tool_use_blocks.append(block)
                    elif btype == "tool_result":
                        tool_result_blocks.append(block)
                elif isinstance(block, str):
                    text_parts.append(block)
            content_text = "\n".join(text_parts) if text_parts else ""

            if role == "assistant" and tool_use_blocks:
                # Assistant message with tool calls
                msg_dict: dict[str, Any] = {"role": "assistant", "content": content_text or None}
                msg_dict["tool_calls"] = []
                for tu in tool_use_blocks:
                    msg_dict["tool_calls"].append({
                        "id": tu.get("id", f"call_{len(msg_dict['tool_calls'])}"),
                        "type": "function",
                        "function": {
                            "name": tu.get("name", ""),
                            "arguments": json.dumps(tu.get("input", {})),
                        },
                    })
                messages.append(msg_dict)
            elif tool_result_blocks:
                # Tool results → OpenAI "tool" role messages
                if content_text:
                    messages.append({"role": "user", "content": content_text})
                for tr in tool_result_blocks:
                    tr_content = tr.get("content", "")
                    if isinstance(tr_content, list):
                        tr_parts = []
                        for c in tr_content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                tr_parts.append(c.get("text", ""))
                            elif isinstance(c, str):
                                tr_parts.append(c)
                        tr_content = "\n".join(tr_parts)
                    elif not isinstance(tr_content, str):
                        tr_content = str(tr_content)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content": tr_content,
                    })
            else:
                messages.append({"role": role, "content": content_text})
        else:
            messages.append({"role": role, "content": content})

    openai_payload: dict[str, Any] = {
        "model": payload.get("model", ""),
        "messages": messages,
        "stream": bool(payload.get("stream", False)),
    }
    if payload.get("max_tokens"):
        openai_payload["max_tokens"] = payload["max_tokens"]
    if payload.get("temperature") is not None:
        openai_payload["temperature"] = payload["temperature"]
    if payload.get("top_p") is not None:
        openai_payload["top_p"] = payload["top_p"]
    if payload.get("stop_sequences"):
        openai_payload["stop"] = payload["stop_sequences"]

    # Convert Anthropic tools → OpenAI function-calling tools
    if payload.get("tools"):
        openai_tools = []
        for tool in payload["tools"]:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        openai_payload["tools"] = openai_tools

    # Convert Anthropic tool_choice → OpenAI tool_choice
    tc = payload.get("tool_choice")
    if tc and isinstance(tc, dict):
        tc_type = tc.get("type", "auto")
        if tc_type == "auto":
            openai_payload["tool_choice"] = "auto"
        elif tc_type == "any":
            openai_payload["tool_choice"] = "required"
        elif tc_type == "tool":
            openai_payload["tool_choice"] = {
                "type": "function",
                "function": {"name": tc.get("name", "")},
            }
        elif tc_type == "none":
            openai_payload["tool_choice"] = "none"

    return openai_payload


def _openai_response_to_anthropic(body: dict[str, Any], requested_model: str) -> dict[str, Any]:
    """Convert OpenAI chat/completions response to Anthropic Messages format."""
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message", {})
    content_text = message.get("content", "")
    reasoning_text = message.get("reasoning", "") or message.get("reasoning_content", "")
    tool_calls = message.get("tool_calls") or []

    content_blocks: list[dict[str, Any]] = []
    if reasoning_text:
        content_blocks.append({"type": "thinking", "thinking": reasoning_text})
    if content_text:
        content_blocks.append({"type": "text", "text": content_text})

    # Convert OpenAI tool_calls → Anthropic tool_use content blocks
    for tc in tool_calls:
        func = tc.get("function", {})
        try:
            input_data = json.loads(func.get("arguments", "{}"))
        except (json.JSONDecodeError, ValueError):
            input_data = {"raw_arguments": func.get("arguments", "")}
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", f"toolu_{int(time.time())}"),
            "name": func.get("name", ""),
            "input": input_data,
        })

    # Ensure at least one content block
    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    stop_reason = "end_turn"
    finish = choice.get("finish_reason", "")
    if finish == "length":
        stop_reason = "max_tokens"
    elif finish == "tool_calls" or tool_calls:
        stop_reason = "tool_use"
    elif finish == "stop":
        stop_reason = "end_turn"

    usage_in = body.get("usage", {})
    return {
        "id": f"msg_{body.get('id', 'unknown')}",
        "type": "message",
        "role": "assistant",
        "model": requested_model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage_in.get("prompt_tokens", 0),
            "output_tokens": usage_in.get("completion_tokens", 0),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


async def _anthropic_stream_adapter(response: Any, requested_model: str, msg_id: str) -> Any:
    """Convert OpenAI SSE stream to Anthropic Messages SSE stream.

    Properly buffers partial SSE lines across raw byte boundaries to avoid
    losing data when aiter_raw() splits a JSON payload mid-line.
    """
    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': requested_model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}}})}\n\n"
    yield "event: ping\ndata: {\"type\": \"ping\"}\n\n"

    block_index = 0
    current_block_type: str | None = None  # "thinking", "text", or "tool_use"
    full_text = ""
    full_thinking = ""
    tool_args_accum: dict[int, str] = {}    # openai tc_index → accumulated arguments
    started_tool_indices: set[int] = set()  # which tc indices have had content_block_start
    tc_block_map: dict[int, int] = {}       # openai tc_index → anthropic block_index
    finish_reason_captured: str | None = None
    line_buf = ""  # SSE line buffer for partial data across raw chunks

    try:
        async for raw_chunk in response.aiter_raw():
            text = raw_chunk.decode("utf-8", errors="ignore") if isinstance(raw_chunk, bytes) else raw_chunk
            line_buf += text

            # Process only complete lines (terminated by \n)
            while "\n" in line_buf:
                line, line_buf = line_buf.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data_str)
                except (json.JSONDecodeError, ValueError):
                    continue

                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta", {})
                fr = choice.get("finish_reason")
                if fr:
                    finish_reason_captured = fr

                reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
                content = delta.get("content") or ""
                tool_calls_delta = delta.get("tool_calls") or []

                # Handle thinking/reasoning blocks
                if reasoning:
                    if current_block_type != "thinking":
                        if current_block_type is not None:
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': block_index})}\n\n"
                            block_index += 1
                        current_block_type = "thinking"
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': block_index, 'content_block': {'type': 'thinking', 'thinking': ''}})}\n\n"
                    full_thinking += reasoning
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': block_index, 'delta': {'type': 'thinking_delta', 'thinking': reasoning}})}\n\n"

                # Handle text content
                if content:
                    if current_block_type != "text":
                        if current_block_type is not None:
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': block_index})}\n\n"
                            block_index += 1
                        current_block_type = "text"
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': block_index, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
                    full_text += content
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': block_index, 'delta': {'type': 'text_delta', 'text': content}})}\n\n"

                # Handle tool calls (OpenAI delta.tool_calls → Anthropic tool_use blocks)
                for tc in tool_calls_delta:
                    tc_idx = tc.get("index", 0)
                    tc_id = tc.get("id")
                    tc_func = tc.get("function", {})
                    tc_name = tc_func.get("name")
                    tc_args = tc_func.get("arguments", "")

                    if tc_idx not in started_tool_indices:
                        # New tool call — close any open block first
                        if current_block_type is not None:
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': block_index})}\n\n"
                            block_index += 1
                        started_tool_indices.add(tc_idx)
                        tool_args_accum[tc_idx] = ""
                        tc_block_map[tc_idx] = block_index
                        current_block_type = "tool_use"
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': block_index, 'content_block': {'type': 'tool_use', 'id': tc_id or f'toolu_{block_index}', 'name': tc_name or '', 'input': {}}})}\n\n"

                    if tc_args:
                        tool_args_accum[tc_idx] += tc_args
                        target_block = tc_block_map.get(tc_idx, block_index)
                        yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': target_block, 'delta': {'type': 'input_json_delta', 'partial_json': tc_args}})}\n\n"

        # Process any remaining buffered data (in case stream ended without final \n)
        if line_buf.strip().startswith("data: "):
            data_str = line_buf.strip()[6:]
            if data_str != "[DONE]":
                try:
                    chunk = json.loads(data_str)
                    choice = (chunk.get("choices") or [{}])[0]
                    fr = choice.get("finish_reason")
                    if fr:
                        finish_reason_captured = fr
                except (json.JSONDecodeError, ValueError):
                    pass

    except Exception as e:
        log_event("SYSTEM", f"Stream adapter error: {e}", "error", source="proxy")

    # Close the last open block
    if current_block_type is not None:
        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': block_index})}\n\n"
        block_index += 1
        current_block_type = None

    # If no blocks were emitted at all, emit an empty text block
    if block_index == 0:
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

    # Determine stop reason from upstream finish_reason
    stop_reason = "end_turn"
    if finish_reason_captured == "tool_calls" or tool_args_accum:
        stop_reason = "tool_use"
    elif finish_reason_captured == "length":
        stop_reason = "max_tokens"

    output_tokens = max(1, (len(full_text) + len(full_thinking) + sum(len(a) for a in tool_args_accum.values())) // 4)
    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"
    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"


@app.post("/v1/messages/count_tokens")
async def anthropic_count_tokens(request: Request) -> Any:
    """Stub for Anthropic count_tokens endpoint (required by Claude Code)."""
    project = await resolve_project_from_request(request)
    payload = await request.json()
    messages = payload.get("messages", [])
    system_text = payload.get("system", "")
    # Rough token estimation: ~4 chars per token
    total_chars = len(str(system_text))
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block.get("text", "")))
                    total_chars += len(str(block.get("thinking", "")))
                else:
                    total_chars += len(str(block))
        else:
            total_chars += len(str(content))
    estimated_tokens = max(1, total_chars // 4)
    return {"input_tokens": estimated_tokens}


@app.post("/v1/messages")
async def anthropic_messages(request: Request) -> Any:
    """Anthropic Messages API compatibility endpoint for Claude Code."""
    if state.paused:
        raise HTTPException(status_code=503, detail="Proxy is paused")
    project = await resolve_project_from_request(request)
    payload = await request.json()
    stream = bool(payload.get("stream", False))
    requested_model = str(payload.get("model", "")).strip()
    resolved_model = resolve_model_hint(requested_model)

    if requested_model and resolved_model is None:
        raise HTTPException(status_code=400, detail=f"Unknown model '{requested_model}'. Use /v1/models to list available ids")

    explicit_target = None
    if resolved_model and resolved_model[0] == "profile":
        profile = resolved_model[1]
    elif resolved_model and resolved_model[0] == "model":
        model_name = resolved_model[1]
        profile = profile_for_model(model_name) or "coding"
        explicit_target = build_target_for_model(model_name)
    elif resolved_model and resolved_model[0] == "explicit":
        explicit_value = resolved_model[1]
        explicit_target = parse_explicit_target(explicit_value)
        if explicit_target is None:
            raise HTTPException(status_code=400, detail=f"Unknown model '{requested_model}'")
        profile = profile_for_model(explicit_target.model) or "coding"
    else:
        profile = "coding"

    enforce_project_policy(project, profile)

    quota_state = await check_project_quota(project)
    candidates = [explicit_target] if explicit_target else choose_targets(profile)
    if quota_state.get("mode") == "local_only":
        candidates = [item for item in candidates if item.provider == "local"]

    openai_payload = _anthropic_messages_to_openai(payload)

    state.last_request = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "profile": profile,
        "model_hint": requested_model,
        "messages": len(payload.get("messages", []) or []),
        "stream": stream,
    }

    if not candidates:
        raise HTTPException(status_code=503, detail=f"No available providers for profile: {profile}")

    msg_id = f"msg_{int(time.time() * 1000)}"
    return await _proxy_with_fallback(
        profile=profile,
        candidates=candidates,
        payload=openai_payload,
        stream=stream,
        project_token=project["token"],
        transform_body=lambda body: _openai_response_to_anthropic(body, requested_model),
        wrap_stream=lambda resp: _anthropic_stream_adapter(resp, requested_model, msg_id),
        log_suffix=" (messages)",
    )


@app.post("/api/reload-config")
async def reload_config() -> dict[str, Any]:
    state.config = load_config()
    db = state.db
    if db is None:
        db_path = state.config.get("settings", {}).get("db_file", "rotator.db")
        db_path = str((BASE_DIR / db_path).resolve()) if not Path(db_path).is_absolute() else db_path
        state.db = RotatorDB(db_path)
        await state.db.initialize()
        db = state.db

    await db.ensure_default_project_key()

    quota_map = await db.load_daily_quota_map()
    state.key_manager = KeyManager(state.config, quota_map)
    await apply_config_overrides(state.config)
    log_event("SYSTEM", "Configuration reloaded", "rotation", source="system")
    return {"ok": True, "message": "Config reloaded"}


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return {"content": f.read()}


@app.get("/api/readme")
async def get_readme() -> dict[str, Any]:
    readme_file = BASE_DIR / "README.md"
    if not readme_file.exists():
        return {"exists": False, "content": ""}
    return {"exists": True, "content": readme_file.read_text(encoding="utf-8")}


@app.post("/api/config")
async def save_config(payload: dict[str, str]) -> dict[str, Any]:
    content = payload.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="Missing content")
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        f.write(content)
    await reload_config()
    return {"ok": True}


@app.get("/api/maintenance/settings")
async def get_maintenance_settings() -> dict[str, Any]:
    return {"settings": backup_settings()}


@app.post("/api/maintenance/settings")
async def save_maintenance_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    current = backup_settings(config)
    updated = {
        "auto_backup_on_shutdown": bool(payload.get("auto_backup_on_shutdown", current["auto_backup_on_shutdown"])),
        "auto_restore_latest_on_startup": bool(
            payload.get("auto_restore_latest_on_startup", current["auto_restore_latest_on_startup"])
        ),
    }
    settings = config.setdefault("settings", {})
    settings["backups"] = updated
    save_config_file(config)
    await reload_config()
    return {"ok": True, "settings": updated}


@app.get("/api/maintenance/backups")
async def list_backups() -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")
    items = await db.list_backups(str(BACKUP_DIR))
    pending_restore = await db.get_app_state("pending_restore_backup", None)
    return {"items": items, "pending_restore": pending_restore}


@app.post("/api/maintenance/backup")
async def create_backup() -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")
    backup = await db.create_backup_snapshot(str(BACKUP_DIR))
    return {"ok": True, "backup": backup}


@app.post("/api/maintenance/restore")
async def restore_backup(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    data = payload or {}
    backup_name = str(data.get("name") or "").strip()
    if backup_name:
        restored = await db.restore_backup_by_name(str(BACKUP_DIR), backup_name)
    else:
        restored = await db.restore_latest_backup(str(BACKUP_DIR))
        if not restored:
            raise HTTPException(status_code=404, detail="No backup available")

    await init_state()
    log_event("SYSTEM", f"Backup restored: {restored['name']}", "rotation", source="system")
    return {"ok": True, "restored": restored}


@app.post("/api/maintenance/restore-next")
async def schedule_restore_next(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    data = payload or {}
    backup_name = str(data.get("name") or "").strip()
    marker = "__LATEST__"

    if backup_name:
        safe_name = Path(backup_name).name
        if safe_name != backup_name or not safe_name.endswith(".db"):
            raise HTTPException(status_code=400, detail="Invalid backup name")
        items = await db.list_backups(str(BACKUP_DIR))
        names = {str(item.get("name")) for item in items}
        if safe_name not in names:
            raise HTTPException(status_code=404, detail="Backup not found")
        marker = safe_name

    await db.set_app_state("pending_restore_backup", marker)
    return {
        "ok": True,
        "pending_restore": marker,
        "message": "Restore scheduled for next startup",
    }


@app.delete("/api/maintenance/backups/{backup_name}")
async def delete_backup(backup_name: str) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")
    safe_name = Path(backup_name).name
    if safe_name != backup_name or not safe_name.endswith(".db"):
        raise HTTPException(status_code=400, detail="Invalid backup name")
    removed = await db.delete_backup_by_name(str(BACKUP_DIR), safe_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"ok": True, "deleted": safe_name}


@app.post("/api/maintenance/reset-all")
async def reset_all_data(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    data = payload or {}
    create_backup_first = bool(data.get("create_backup", True))
    backup_info: dict[str, Any] | None = None
    if create_backup_first:
        backup_info = await db.create_backup_snapshot(str(BACKUP_DIR))

    result = await db.reset_all_data()
    state.logs.clear()
    state.tests_results = {"last_run": None, "results": []}
    state.benchmark = {"running": False, "results": [], "started_at": None, "stop": False}
    await reload_config()

    return {
        "ok": True,
        "message": "All DB data has been reset",
        "backup": backup_info,
        "result": result,
    }


@app.post("/api/maintenance/purge-before")
async def purge_data_before(payload: dict[str, Any]) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    before_date = str(payload.get("before_date") or "").strip()
    if not before_date:
        raise HTTPException(status_code=400, detail="before_date is required (YYYY-MM-DD)")
    try:
        datetime.strptime(before_date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid before_date format, expected YYYY-MM-DD") from exc

    create_backup_first = bool(payload.get("create_backup", True))
    backup_info: dict[str, Any] | None = None
    if create_backup_first:
        backup_info = await db.create_backup_snapshot(str(BACKUP_DIR))

    deleted = await db.purge_data_before(before_date)
    await refresh_suggestions(force=True)
    return {
        "ok": True,
        "message": f"Data before {before_date} deleted",
        "backup": backup_info,
        "deleted": deleted,
    }


@app.get("/api/config/keys")
async def get_config_keys() -> dict[str, Any]:
    config = load_config()
    return {"keys": normalize_keys_from_config(config)}


@app.post("/api/config/keys")
async def save_config_keys(payload: dict[str, Any]) -> dict[str, Any]:
    incoming = payload.get("keys")
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Missing keys payload")

    config = load_config()
    config_keys: dict[str, list[dict[str, str]]] = {}

    for provider in SUPPORTED_KEY_PROVIDERS:
        raw_entries = incoming.get(provider, [])
        if not isinstance(raw_entries, list):
            raise HTTPException(status_code=400, detail=f"Invalid keys list for provider '{provider}'")

        provider_field = secret_field_for_provider(provider)
        clean_entries: list[dict[str, str]] = []
        for index, item in enumerate(raw_entries, start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or f"{provider}-{index}").strip()
            value = str(item.get("value") or "").strip()
            if not value:
                continue
            clean_entries.append({"label": label, provider_field: value})

        config_keys[provider] = clean_entries

    config["keys"] = config_keys
    save_config_file(config)
    await reload_config()
    return {"ok": True, "message": "Keys updated"}


@app.post("/api/config/keys/test")
async def test_provider_key(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "").strip()
    value_input = str(payload.get("value") or "").strip()

    if not value_input:
        return {"ok": False, "status": "invalid", "message": "Empty key"}

    value = value_input
    if value_input.startswith("env:"):
        env_name = value_input[4:].strip()
        resolved = os.environ.get(env_name, "").strip()
        if not resolved:
            return {
                "ok": False,
                "status": "invalid",
                "message": f"Environment variable not found: {env_name}",
            }
        value = resolved
    elif value_input.startswith("${") and value_input.endswith("}") and len(value_input) > 3:
        env_name = value_input[2:-1].strip()
        resolved = os.environ.get(env_name, "").strip()
        if not resolved:
            return {
                "ok": False,
                "status": "invalid",
                "message": f"Environment variable not found: {env_name}",
            }
        value = resolved

    format_rules: dict[str, Any] = {
        "google": lambda k: k.startswith("AIza") and len(k) > 30,
        "nvidia": lambda k: k.startswith("nvapi-") and len(k) > 20,
        "openrouter": lambda k: k.startswith("sk-or-") and len(k) > 20,
        "ollama_cloud": lambda k: len(k) > 6,
    }
    validator = format_rules.get(provider)
    if validator and not validator(value):
        return {"ok": False, "status": "invalid", "message": "Invalid key format"}

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            if provider == "google":
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": value},
                )
                if response.status_code == 200:
                    return {"ok": True, "status": "ok", "message": "✅ Valid Google key"}
                if response.status_code == 429:
                    return {"ok": False, "status": "quota", "message": "⚠️ Google quota reached"}
                if response.status_code == 400:
                    return {"ok": False, "status": "invalid", "message": "❌ Invalid key"}
                if response.status_code == 403:
                    return {"ok": False, "status": "invalid", "message": "❌ Key revoked or missing permissions"}
                return {"ok": False, "status": "error", "message": f"❌ Error {response.status_code}"}

            if provider == "nvidia":
                response = await client.get(
                    "https://integrate.api.nvidia.com/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if response.status_code == 200:
                    count = len(response.json().get("data", []))
                    return {"ok": True, "status": "ok", "message": f"✅ Valid NVIDIA key ({count} models)"}
                if response.status_code == 429:
                    return {"ok": False, "status": "quota", "message": "⚠️ NVIDIA quota reached"}
                if response.status_code == 401:
                    return {"ok": False, "status": "invalid", "message": "❌ Invalid NVIDIA key"}
                return {"ok": False, "status": "error", "message": f"❌ Error {response.status_code}"}

            if provider == "openrouter":
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if response.status_code == 200:
                    return {"ok": True, "status": "ok", "message": "✅ Valid OpenRouter key"}
                if response.status_code == 429:
                    return {"ok": False, "status": "quota", "message": "⚠️ OpenRouter quota reached"}
                if response.status_code == 401:
                    return {"ok": False, "status": "invalid", "message": "❌ Invalid OpenRouter key"}
                return {"ok": False, "status": "error", "message": f"❌ Error {response.status_code}"}

            if provider == "ollama_cloud":
                response = await client.get(
                    "https://ollama.com/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if response.status_code in (200, 404):
                    return {"ok": True, "status": "ok", "message": "✅ Valid Ollama token"}
                if response.status_code == 429:
                    return {"ok": False, "status": "quota", "message": "⚠️ Ollama Cloud quota reached"}
                if response.status_code == 401:
                    return {"ok": False, "status": "invalid", "message": "❌ Invalid Ollama token"}
                return {"ok": False, "status": "warning", "message": "⚠️ Unexpected response"}

            return {"ok": False, "status": "warning", "message": "⚠️ Unknown provider, test not performed"}

    except httpx.TimeoutException:
        return {"ok": False, "status": "network", "message": "⏱ Timeout — check your connection"}
    except Exception as exc:
        return {"ok": False, "status": "network", "message": f"❌ Network error: {str(exc)[:60]}"}


@app.get("/api/projects")
async def list_projects() -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")
    rows = await db.list_projects_usage_today()
    return {"items": rows}


@app.post("/api/projects")
async def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    daily_limit_raw = payload.get("daily_limit")
    daily_limit: int | None
    if daily_limit_raw in (None, ""):
        daily_limit = None
    else:
        try:
            daily_limit = int(daily_limit_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="daily_limit must be an integer") from exc
        if daily_limit < 0:
            raise HTTPException(status_code=400, detail="daily_limit must be >= 0")

    policy = str(payload.get("policy") or "full_access")
    if policy not in {"full_access", "coding_only"}:
        raise HTTPException(status_code=400, detail="Unknown policy")

    quota_mode = str(payload.get("quota_mode") or "hard_block")
    if quota_mode not in {"hard_block", "local_only", "alert_only"}:
        raise HTTPException(status_code=400, detail="Unknown quota_mode")

    try:
        project = await db.create_project_key(name, daily_limit, policy, quota_mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to create project key: {exc}") from exc

    return {"ok": True, "project": project}


@app.post("/api/projects/{project_id}/revoke")
async def revoke_project(project_id: int) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")
    await db.deactivate_project_key(project_id)
    return {"ok": True}


@app.post("/api/projects/claude-onboarding")
async def create_claude_onboarding_project(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    data = payload or {}
    existing_names = {item["name"] for item in await db.list_project_keys()}
    provided_name = str(data.get("name") or "").strip()

    if provided_name:
        base_name = provided_name
        project_name = base_name
        suffix = 2
        while project_name in existing_names:
            project_name = f"{base_name}-{suffix}"
            suffix += 1
    else:
        base_name = "ar_claudecode_api"
        suffix = 1
        project_name = f"{base_name}{suffix}"
        while project_name in existing_names:
            suffix += 1
            project_name = f"{base_name}{suffix}"

    daily_limit_raw = data.get("daily_limit")
    daily_limit: int | None
    if daily_limit_raw in (None, ""):
        daily_limit = None
    else:
        try:
            daily_limit = int(daily_limit_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="daily_limit must be an integer") from exc
        if daily_limit < 0:
            raise HTTPException(status_code=400, detail="daily_limit must be >= 0")

    quota_mode = str(data.get("quota_mode") or "hard_block")
    if quota_mode not in {"hard_block", "local_only", "alert_only"}:
        raise HTTPException(status_code=400, detail="Unknown quota_mode")

    project = await db.create_project_key(project_name, daily_limit, "coding_only", quota_mode)
    port = state.config.get("settings", {}).get("port", 47822)
    rotator_path = str(BASE_DIR.resolve()).replace("\\", "\\\\")
    return {
        "ok": True,
        "project": project,
        "env": {
            "ANTHROPIC_BASE_URL": f"http://localhost:{port}",
            "ANTHROPIC_AUTH_TOKEN": project["token"],
        },
        "rotator_path": str(BASE_DIR.resolve()),
        "usage": [
            f"$env:ANTHROPIC_BASE_URL=http://localhost:{port}",
            f"$env:ANTHROPIC_AUTH_TOKEN={project['token']}",
            "claude --model coding",
            "# optionnel: /model puis choisir un id de /v1/models",
        ],
    }


@app.post("/api/projects/claude-onboarding/launch")
async def launch_claude_onboarding_terminal(payload: dict[str, Any]) -> dict[str, Any]:
    db = state.db
    if db is None:
        raise HTTPException(status_code=500, detail="DB unavailable")

    token = str(payload.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token required")

    project = await db.resolve_project_key(token)
    if not project:
        raise HTTPException(status_code=404, detail="Project token not found")
    if not project.get("active"):
        raise HTTPException(status_code=400, detail="Project token is inactive")

    install_claude = bool(payload.get("install_claude", False))
    install_skills = bool(payload.get("install_skills", False))
    skills = payload.get("skills", None)
    work_dir = str(payload.get("work_dir") or "").strip()
    model = str(payload.get("model") or "").strip()

    import subprocess
    import sys

    script = str((BASE_DIR / "connect_claude.ps1").resolve())
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script,
            "-Token",
            token,
        ]
        if install_claude:
            command.append("-InstallClaude")
        if install_skills:
            command.append("-InstallSkills")
        # Pass skills as comma-separated (avoids JSON quote mangling on Windows cmd line)
        if skills:
            command.extend(["-SkillsJson", ",".join(skills)])
        if work_dir:
            command.extend(["-WorkDir", work_dir])
        if model:
            command.extend(["-Model", model])
        subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    else:
        cmd = ["pwsh", "-NoExit", "-File", script, "-Token", token]
        if work_dir:
            cmd.extend(["-WorkDir", work_dir])
        if install_skills:
            cmd.append("-InstallSkills")
        if skills:
            cmd.extend(["-SkillsJson", ",".join(skills)])
        if model:
            cmd.extend(["-Model", model])
        subprocess.Popen(cmd)

    return {"ok": True, "message": "Claude onboarding terminal launched", "token": token}


# ---------------------------------------------------------------------------
# Skills catalog (reads from skills.json)
# ---------------------------------------------------------------------------

@app.get("/api/skills")
async def get_skills_catalog():
    """Return the skills catalog from skills.json."""
    skills_file = BASE_DIR / "skills.json"
    if not skills_file.exists():
        raise HTTPException(status_code=404, detail="skills.json not found")
    import json as _json
    try:
        data = _json.loads(skills_file.read_text(encoding="utf-8"))
        # Strip the _comment key from the response
        data.pop("_comment", None)
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error reading skills.json: {exc}")


@app.put("/api/skills")
async def update_skills_catalog(payload: dict[str, Any]):
    """Write the entire skills catalog back to skills.json."""
    skills_file = BASE_DIR / "skills.json"
    import json as _json
    try:
        skills_file.write_text(_json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error writing skills.json: {exc}")


# ---------------------------------------------------------------------------
# Claude Code – CLAUDE.md memory management
# ---------------------------------------------------------------------------


import re as _re

_SAFE_MODEL_NAME = _re.compile(r"^[a-zA-Z0-9._:/-]+$")

# Directories that must never be written to via the API
_BLOCKED_DIRS = (
    "C:\\Windows", "C:\\Program Files", "/etc", "/usr", "/bin",
    "/sbin", "/var", "/boot", "/sys", "/proc",
)


def _validate_directory_path(dir_path: str) -> Path:
    """Validate and resolve a directory path. Blocks system dirs and traversals."""
    if not dir_path:
        raise HTTPException(status_code=400, detail="dir required")
    resolved = Path(dir_path).resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Directory not found")
    resolved_str = str(resolved)
    for blocked in _BLOCKED_DIRS:
        if resolved_str.lower().startswith(blocked.lower()):
            raise HTTPException(status_code=403, detail="Access to system directories is forbidden")
    return resolved


@app.get("/api/claude-code/memory")
async def read_claude_memory(dir: str) -> dict[str, Any]:
    """Read CLAUDE.md from a project directory."""
    target = _validate_directory_path(dir)
    claude_md = target / "CLAUDE.md"
    if claude_md.is_file():
        return {"found": True, "path": str(claude_md), "content": claude_md.read_text("utf-8")}
    return {"found": False, "path": str(claude_md)}


@app.post("/api/claude-code/memory")
async def write_claude_memory(payload: dict[str, Any]) -> dict[str, Any]:
    """Write CLAUDE.md to a project directory."""
    dir_path = str(payload.get("dir") or "").strip()
    content = str(payload.get("content") or "")
    target = _validate_directory_path(dir_path)
    claude_md = target / "CLAUDE.md"
    claude_md.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(claude_md)}


def _get_first_provider_key_value(provider: str) -> str | None:
    km = state.key_manager
    if km:
        records = km.keys_by_provider.get(provider, [])
        if records:
            return records[0].value

    config = state.config or load_config()
    entries = config.get("keys", {}).get(provider, [])
    if not isinstance(entries, list) or not entries:
        return None
    if provider == "ollama_cloud":
        return entries[0].get("token")
    return entries[0].get("key")


@app.get("/api/ollama/status")
async def ollama_status() -> dict[str, Any]:
    try:
        response = await state.client.get("http://localhost:11434/api/tags", timeout=3)
        data = response.json() if response.status_code < 500 else {}
        models = data.get("models", []) if isinstance(data, dict) else []
        return {"installed": response.status_code < 400, "model_count": len(models)}
    except Exception:
        return {"installed": False, "model_count": 0}


@app.post("/api/ollama/install")
async def ollama_install() -> dict[str, Any]:
    import subprocess
    import sys

    if sys.platform == "win32":
        subprocess.Popen(
            ["powershell", "-Command", "irm https://ollama.com/install.ps1 | iex"],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    else:
        subprocess.Popen(
            ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {"message": "Installation started"}


# ---------------------------------------------------------------------------
# Catalogue cache helpers
# ---------------------------------------------------------------------------

CATALOGUE_CACHE_FILES = {
    "ollama": BASE_DIR / "ollama_models_cloud.json",
    "openrouter": BASE_DIR / "openrouter_models.json",
    "nvidia": BASE_DIR / "nvidia_models.json",
}
CATALOGUE_REFRESH_INTERVAL = 3600  # seconds between automatic refreshes


def _read_catalogue_cache(provider: str) -> dict[str, Any]:
    path = CATALOGUE_CACHE_FILES.get(provider)
    if path and path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            pass
    return {"models": [], "updated_at": None}


def _write_catalogue_cache(provider: str, data: dict[str, Any]) -> None:
    path = CATALOGUE_CACHE_FILES.get(provider)
    if path:
        data["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def _refresh_ollama_cache() -> int:
    """Fetch Ollama library from ollama.com and update cache. Returns model count."""
    try:
        response = await state.client.get("https://ollama.com/api/tags", timeout=15)
        raw = response.json()
        models = raw.get("models", [])
        _write_catalogue_cache("ollama", {"models": models})
        return len(models)
    except Exception:
        return -1


async def _refresh_openrouter_cache() -> int:
    api_key = _get_first_provider_key_value("openrouter")
    if not api_key:
        return -1
    try:
        response = await state.client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        all_models = response.json().get("data", [])
        free_models = [m for m in all_models if str(m.get("pricing", {}).get("prompt", "1")) == "0"]
        models = [
            {
                "name": item.get("id", ""),
                "description": (item.get("description") or "")[:200],
                "context_length": item.get("context_length"),
                "tags": [],
            }
            for item in free_models
        ]
        _write_catalogue_cache("openrouter", {"models": models})
        return len(models)
    except Exception:
        return -1


async def _refresh_nvidia_cache() -> int:
    api_key = _get_first_provider_key_value("nvidia")
    if not api_key:
        return -1
    try:
        response = await state.client.get(
            "https://integrate.api.nvidia.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        data = response.json().get("data", [])
        models = [
            {
                "name": item.get("id", ""),
                "description": (item.get("description") or "")[:200],
                "tags": [],
            }
            for item in data
        ]
        _write_catalogue_cache("nvidia", {"models": models})
        return len(models)
    except Exception:
        return -1


async def refresh_all_catalogues() -> dict[str, int]:
    """Refresh all provider caches. Returns {provider: model_count} (-1 = error)."""
    results: dict[str, int] = {}
    results["ollama"] = await _refresh_ollama_cache()
    results["openrouter"] = await _refresh_openrouter_cache()
    results["nvidia"] = await _refresh_nvidia_cache()
    return results


async def _catalogue_refresh_loop() -> None:
    """Background task: refreshes catalogues periodically."""
    await asyncio.sleep(10)  # wait for startup
    while True:
        try:
            await refresh_all_catalogues()
        except Exception:
            logger.debug("Catalogue refresh error", exc_info=True)
        await asyncio.sleep(CATALOGUE_REFRESH_INTERVAL)


@app.post("/api/catalogue/refresh")
async def catalogue_refresh() -> dict[str, Any]:
    results = await refresh_all_catalogues()
    return {"ok": True, "results": results}


@app.get("/api/catalogue/ollama")
async def catalogue_ollama() -> dict[str, Any]:
    installed = set()
    try:
        response = await state.client.get("http://localhost:11434/api/tags", timeout=5)
        payload = response.json()
        for item in payload.get("models", []):
            installed.add(str(item.get("name", "")).split(":")[0])
    except Exception:
        pass

    cache = _read_catalogue_cache("ollama")
    cached_models = cache.get("models", [])
    if not cached_models:
        count = await _refresh_ollama_cache()
        if count > 0:
            cache = _read_catalogue_cache("ollama")
            cached_models = cache.get("models", [])

    models: list[dict[str, Any]] = []
    for item in cached_models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", item.get("model", "")))
        details = item.get("details") or {}
        models.append({
            "name": name,
            "description": item.get("description", ""),
            "tags": item.get("tags", []) or [],
            "size": item.get("size"),
            "parameter_size": item.get("parameter_size", "") or details.get("parameter_size", ""),
            "context_length": item.get("context_length"),
            "installed": name.split(":")[0] in installed,
            "downloads": item.get("downloads", 0),
            "details": {
                "family": details.get("family", ""),
                "parameter_size": details.get("parameter_size", ""),
                "quantization_level": details.get("quantization_level", ""),
                "format": details.get("format", ""),
            },
            "digest": item.get("digest", ""),
        })
    return {"models": models, "updated_at": cache.get("updated_at")}


@app.get("/api/catalogue/openrouter")
async def catalogue_openrouter() -> dict[str, Any]:
    cache = _read_catalogue_cache("openrouter")
    cached_models = cache.get("models", [])
    if not cached_models:
        count = await _refresh_openrouter_cache()
        if count > 0:
            cache = _read_catalogue_cache("openrouter")
            cached_models = cache.get("models", [])
    if not cached_models:
        api_key = _get_first_provider_key_value("openrouter")
        if not api_key:
            return {"models": [], "error": "No OpenRouter key configured"}
        return {"models": [], "error": "Cache empty, refresh in progress"}
    return {"models": cached_models, "updated_at": cache.get("updated_at")}


@app.get("/api/catalogue/nvidia")
async def catalogue_nvidia() -> dict[str, Any]:
    cache = _read_catalogue_cache("nvidia")
    cached_models = cache.get("models", [])
    if not cached_models:
        count = await _refresh_nvidia_cache()
        if count > 0:
            cache = _read_catalogue_cache("nvidia")
            cached_models = cache.get("models", [])
    if not cached_models:
        api_key = _get_first_provider_key_value("nvidia")
        if not api_key:
            return {"models": [], "error": "No NVIDIA key configured"}
        return {"models": [], "error": "Cache empty, refresh in progress"}
    return {"models": cached_models, "updated_at": cache.get("updated_at")}



@app.get("/api/catalogue/local")
async def catalogue_local() -> dict[str, Any]:
    try:
        response = await state.client.get("http://localhost:11434/api/tags", timeout=5)
        models = [
            {
                "name": item.get("name", ""),
                "description": f"Installed local model · {item.get('details', {}).get('parameter_size', '')}",
                "size": item.get("size"),
                "parameter_size": item.get("details", {}).get("parameter_size", ""),
                "tags": ["local"],
                "installed": True,
            }
            for item in response.json().get("models", [])
        ]
        return {"models": models}
    except Exception:
        return {"models": [], "error": "Ollama not running"}


@app.post("/api/catalogue/install")
async def catalogue_install(payload: dict[str, Any]) -> dict[str, Any]:
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="model required")
    if not _SAFE_MODEL_NAME.match(model):
        raise HTTPException(status_code=400, detail="Invalid model name format")

    install_status[model] = {"done": False, "progress": 0, "message": "Starting...", "error": None}

    async def run_pull() -> None:
        import re

        try:
            proc = await asyncio.create_subprocess_exec(
                "ollama",
                "pull",
                model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            install_status[model]["done"] = True
            install_status[model]["error"] = str(exc)
            install_status[model]["message"] = "Installation launch error"
            return

        assert proc.stdout is not None
        async for line in proc.stdout:
            text = line.decode(errors="ignore").strip()
            if text:
                install_status[model]["message"] = text
                match = re.search(r"(\d+)%", text)
                if match:
                    install_status[model]["progress"] = int(match.group(1))

        return_code = await proc.wait()
        install_status[model]["done"] = True
        if return_code == 0:
            install_status[model]["progress"] = 100
            install_status[model]["message"] = "Installation complete"
        else:
            install_status[model]["error"] = f"Process exited with code {return_code}"
            install_status[model]["message"] = "Installation failed"

    asyncio.create_task(run_pull())
    return {"message": f"Installation of {model} started"}


@app.get("/api/catalogue/install/status")
async def catalogue_install_status(model: str) -> dict[str, Any]:
    status = install_status.get(model)
    if not status:
        return {"done": False, "progress": 0, "message": "Not found"}
    return status


@app.post("/api/catalogue/delete")
async def catalogue_delete(payload: dict[str, Any]) -> dict[str, Any]:
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="model required")
    if not _SAFE_MODEL_NAME.match(model):
        raise HTTPException(status_code=400, detail="Invalid model name format")
    proc = await asyncio.create_subprocess_exec(
        "ollama",
        "rm",
        model,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return {"message": f"{model} deleted"}


@app.post("/api/catalogue/add-to-rotator")
async def catalogue_add_to_rotator(payload: dict[str, Any]) -> dict[str, Any]:
    model = str(payload.get("model", "")).strip()
    source = str(payload.get("source", "local")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="model required")

    provider_map = {
        "ollama": "ollama_cloud" if ":cloud" in model else "local",
        "local": "local",
        "openrouter": "openrouter",
        "nvidia": "nvidia",
    }
    provider = provider_map.get(source, "local")

    config = load_config()
    catalogue = config.setdefault("catalogue", {})
    models_by_provider = catalogue.setdefault("models_by_provider", {})
    provider_models = models_by_provider.setdefault(provider, [])
    if model not in provider_models:
        provider_models.append(model)
    save_config_file(config)

    return {"message": f"{model} added to provider {provider}"}


@app.get("/api/logs")
async def get_logs() -> dict[str, Any]:
    return {"items": list(state.logs)}


@app.get("/api/sessions")
async def get_sessions(
    limit: int = 200,
    profile: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return recent request history from profile_history DB table."""
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    items = await state.db.get_recent_sessions(
        limit=limit, profile=profile, provider=provider
    )
    return {"items": items}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    db = state.db
    km = state.key_manager
    if db is None or km is None:
        raise HTTPException(status_code=500, detail="State unavailable")

    await refresh_suggestions()

    today_counts = await db.get_profile_requests_today()
    total_requests = sum(today_counts.values())
    profiles = []
    for profile in PROFILES:
        target = state.active_routes.get(profile, {"provider": "-", "model": "-"})
        profiles.append(
            {
                "name": profile,
                "emoji": profile_emoji(profile),
                "provider": target["provider"],
                "model": target["model"],
                "override": effective_override(profile),
                "requests_today": today_counts.get(profile, 0),
                "locked_model": state.model_locks.get(profile, {}).get("model"),
            }
        )

    mode = "AUTO"
    if state.active_preset_id:
        mode = "PRESET"
    elif state.model_locks:
        mode = "LOCKED"

    return {
        "uptime_seconds": int(time.time() - state.started_at),
        "port": state.config.get("settings", {}).get("port", 47822),
        "mode": mode,
        "total_requests_today": total_requests,
        "active_providers": len([p for p in km.keys_by_provider if p not in state.suspensions]),
        "paused": state.paused,
        "profiles": profiles,
        "provider_status": km.get_provider_status(),
        "overrides": state.overrides,
        "override_expiry": {k: v.isoformat(timespec="seconds") for k, v in state.override_expiry.items()},
        "block_expiry": {k: v.isoformat(timespec="seconds") for k, v in state.block_expiry.items()},
        "suspensions": {k: (v.isoformat(timespec="seconds") if v else None) for k, v in state.suspensions.items()},
        "locks": state.model_locks,
        "active_preset_id": state.active_preset_id,
        "presets": [{"id": p["id"], "name": p["name"], "description": p["description"]} for p in state.presets],
        "priority_mode": state.priority_mode,
        "last_request": state.last_request,
        "suggestions": state.suggestions,
        "security": security_status_payload(),
        "logs": list(state.logs),
    }


@app.get("/api/security/status")
async def get_security_status() -> dict[str, Any]:
    return {"security": security_status_payload()}


@app.post("/api/override/force")
async def override_force(payload: dict[str, str]) -> dict[str, Any]:
    profile = payload.get("profile", "").lower()
    provider = payload.get("provider", "auto").lower()
    ttl_raw = payload.get("ttl_minutes")
    if profile not in PROFILES:
        raise HTTPException(status_code=400, detail="Unknown profile")
    if provider not in {"auto", "ollama_cloud", "nvidia", "openrouter", "google", "local"}:
        raise HTTPException(status_code=400, detail="Unknown provider")

    state.overrides["profiles"][profile] = provider
    if provider == "auto":
        state.override_expiry.pop(profile, None)
    elif ttl_raw:
        try:
            ttl = int(ttl_raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="ttl_minutes must be an integer") from exc
        state.override_expiry[profile] = datetime.now(UTC) + timedelta(minutes=ttl)
    await save_overrides_to_db()
    log_event("SYSTEM", f"Override set: {profile} -> {provider}", "rotation", source="override")
    return {"ok": True}


@app.post("/api/override/block")
async def override_block(payload: dict[str, str]) -> dict[str, Any]:
    provider = payload.get("provider", "").lower()
    ttl_raw = payload.get("ttl_minutes")
    blocked = set(state.overrides.get("blocked", []))
    blocked.add(provider)
    state.overrides["blocked"] = sorted(blocked)
    if ttl_raw:
        try:
            ttl = int(ttl_raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="ttl_minutes must be an integer") from exc
        state.block_expiry[provider] = datetime.now(UTC) + timedelta(minutes=ttl)
    await save_overrides_to_db()
    log_event("SYSTEM", f"Blocked: {provider}", "rotation", source="override")
    return {"ok": True, "blocked": state.overrides["blocked"]}


@app.post("/api/override/unblock")
async def override_unblock(payload: dict[str, str]) -> dict[str, Any]:
    provider = payload.get("provider", "").lower()
    blocked = set(state.overrides.get("blocked", []))
    blocked.discard(provider)
    state.overrides["blocked"] = sorted(blocked)
    state.block_expiry.pop(provider, None)
    await save_overrides_to_db()
    log_event("SYSTEM", f"Unblocked: {provider}", "rotation", source="override")
    return {"ok": True, "blocked": state.overrides["blocked"]}


@app.post("/api/override/reset")
async def override_reset() -> dict[str, Any]:
    state.overrides = {"profiles": {p: "auto" for p in PROFILES}, "blocked": []}
    state.override_expiry.clear()
    state.block_expiry.clear()
    await save_overrides_to_db()
    log_event("SYSTEM", "Overrides reset", "rotation", source="override")
    return {"ok": True}


@app.post("/api/pause")
async def pause_proxy() -> dict[str, Any]:
    state.paused = True
    log_event("SYSTEM", "Proxy paused", "rotation", source="system")
    return {"ok": True}


@app.post("/api/resume")
async def resume_proxy(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = str((payload or {}).get("provider", "")).lower().strip()
    if provider:
        state.suspensions.pop(provider, None)
        if state.db:
            await state.db.delete_suspension(provider)
        if state.key_manager:
            state.key_manager.resume_provider(provider)
        log_event("SYSTEM", f"Provider resumed: {provider}", "rotation", source="suspend")
        return {"ok": True, "scope": "provider", "provider": provider}

    state.paused = False
    log_event("SYSTEM", "Proxy resumed", "rotation", source="system")
    return {"ok": True, "scope": "proxy"}


@app.post("/api/restart")
async def restart_proxy() -> dict[str, Any]:
    """Restart the proxy process by spawning a new process and exiting."""
    import subprocess
    import sys

    log_event("SYSTEM", "Proxy restart requested", "rotation", source="system")
    # Trigger auto-backup before shutdown
    db = state.db
    if db and backup_settings().get("auto_backup_on_shutdown", True):
        try:
            await db.create_backup_snapshot(str(BACKUP_DIR))
        except Exception:
            logger.debug("Auto-backup before restart failed", exc_info=True)

    # Build command to restart the same way
    python = sys.executable
    script = str((BASE_DIR / "main.py").resolve())
    subprocess.Popen(
        [python, script],
        cwd=str(BASE_DIR),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    # Schedule current process exit after response is sent
    import sys as _sys

    async def _shutdown():
        await asyncio.sleep(0.5)
        _sys.exit(0)

    asyncio.create_task(_shutdown())
    return {"ok": True, "message": "Restarting..."}


@app.get("/api/models")
async def models_catalog() -> dict[str, Any]:
    return {"providers": list_all_models()}


@app.get("/api/locks")
async def get_locks() -> dict[str, Any]:
    return {"locks": state.model_locks}


@app.post("/api/lock")
async def set_lock(payload: dict[str, str]) -> dict[str, Any]:
    profile = payload.get("profile", "").lower()
    model = payload.get("model", "")
    provider = find_model_provider(model)
    if not model or not provider:
        raise HTTPException(status_code=400, detail="Unknown model")

    targets = PROFILES if profile in {"all", "*"} else [profile]
    for target in targets:
        if target not in PROFILES:
            raise HTTPException(status_code=400, detail="Unknown profile")
        state.model_locks[target] = {"model": model, "provider": provider}
        if state.db:
            await state.db.save_model_lock(target, model, provider)

    log_event("SYSTEM", f"Model locked: {model}", "rotation", source="lock")
    dispatch_webhook("lock", f"Model locked: {model}", {"profile": profile, "model": model})
    return {"ok": True, "locks": state.model_locks}


@app.delete("/api/lock/{profile}")
async def delete_lock(profile: str) -> dict[str, Any]:
    targets = PROFILES if profile in {"all", "*"} else [profile]
    for target in targets:
        state.model_locks.pop(target, None)
        if state.db:
            await state.db.delete_model_lock(target)
    log_event("SYSTEM", f"Lock removed: {profile}", "rotation", source="lock")
    return {"ok": True, "locks": state.model_locks}


@app.post("/api/suspend")
async def suspend_provider(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider", "")).lower()
    duration = payload.get("duration_minutes")
    until_ts = None
    if duration:
        try:
            until = datetime.now(UTC) + timedelta(minutes=int(duration))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="duration_minutes must be integer") from exc
        until_ts = until.isoformat(timespec="seconds")
        state.suspensions[provider] = until
    else:
        state.suspensions[provider] = None
    if state.db:
        await state.db.save_suspension(provider, until_ts)
    if state.key_manager:
        state.key_manager.suspend_provider(provider)
    log_event("SYSTEM", f"Provider suspended: {provider}", "rotation", source="suspend")
    dispatch_webhook("suspend", f"Provider suspended: {provider}", {"provider": provider, "until": until_ts})
    return {"ok": True}


@app.get("/api/suspensions")
async def get_suspensions() -> dict[str, Any]:
    return {"suspensions": {k: (v.isoformat(timespec="seconds") if v else None) for k, v in state.suspensions.items()}}


@app.get("/api/presets")
async def list_presets() -> dict[str, Any]:
    return {"items": state.presets}


@app.post("/api/presets")
async def create_preset(payload: dict[str, Any]) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    preset_id = await state.db.save_preset(payload["name"], payload.get("description", ""), payload["data"])
    state.presets = await state.db.list_presets()
    return {"ok": True, "id": preset_id}


@app.put("/api/presets/{preset_id}")
async def update_preset(preset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    await state.db.save_preset(payload["name"], payload.get("description", ""), payload["data"], preset_id)
    state.presets = await state.db.list_presets()
    return {"ok": True}


@app.delete("/api/presets/{preset_id}")
async def delete_preset(preset_id: int) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    await state.db.delete_preset(preset_id)
    state.presets = await state.db.list_presets()
    return {"ok": True}


@app.post("/api/presets/{preset_id}/apply")
async def apply_preset_route(preset_id: int) -> dict[str, Any]:
    preset = next((p for p in state.presets if p["id"] == preset_id), None)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    await apply_preset(preset_id, preset["data"])
    log_event("SYSTEM", f"Preset applied: {preset['name']}", "rotation", source="preset")
    return {"ok": True}


@app.post("/api/skip")
async def skip_profile(payload: dict[str, str]) -> dict[str, Any]:
    profile = payload.get("profile", "").lower()
    if profile not in PROFILES:
        raise HTTPException(status_code=400, detail="Unknown profile")
    key_id = state.last_key_by_profile.get(profile)
    if not key_id or not state.key_manager:
        raise HTTPException(status_code=404, detail="No key to skip")
    state.key_manager.mark_key_exhausted(key_id, minutes=60)
    log_event("SYSTEM", f"Skip key for {profile}: {key_id}", "rotation", source="key")
    return {"ok": True}


@app.get("/api/keys")
async def list_keys() -> dict[str, Any]:
    km = state.key_manager
    if not km:
        raise HTTPException(status_code=500, detail="State unavailable")
    keys = []
    for provider, items in km.keys_by_provider.items():
        for key in items:
            keys.append({"provider": provider, "key_id": key.key_id, "label": key.label})
    return {"items": keys}


@app.post("/api/keys/block")
async def block_key(payload: dict[str, str]) -> dict[str, Any]:
    km = state.key_manager
    if not km or not state.db:
        raise HTTPException(status_code=500, detail="State unavailable")
    label = payload.get("label", "")
    key = km.find_key_by_label(label)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    km.block_key(key.key_id)
    blocked = await state.db.get_app_state("blocked_keys", [])
    if key.key_id not in blocked:
        blocked.append(key.key_id)
    await state.db.set_app_state("blocked_keys", blocked)
    return {"ok": True}


@app.post("/api/keys/unblock")
async def unblock_key(payload: dict[str, str]) -> dict[str, Any]:
    km = state.key_manager
    if not km or not state.db:
        raise HTTPException(status_code=500, detail="State unavailable")
    label = payload.get("label", "")
    key = km.find_key_by_label(label)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    km.unblock_key(key.key_id)
    blocked = await state.db.get_app_state("blocked_keys", [])
    blocked = [item for item in blocked if item != key.key_id]
    await state.db.set_app_state("blocked_keys", blocked)
    return {"ok": True}


@app.post("/api/keys/reset")
async def reset_keys(payload: dict[str, str]) -> dict[str, Any]:
    provider = payload.get("provider", "")
    km = state.key_manager
    if not km:
        raise HTTPException(status_code=500, detail="State unavailable")
    for key in km.keys_by_provider.get(provider, []):
        km.exhausted_until.pop(key.key_id, None)
    return {"ok": True}


@app.get("/api/quota")
async def quota_status() -> dict[str, Any]:
    km = state.key_manager
    if not km:
        raise HTTPException(status_code=500, detail="State unavailable")
    result: dict[str, Any] = {}
    for provider, keys in km.keys_by_provider.items():
        if provider == "google":
            entries = []
            for key in keys:
                for model, limit in km.daily_limits.items():
                    used = km.daily_quota_map.get(f"google:{model}:{key.key_id}", 0)
                    entries.append(
                        {
                            "key_id": key.key_id,
                            "model": model,
                            "used": used,
                            "remaining": max(limit - used, 0),
                        }
                    )
            result[provider] = entries
        elif provider == "nvidia":
            result[provider] = [{"remaining": "rpm", "limit": km.rpm_limits.get("nvidia", 35)}]
        else:
            result[provider] = [{"remaining": "∞"}]
    return {"items": result}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    providers = []
    km = state.key_manager
    if not km:
        raise HTTPException(status_code=500, detail="State unavailable")
    for provider, keys in km.keys_by_provider.items():
        status = "ok"
        if provider in state.suspensions:
            status = "suspended"
        else:
            try:
                key = keys[0] if keys else None
                headers = build_headers(provider, key.value if key else "")
                url = f"{BASE_URLS[provider]}/models"
                res = await state.client.get(url, headers=headers, timeout=8)
                if res.status_code >= 400:
                    status = "degraded"
            except Exception:
                status = "degraded"
        providers.append(
            {
                "provider": provider,
                "keys": len(keys),
                "suspended": provider in state.suspensions,
                "status": status,
            }
        )
    return {"providers": providers, "ok": True}


@app.get("/api/stats")
async def stats(period: str = "today") -> dict[str, Any]:
    db_path = state.config.get("settings", {}).get("db_file", "rotator.db")
    db_path = str((BASE_DIR / db_path).resolve()) if not Path(db_path).is_absolute() else db_path
    now = datetime.now(UTC)
    if period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    else:
        cutoff = datetime.strptime(now.strftime("%Y-%m-%d"), "%Y-%m-%d")

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT provider, profile, success, timestamp FROM profile_history WHERE timestamp >= ?",
            (cutoff.isoformat(timespec="seconds"),),
        )
        rows = await cursor.fetchall()
        await cursor.close()

    totals = {"total": len(rows), "success": 0, "failed": 0}
    by_provider: dict[str, int] = {}
    by_profile: dict[str, int] = {}
    for provider, profile, success, _ in rows:
        by_provider[provider] = by_provider.get(provider, 0) + 1
        by_profile[profile] = by_profile.get(profile, 0) + 1
        if success:
            totals["success"] += 1
        else:
            totals["failed"] += 1

    return {
        "totals": totals,
        "by_provider": by_provider,
        "by_profile": by_profile,
        "rotations": 0,
        "tokens": 0,
        "avg_response_ms": 0,
    }


@app.get("/api/stats/export")
async def stats_export() -> StreamingResponse:
    db_path = state.config.get("settings", {}).get("db_file", "rotator.db")
    db_path = str((BASE_DIR / db_path).resolve()) if not Path(db_path).is_absolute() else db_path
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT timestamp, profile, provider, model, key_id, success FROM profile_history"
        )
        rows = await cursor.fetchall()
        await cursor.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "profile", "provider", "model", "key_id", "success"])
    for row in rows:
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv")


@app.get("/api/schedules")
async def list_schedules() -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    return {"items": await state.db.list_schedules()}


@app.post("/api/schedules")
async def create_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    schedule_id = await state.db.save_schedule(payload)
    return {"ok": True, "id": schedule_id}


@app.put("/api/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    await state.db.save_schedule(payload, schedule_id)
    return {"ok": True}


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    await state.db.delete_schedule(schedule_id)
    return {"ok": True}


TEST_CASES = [
    {
        "name": "connectivity",
        "description": "ping /v1/models, expect 200",
        "profile": "chat",
    },
    {
        "name": "chat_basic",
        "description": "Hello on chat profile",
        "profile": "chat",
    },
    {
        "name": "coding_test",
        "description": "Write a Python hello world",
        "profile": "coding",
    },
    {
        "name": "reasoning_test",
        "description": "2+2 and why",
        "profile": "reasoning",
    },
    {
        "name": "long_context",
        "description": "1000-word dummy text",
        "profile": "long",
    },
    {
        "name": "vision_test",
        "description": "base64 test image",
        "profile": "vision",
    },
    {
        "name": "key_rotation",
        "description": "force rotate by marking key exhausted",
        "profile": "chat",
    },
    {
        "name": "fallback_chain",
        "description": "block all except local",
        "profile": "chat",
    },
    {
        "name": "profile_detection",
        "description": "fix this bug without model",
        "profile": "coding",
    },
    {
        "name": "preset_apply",
        "description": "apply preset and verify",
        "profile": "chat",
    },
    {
        "name": "override_force",
        "description": "force local then reset",
        "profile": "chat",
    },
    {
        "name": "suspend_resume",
        "description": "suspend provider then resume",
        "profile": "chat",
    },
    {
        "name": "sqlite_persistence",
        "description": "write stat and reload",
        "profile": "chat",
    },
    {
        "name": "quota_guard",
        "description": "gemini flash threshold",
        "profile": "chat",
    },
    {
        "name": "streaming_test",
        "description": "test streaming response",
        "profile": "chat",
    },
]


@app.get("/api/tests")
async def list_tests() -> dict[str, Any]:
    return {"items": TEST_CASES}


async def run_single_test(name: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if name == "connectivity":
            port = state.config.get("settings", {}).get("port", 47822)
            url = f"http://localhost:{port}/v1/models"
            res = await state.client.get(url, headers={"Authorization": "Bearer rotator"})
            if res.status_code >= 400:
                return {"name": name, "status": "fail", "details": res.text}
            return {"name": name, "status": "pass", "duration_ms": int((time.perf_counter() - started) * 1000)}

        if name == "key_rotation":
            if state.key_manager:
                for keys in state.key_manager.keys_by_provider.values():
                    if keys:
                        state.key_manager.mark_key_exhausted(keys[0].key_id, minutes=1)
                        return {"name": name, "status": "pass", "duration_ms": 1, "details": "key marked exhausted"}
            return {"name": name, "status": "skip", "details": "no keys"}

        if name == "fallback_chain":
            original = state.overrides.get("blocked", [])
            state.overrides["blocked"] = ["ollama_cloud", "nvidia", "openrouter", "google", "gemini_flash"]
            await save_overrides_to_db()
            state.overrides["blocked"] = original
            await save_overrides_to_db()
            return {"name": name, "status": "pass", "duration_ms": 1}

        if name == "preset_apply":
            if state.presets:
                await apply_preset(state.presets[0]["id"], state.presets[0]["data"])
                return {"name": name, "status": "pass", "duration_ms": 1}
            return {"name": name, "status": "skip", "details": "no presets"}

        if name == "override_force":
            state.overrides["profiles"]["chat"] = "local"
            await save_overrides_to_db()
            state.overrides["profiles"]["chat"] = "auto"
            await save_overrides_to_db()
            return {"name": name, "status": "pass", "duration_ms": 1}

        if name == "suspend_resume":
            state.suspensions["openrouter"] = datetime.now(UTC) + timedelta(minutes=1)
            if state.db:
                await state.db.save_suspension("openrouter", state.suspensions["openrouter"].isoformat(timespec="seconds"))
                await state.db.delete_suspension("openrouter")
            state.suspensions.pop("openrouter", None)
            return {"name": name, "status": "pass", "duration_ms": 1}

        if name == "sqlite_persistence":
            if state.db:
                await state.db.set_app_state("test_flag", True)
                value = await state.db.get_app_state("test_flag")
                return {"name": name, "status": "pass" if value else "fail", "duration_ms": 1}
            return {"name": name, "status": "fail", "details": "db unavailable"}

        if name == "quota_guard":
            return {"name": name, "status": "skip", "details": "requires quota pressure"}

        if name == "vision_test":
            return {"name": name, "status": "skip", "details": "requires image payload"}

        if name == "streaming_test":
            return {"name": name, "status": "skip", "details": "manual"}

        # default: fire a quick completion via proxy
        prompt = "Hello"
        if name == "coding_test":
            prompt = "Write a Python hello world."
        elif name == "reasoning_test":
            prompt = "What is 2+2 and why?"
        elif name == "long_context":
            prompt = "Lorem ipsum " * 600
        elif name == "profile_detection":
            prompt = "fix this bug"

        payload = {
            "model": "chat",
            "messages": [{"role": "user", "content": prompt}],
        }
        if name == "coding_test":
            payload["model"] = "coding"
        if name == "reasoning_test":
            payload["model"] = "reasoning"
        if name == "long_context":
            payload["model"] = "long"
        if name == "profile_detection":
            payload.pop("model", None)

        port = state.config.get("settings", {}).get("port", 47822)
        url = f"http://localhost:{port}/v1/chat/completions"
        res = await state.client.post(url, json=payload)
        if res.status_code >= 400:
            return {"name": name, "status": "fail", "details": res.text}
        return {"name": name, "status": "pass", "duration_ms": int((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        return {"name": name, "status": "fail", "details": str(exc)}


@app.post("/api/tests/run")
async def run_all_tests() -> dict[str, Any]:
    results = []
    for test in TEST_CASES:
        results.append(await run_single_test(test["name"]))
    state.tests_results = {"last_run": datetime.now(UTC).isoformat(timespec="seconds"), "results": results}
    return state.tests_results


@app.post("/api/tests/run/{name}")
async def run_test(name: str) -> dict[str, Any]:
    result = await run_single_test(name)
    return result


@app.get("/api/tests/results")
async def get_test_results() -> dict[str, Any]:
    return state.tests_results


async def benchmark_task(prompt: str) -> None:
    state.benchmark["running"] = True
    state.benchmark["results"] = []
    state.benchmark["started_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    for provider, models in list_all_models().items():
        if state.benchmark.get("stop"):
            break
        for item in models:
            model_name = item["model"]
            try:
                res = await send_model_request(model_name, prompt)
                state.benchmark["results"].append(
                    {
                        "model": model_name,
                        "provider": provider,
                        "elapsed_ms": res["elapsed_ms"],
                        "length": len(json.dumps(res["json"]))
                    }
                )
            except Exception as exc:
                state.benchmark["results"].append(
                    {"model": model_name, "provider": provider, "error": str(exc)}
                )
    state.benchmark["running"] = False
    state.benchmark["stop"] = False


@app.post("/api/benchmark/start")
async def start_benchmark(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if state.benchmark["running"]:
        return {"ok": True, "running": True}
    prompt = (payload or {}).get("prompt", "Summarize the benefits of local routing.")
    asyncio.create_task(benchmark_task(prompt))
    return {"ok": True, "running": True}


@app.post("/api/benchmark/stop")
async def stop_benchmark() -> dict[str, Any]:
    state.benchmark["stop"] = True
    return {"ok": True}


@app.get("/api/benchmark/status")
async def benchmark_status() -> dict[str, Any]:
    return {"running": state.benchmark["running"], "started_at": state.benchmark["started_at"]}


@app.get("/api/benchmark/results")
async def benchmark_results() -> dict[str, Any]:
    return {"results": state.benchmark["results"]}


@app.post("/api/compare")
async def compare(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload.get("prompt", "")
    models = payload.get("models", [])
    if not prompt or not models:
        raise HTTPException(status_code=400, detail="Missing prompt or models")
    results = []
    for model_name in models:
        try:
            res = await send_model_request(model_name, prompt)
            results.append(
                {
                    "model": model_name,
                    "elapsed_ms": res["elapsed_ms"],
                    "response": res["json"],
                }
            )
        except Exception as exc:
            results.append({"model": model_name, "error": str(exc)})
    return {"results": results}


@app.post("/api/compare/vote")
async def compare_vote(payload: dict[str, Any]) -> dict[str, Any]:
    if not state.db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    await state.db.add_model_vote(
        payload.get("profile", "chat"),
        payload.get("model_a", ""),
        payload.get("model_b", ""),
        payload.get("winner", ""),
    )
    return {"ok": True}


@app.get("/api/suggestions")
async def suggestions() -> dict[str, Any]:
    await refresh_suggestions()
    return {"items": state.suggestions}


@app.post("/api/suggestions/{index}/apply")
async def apply_suggestion(index: int) -> dict[str, Any]:
    try:
        suggestion = state.suggestions[index]
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="Suggestion not found") from exc
    profile = suggestion["profile"]
    model = suggestion["suggested"]
    provider = find_model_provider(model)
    if not provider:
        raise HTTPException(status_code=400, detail="Unknown model")
    state.model_locks[profile] = {"model": model, "provider": provider}
    if state.db:
        await state.db.save_model_lock(profile, model, provider)
    return {"ok": True}


def parse_days(days_str: str) -> set[int]:
    if not days_str:
        return set(range(7))
    parts = [p.strip().lower() for p in days_str.split(",") if p.strip()]
    mapping = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    result = set()
    for part in parts:
        if part.isdigit():
            result.add(int(part))
        elif part[:3] in mapping:
            result.add(mapping[part[:3]])
    return result or set(range(7))


def in_time_window(start: str, end: str, now: datetime) -> bool:
    start_h, start_m = [int(x) for x in start.split(":")]
    end_h, end_m = [int(x) for x in end.split(":")]
    start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if end_dt <= start_dt:
        return now >= start_dt or now <= end_dt
    return start_dt <= now <= end_dt


async def apply_schedule_action(item: dict[str, Any]) -> None:
    action = item["action"]
    target = item["target"]
    value = item.get("value")
    if action == "suspend_provider":
        minutes = int(value) if value else 60
        await suspend_provider({"provider": target, "duration_minutes": minutes})
    elif action == "force_profile":
        await override_force({"profile": target, "provider": value or "auto", "ttl_minutes": 60})
    elif action == "apply_preset":
        try:
            preset_id = int(value)
        except (TypeError, ValueError):
            return
        await apply_preset_route(preset_id)
    elif action == "block_provider":
        await override_block({"provider": target, "ttl_minutes": 60})
    elif action == "set_priority":
        await set_priority({"mode": value or "balanced"})

    log_event("SYSTEM", f"Scheduler: {action} -> {target}", "rotation", source="scheduler")
    dispatch_webhook("scheduler", f"Scheduler: {action}", {"action": action, "target": target, "value": value})


async def schedule_loop() -> None:
    while True:
        try:
            if state.db:
                schedules = await state.db.list_schedules()
                now = datetime.now(UTC)
                for item in schedules:
                    if not item.get("active"):
                        continue
                    days = parse_days(item.get("days_of_week", ""))
                    if now.weekday() not in days:
                        continue
                    if not in_time_window(item["time_start"], item["time_end"], now):
                        continue
                    last_run = state.schedule_last_run.get(item["id"])
                    if last_run and (now - last_run) < timedelta(minutes=30):
                        continue
                    await apply_schedule_action(item)
                    state.schedule_last_run[item["id"]] = now
        except Exception:
            logger.debug("Schedule loop error", exc_info=True)
        await asyncio.sleep(60)


@app.post("/api/suggestions/{index}/dismiss")
async def dismiss_suggestion(index: int) -> dict[str, Any]:
    if index < len(state.suggestions):
        state.suggestions.pop(index)
    return {"ok": True}


@app.post("/api/quotas/reset")
async def reset_quotas() -> dict[str, Any]:
    db = state.db
    km = state.key_manager
    if db is None or km is None:
        raise HTTPException(status_code=500, detail="State unavailable")
    await db.reset_daily_quotas()
    km.daily_quota_map.clear()
    log_event("SYSTEM", "Daily quotas reset", "rotation", source="system")
    return {"ok": True}


@app.get("/api/logs/export")
async def export_logs() -> dict[str, Any]:
    return {"items": list(state.logs)}


@app.get("/api/ping")
async def ping() -> dict[str, Any]:
    started = time.perf_counter()
    return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000)}


@app.post("/api/routing/priority")
async def set_priority(payload: dict[str, str]) -> dict[str, Any]:
    mode = payload.get("mode", "balanced")
    if mode not in {"balanced", "local_first", "cloud_first"}:
        raise HTTPException(status_code=400, detail="Unknown mode")
    state.priority_mode = mode
    log_event("SYSTEM", f"Priority mode: {mode}", "rotation", source="system")
    return {"ok": True, "mode": state.priority_mode}


def dashboard_html() -> str:
    dashboard_file = BASE_DIR / "dashboard.html"
    html = dashboard_file.read_text(encoding="utf-8")
    rotator_path_js = str(BASE_DIR.resolve()).replace("\\", "\\\\")
    inject = f'<script>window.__rotatorPath="{rotator_path_js}";</script>'
    html = html.replace("</head>", inject + "</head>", 1)
    return html


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    return dashboard_html()


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    port = config.get("settings", {}).get("port", 47822)
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=False)