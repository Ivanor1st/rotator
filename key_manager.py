from __future__ import annotations

import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from constants import Provider, Defaults, RateLimits
from router import RouteTarget


@dataclass
class KeyRecord:
    key_id: str
    value: str
    label: str
    provider: str


class KeyManager:
    def __init__(self, config: dict, daily_quota_map: dict[str, int]) -> None:
        self.config = config
        self.daily_quota_map = daily_quota_map

        def resolve_secret(value: str) -> str:
            raw = str(value or "").strip()
            if not raw:
                return ""
            if raw.startswith("env:"):
                return str(os.environ.get(raw[4:].strip(), "")).strip()
            if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
                return str(os.environ.get(raw[2:-1].strip(), "")).strip()
            return raw

        # Use constants for rotation and rate limits
        self.rotate_after_errors = {
            Provider.NVIDIA.value: 3,
            Provider.OLLAMA_CLOUD.value: 3,
            Provider.OPENROUTER.value: 5,
            Provider.GOOGLE.value: 3,
        }
        self.rpm_limits = {Provider.NVIDIA.value: RateLimits.RPM.get(Provider.NVIDIA.value)}
        self.daily_limits = {
            "gemma-3-27b-it": 14000,
            "gemma-3-12b-it": 14000,
            "gemini-2.5-flash": 18,
        }
        self.cooldown = timedelta(hours=1)

        # Use constants for provider names
        self.keys_by_provider: dict[str, list[KeyRecord]] = {
            Provider.OLLAMA_CLOUD.value: [
                KeyRecord(
                    f"{Provider.OLLAMA_CLOUD.value}:{idx+1}",
                    resolve_secret(item.get("token", "")),
                    item.get("label", f"Ollama {idx+1}"),
                    Provider.OLLAMA_CLOUD.value,
                )
                for idx, item in enumerate(config.get("keys", {}).get(Provider.OLLAMA_CLOUD.value, []))
                if resolve_secret(item.get("token", ""))
            ],
            Provider.NVIDIA.value: [
                KeyRecord(
                    f"{Provider.NVIDIA.value}:{idx+1}",
                    resolve_secret(item.get("key", "")),
                    item.get("label", f"NVIDIA {idx+1}"),
                    Provider.NVIDIA.value,
                )
                for idx, item in enumerate(config.get("keys", {}).get(Provider.NVIDIA.value, []))
                if resolve_secret(item.get("key", ""))
            ],
            Provider.OPENROUTER.value: [
                KeyRecord(
                    f"{Provider.OPENROUTER.value}:{idx+1}",
                    resolve_secret(item.get("key", "")),
                    item.get("label", "OpenRouter"),
                    Provider.OPENROUTER.value,
                )
                for idx, item in enumerate(config.get("keys", {}).get(Provider.OPENROUTER.value, []))
                if resolve_secret(item.get("key", ""))
            ],
            Provider.GOOGLE.value: [
                KeyRecord(
                    f"{Provider.GOOGLE.value}:{idx+1}",
                    resolve_secret(item.get("key", "")),
                    item.get("label", f"Google {idx+1}"),
                    Provider.GOOGLE.value,
                )
                for idx, item in enumerate(config.get("keys", {}).get(Provider.GOOGLE.value, []))
                if resolve_secret(item.get("key", ""))
            ],
            Provider.OPENAI.value: [
                KeyRecord(
                    f"{Provider.OPENAI.value}:{idx+1}",
                    resolve_secret(item.get("key", "")),
                    item.get("label", f"OpenAI {idx+1}"),
                    Provider.OPENAI.value,
                )
                for idx, item in enumerate(config.get("keys", {}).get(Provider.OPENAI.value, []))
                if resolve_secret(item.get("key", ""))
            ],
            Provider.ANTHROPIC.value: [
                KeyRecord(
                    f"{Provider.ANTHROPIC.value}:{idx+1}",
                    resolve_secret(item.get("key", "")),
                    item.get("label", f"Anthropic {idx+1}"),
                    Provider.ANTHROPIC.value,
                )
                for idx, item in enumerate(config.get("keys", {}).get(Provider.ANTHROPIC.value, []))
                if resolve_secret(item.get("key", ""))
            ],
            Provider.LOCAL.value: [KeyRecord(f"{Provider.LOCAL.value}:0", "", "Local Ollama", Provider.LOCAL.value)],
        }

        self.consecutive_errors: dict[str, int] = defaultdict(int)
        self.exhausted_until: dict[str, datetime] = {}
        self.rpm_windows: dict[str, deque[datetime]] = defaultdict(deque)
        self.blocked_keys: set[str] = set()
        self.suspended_providers: set[str] = set()

    def _is_cooldown_over(self, key_id: str) -> bool:
        until = self.exhausted_until.get(key_id)
        if until is None:
            return True
        if datetime.now(UTC) >= until:
            self.exhausted_until.pop(key_id, None)
            self.consecutive_errors[key_id] = 0
            return True
        return False

    def _daily_quota_used(self, provider: str, model: str, key_id: str) -> int:
        return self.daily_quota_map.get(f"{provider}:{model}:{key_id}", 0)

    def _rpm_count(self, key_id: str) -> int:
        window = self.rpm_windows[key_id]
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=1)
        while window and window[0] < cutoff:
            window.popleft()
        return len(window)

    def _is_key_eligible(self, key: KeyRecord, model: str) -> bool:
        if key.key_id in self.blocked_keys:
            return False
        if not self._is_cooldown_over(key.key_id):
            return False

        if key.provider in self.rpm_limits and self._rpm_count(key.key_id) >= self.rpm_limits[key.provider]:
            self.exhausted_until[key.key_id] = datetime.now(UTC) + self.cooldown
            return False

        daily_limit = self.daily_limits.get(model)
        if daily_limit is not None:
            used = self._daily_quota_used(key.provider, model, key.key_id)
            if used >= daily_limit:
                self.exhausted_until[key.key_id] = datetime.now(UTC) + self.cooldown
                return False

        return True

    def choose_key_for_target(self, target: RouteTarget) -> KeyRecord | None:
        if target.provider in self.suspended_providers:
            return None
        keys = self.keys_by_provider.get(target.provider, [])
        if not keys:
            return None

        eligible = [key for key in keys if self._is_key_eligible(key, target.model)]
        if not eligible:
            return None

        def score(item: KeyRecord) -> tuple[int, int, int]:
            errs = self.consecutive_errors.get(item.key_id, 0)
            rpm = self._rpm_count(item.key_id)
            used = self._daily_quota_used(item.provider, target.model, item.key_id)
            return (errs, rpm, used)

        return sorted(eligible, key=score)[0]

    def choose_keys_for_target(self, target: RouteTarget) -> list[KeyRecord]:
        """Return all eligible keys for a given target, ordered by score (low rpm, low daily usage first).

        This allows callers to try multiple keys for the same provider/model before
        moving on to the next provider.
        """
        if target.provider in self.suspended_providers:
            return []
        keys = self.keys_by_provider.get(target.provider, [])
        if not keys:
            return []

        eligible = [key for key in keys if self._is_key_eligible(key, target.model)]
        if not eligible:
            return []

        def score(item: KeyRecord) -> tuple[int, int]:
            rpm = self._rpm_count(item.key_id)
            used = self._daily_quota_used(item.provider, target.model, item.key_id)
            return (rpm, used)

        return sorted(eligible, key=score)

    def block_key(self, key_id: str) -> None:
        self.blocked_keys.add(key_id)

    def unblock_key(self, key_id: str) -> None:
        self.blocked_keys.discard(key_id)

    def suspend_provider(self, provider: str) -> None:
        self.suspended_providers.add(provider)

    def resume_provider(self, provider: str) -> None:
        self.suspended_providers.discard(provider)

    def mark_key_exhausted(self, key_id: str, minutes: int = 60) -> None:
        self.exhausted_until[key_id] = datetime.now(UTC) + timedelta(minutes=minutes)

    def find_key_by_label(self, label: str) -> KeyRecord | None:
        needle = label.lower()
        for keys in self.keys_by_provider.values():
            for key in keys:
                if key.label.lower() == needle or key.key_id.lower() == needle:
                    return key
        return None

    def mark_result(
        self,
        provider: str,
        model: str,
        key_id: str,
        success: bool,
    ) -> dict[str, str | bool]:
        if provider in self.rpm_limits:
            self.rpm_windows[key_id].append(datetime.now(UTC))

        if provider == Provider.GOOGLE.value or model in self.daily_limits:
            quota_key = f"{provider}:{model}:{key_id}"
            self.daily_quota_map[quota_key] = self.daily_quota_map.get(quota_key, 0) + 1

        action = {"rotated": False, "reason": ""}
        if success:
            self.consecutive_errors[key_id] = 0
            return action

        self.consecutive_errors[key_id] += 1
        threshold = self.rotate_after_errors.get(provider, 3)
        if self.consecutive_errors[key_id] >= threshold:
            self.exhausted_until[key_id] = datetime.now(UTC) + self.cooldown
            self.consecutive_errors[key_id] = 0
            action = {"rotated": True, "reason": f"{provider} key error threshold reached"}
        return action

    def get_provider_status(self) -> dict[str, dict]:
        now = datetime.now(UTC)
        result: dict[str, dict] = {}
        for provider, keys in self.keys_by_provider.items():
            key_rows = []
            for key in keys:
                cooldown_until = self.exhausted_until.get(key.key_id)
                if cooldown_until and cooldown_until > now:
                    state = "red"
                elif self.consecutive_errors.get(key.key_id, 0) > 0:
                    state = "orange"
                else:
                    state = "green"

                key_rows.append(
                    {
                        "key_id": key.key_id,
                        "label": key.label,
                        "state": state,
                        "rpm": self._rpm_count(key.key_id),
                    }
                )
            result[provider] = {"provider": provider, "keys": key_rows}
        return result