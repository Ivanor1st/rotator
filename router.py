from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants import Profile, Provider, DatabaseLoaders


# Use constants for profiles
PROFILES = Profile.all()

PROFILE_KEYWORDS = {
    Profile.CODING.value: ["code", "fix", "bug", "function", "implement", "debug", "script", "class"],
    Profile.REASONING.value: ["explain", "why", "analyze", "compare", "reason", "think", "solve", "math", "proof"],
    Profile.LONG.value: ["document", "file", "entire", "full"],
    Profile.AUDIO.value: ["transcribe", "speech", "audio"],
    Profile.TRANSLATE.value: ["translate", "translation"],
}

LANGUAGE_NAMES = {
    "english", "french", "spanish", "german", "italian", "portuguese", "russian", "chinese",
    "japanese", "korean", "arabic", "hindi", "thai", "vietnamese", "turkish", "indonesian",
}


@dataclass
class RouteTarget:
    provider: str
    model: str
    quota_hint: str


# Default routing chains (fallback when DB is not available)
ROUTING_CHAINS: dict[str, list[RouteTarget]] = {
    # Chaines verifiees le 2026-11-24 (lot 26) : chaque modele ci-dessous a repondu
    # en direct, et pour coding / reasoning / long il a aussi passe un test JSON,
    # code et appel d'outil. Ollama Cloud est retire : tous ses modeles sont soit
    # retires (410), soit payants (402 « Add usage credits ») sur ces comptes.
    # Le meme modele est garde chez deux fournisseurs (NVIDIA + OpenRouter) pour
    # qu'une panne d'un cote ne bloque pas le profil.
    Profile.CODING.value: [
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3-ultra-550b-a55b", "35/40 rpm"),
        RouteTarget(Provider.GOOGLE.value, "gemini-3-flash-preview", "free tier"),
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3-ultra-550b-a55b:free", "free"),
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3.5-super-vl-120b-a12b", "35/40 rpm"),
        RouteTarget(Provider.NVIDIA.value, "poolside/laguna-xs-2.1", "35/40 rpm"),
        # Tres bon codeur mais lent (50-75 s par reponse) : en repli seulement.
        RouteTarget(Provider.NVIDIA.value, "minimaxai/minimax-m3.1-flash", "35/40 rpm"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.REASONING.value: [
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3-ultra-550b-a55b", "35/40 rpm"),
        RouteTarget(Provider.GOOGLE.value, "gemini-3-flash-preview", "free tier"),
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3-ultra-550b-a55b:free", "free"),
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3.5-super-vl-120b-a12b", "35/40 rpm"),
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "free"),
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "35/40 rpm"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.CHAT.value: [
        RouteTarget(Provider.GOOGLE.value, "gemini-flash-lite-latest", "free tier"),
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3.5-lightning-30b-a3b", "35/40 rpm"),
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3.5-lightning:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "baidu/ernie-5.5-flash-preview:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "google/gemma-4-31b-it:free", "free"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.LONG.value: [
        # Contexte 1M pour les quatre premiers.
        RouteTarget(Provider.GOOGLE.value, "gemini-3-flash-preview", "free tier"),
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3-ultra-550b-a55b", "35/40 rpm"),
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3-ultra-550b-a55b:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3.5-super-vl:free", "free"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
    ],
    Profile.VISION.value: [
        # Teste en texte seulement le 2026-11-24 (pas avec une image).
        RouteTarget(Provider.OPENROUTER.value, "nvidia/nemotron-3.5-super-vl:free", "free"),
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3.5-super-vl-120b-a12b", "35/40 rpm"),
        RouteTarget(Provider.GOOGLE.value, "gemini-3-flash-preview", "free tier"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.AUDIO.value: [
        # Google - free tier, multimodal (audio file understanding via generateContent)
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
    ],
    Profile.TRANSLATE.value: [
        RouteTarget(Provider.NVIDIA.value, "nvidia/riva-translate-4b-instruct-v2", "35/40 rpm"),
        RouteTarget(Provider.GOOGLE.value, "gemini-flash-lite-latest", "free tier"),
        RouteTarget(Provider.OPENROUTER.value, "google/gemma-4-31b-it:free", "free"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
    ],
}


# Cache for routing chains (loaded from DB at runtime)
_routing_chains_cache: dict[str, list[RouteTarget]] | None = None


async def get_routing_chain(profile: str) -> list[RouteTarget]:
    """
    Get routing chain for a profile.
    First tries to load from database, falls back to hardcoded constants.
    """
    global _routing_chains_cache

    # Try to load from DB via DatabaseLoaders
    db_loader = DatabaseLoaders.get_db()
    if db_loader:
        try:
            db_routing = await DatabaseLoaders.get_routing_for_profile(profile)
            if db_routing:
                # Convert DB format to RouteTarget format
                return [
                    RouteTarget(
                        provider=r["provider"],
                        model=r["model"],
                        quota_hint=r.get("quota_hint", ""),
                    )
                    for r in db_routing
                ]
        except Exception:
            pass  # Fall back to hardcoded

    # Fall back to hardcoded
    return ROUTING_CHAINS.get(profile, [])


async def get_all_routing_chains() -> dict[str, list[RouteTarget]]:
    """Get all routing chains."""
    global _routing_chains_cache

    if _routing_chains_cache is not None:
        return _routing_chains_cache

    # Try to load from DB
    db_loader = DatabaseLoaders.get_db()
    if db_loader:
        try:
            db_chains = await DatabaseLoaders.load_routing_chains()
            if db_chains:
                _routing_chains_cache = {}
                for profile, chain in db_chains.items():
                    _routing_chains_cache[profile] = [
                        RouteTarget(
                            provider=r["provider"],
                            model=r["model"],
                            quota_hint=r.get("quota_hint", ""),
                        )
                        for r in chain
                    ]
                return _routing_chains_cache
        except Exception:
            pass  # Fall back to hardcoded

    # Fall back to hardcoded
    _routing_chains_cache = ROUTING_CHAINS
    return _routing_chains_cache


def invalidate_routing_cache() -> None:
    """Invalidate the routing chains cache."""
    global _routing_chains_cache
    _routing_chains_cache = None

MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    # Verifie le 2026-11-24 (lot 26). Les modeles retires (410), introuvables
    # (404) ou payants (402) ont ete enleves.
    Provider.OLLAMA_CLOUD.value: [
        # Vide : sur ces comptes, tous les modeles Ollama Cloud repondent 410
        # (retire) ou 402 (« Add usage credits »). A re-tester si des credits
        # sont ajoutes.
    ],
    Provider.NVIDIA.value: [
        {"model": "nvidia/nemotron-3-ultra-550b-a55b", "context": "1M", "emoji": "💻🧠📄"},
        {"model": "nvidia/nemotron-3.5-super-vl-120b-a12b", "context": "1M", "emoji": "💻🧠👁️"},
        {"model": "nvidia/nemotron-3.5-lightning-30b-a3b", "context": "1M", "emoji": "💬"},
        {"model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "context": "256K", "emoji": "🧠"},
        {"model": "minimaxai/minimax-m3.1-flash", "context": "200K", "emoji": "💻"},
        {"model": "poolside/laguna-xs-2.1", "context": "128K", "emoji": "💻"},
        {"model": "mistralai/mistral-large-4-1t-a52b", "context": "128K", "emoji": "💬"},
        {"model": "nvidia/riva-translate-4b-instruct-v2", "context": "4K", "emoji": "🌍"},
    ],
    Provider.OPENROUTER.value: [
        # Verified free (":free" suffix, $0 pricing)
        {"model": "nvidia/nemotron-3-ultra-550b-a55b:free", "context": "1M", "emoji": "💻🧠📄"},
        {"model": "nvidia/nemotron-3.5-super-vl:free", "context": "1M", "emoji": "🧠👁️📄"},
        {"model": "nvidia/nemotron-3.5-lightning:free", "context": "1M", "emoji": "💬"},
        {"model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "context": "256K", "emoji": "🧠"},
        {"model": "inclusionai/ling-3.2-flash:free", "context": "1M", "emoji": "📄"},
        {"model": "particle-ai/particle-1:free", "context": "1M", "emoji": "💻"},
        {"model": "baidu/ernie-5.5-flash-preview:free", "context": "1M", "emoji": "💬"},
        {"model": "recursive/flint-v1.0:free", "context": "256K", "emoji": "💻"},
        {"model": "dots-studio/dots-3-note-preview:free", "context": "512K", "emoji": "💬"},
        {"model": "google/gemma-4-31b-it:free", "context": "256K", "emoji": "💬🌍"},
        # Routeur OpenRouter : choisit lui-meme un modele gratuit (etait range a
        # tort sous NVIDIA, d'ou un 404).
        {"model": "openrouter/free", "context": "200K", "emoji": "🎲"},
    ],
    Provider.GOOGLE.value: [
        {"model": "gemini-3-flash-preview", "context": "1M", "emoji": "🟡"},
        {"model": "gemini-flash-lite-latest", "context": "1M", "emoji": "🟡"},
        {"model": "gemini-3.5-flash", "context": "1M", "emoji": "🟡"},
        {"model": "gemini-2.5-flash", "context": "1M", "emoji": "🟡"},
        {"model": "gemma-4-31b-it", "context": "128K", "emoji": "🟡"},
    ],
    Provider.LOCAL.value: [
        # Non teste le 2026-11-24 : Ollama local n'etait pas lance.
        {"model": "qwen3-coder-next:latest", "context": "?", "emoji": "🏠"},
        {"model": "glm-ocr", "context": "?", "emoji": "🏠"},
        {"model": "lfm2.5-thinking:1.2b", "context": "?", "emoji": "🏠"},
        {"model": "translategemma:27b", "context": "?", "emoji": "🏠"},
    ],
    # OpenAI / Anthropic : aucune cle configuree, donc non testables ; gardes
    # pour les alias de compatibilite (claude-*, gpt-*).
    Provider.OPENAI.value: [
        {"model": "gpt-4o", "context": "128K", "emoji": "🟢"},
        {"model": "gpt-4o-mini", "context": "128K", "emoji": "🟢"},
        {"model": "o1", "context": "200K", "emoji": "🟢"},
        {"model": "o1-mini", "context": "200K", "emoji": "🟢"},
        {"model": "gpt-4-turbo", "context": "128K", "emoji": "🟢"},
    ],
    Provider.ANTHROPIC.value: [
        {"model": "claude-sonnet-4-6", "context": "200K", "emoji": "🟣"},
        {"model": "claude-3-5-sonnet-20241022", "context": "200K", "emoji": "🟣"},
        {"model": "claude-3-5-sonnet-20240620", "context": "200K", "emoji": "🟣"},
        {"model": "claude-3-haiku", "context": "200K", "emoji": "🟣"},
        {"model": "claude-3-opus", "context": "200K", "emoji": "🟣"},
    ],
}


def list_all_models() -> dict[str, list[dict[str, str]]]:
    return MODEL_CATALOG


def find_model_provider(model_name: str) -> str | None:
    for provider, models in MODEL_CATALOG.items():
        for item in models:
            if item["model"] == model_name:
                return provider
    return None


def model_context(model_name: str) -> str:
    for models in MODEL_CATALOG.values():
        for item in models:
            if item["model"] == model_name:
                return item.get("context", "?")
    return "?"


def inject_custom_models(custom_models: list[dict[str, Any]]) -> None:
    for custom in custom_models:
        model_id = str(custom.get("id") or "").strip()
        provider = str(custom.get("provider") or "").strip()
        profile = str(custom.get("profile") or "chat").strip()
        context = str(custom.get("context") or "?").strip()

        if not model_id or not provider:
            continue

        if profile in ROUTING_CHAINS:
            # Check if it's already there to avoid duplicates on reload
            if not any(t.model == model_id and t.provider == provider for t in ROUTING_CHAINS[profile]):
                ROUTING_CHAINS[profile].append(RouteTarget(provider, model_id, "custom"))

        if provider not in MODEL_CATALOG:
            MODEL_CATALOG[provider] = []
            
        if not any(m["model"] == model_id for m in MODEL_CATALOG[provider]):
            MODEL_CATALOG[provider].append({"model": model_id, "context": context, "emoji": "✨"})


def compute_suggestion(profile: str, current_model: str, stats: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(stats) < 2:
        return None
    best = sorted(stats, key=lambda row: (row.get("error_rate", 1.0), row.get("avg_total_ms", 10**9)))[0]
    if best.get("model") and best.get("model") != current_model:
        return {
            "profile": profile,
            "current": current_model,
            "suggested": best.get("model"),
            "reason": "speed_reliability",
        }
    return None


def _text_from_messages(messages: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for message in messages[:2]:
        content = message.get("content", "")
        if isinstance(content, str):
            chunks.append(content.lower())
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")).lower())
    return " ".join(chunks)


def _has_image(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                item_type = str(item.get("type", "")).lower()
                if item_type in {"image", "image_url", "input_image"}:
                    return True
    return False


def _has_audio(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                item_type = str(item.get("type", "")).lower()
                if "audio" in item_type:
                    return True
    return False


def _likely_translation(text: str) -> bool:
    if "translate" in text or "translation" in text:
        return True
    found = [lang for lang in LANGUAGE_NAMES if lang in text]
    return len(found) >= 2


def detect_profile(payload: dict[str, Any]) -> str:
    model = str(payload.get("model", "")).strip().lower()
    if model in PROFILES:
        return model

    # Also check if model matches any profile's routing chain from database (including custom profiles)
    # This allows custom profiles like "internat" to be automatically detected
    try:
        # Try to get from cache or use fallback
        chains = _routing_chains_cache if _routing_chains_cache else ROUTING_CHAINS
        for profile_name, chain in chains.items():
            for target in chain:
                if target.model.lower() == model:
                    return profile_name
    except Exception:
        pass  # If cache not available, skip this check

    messages = payload.get("messages", []) or []
    if _has_image(messages):
        return "vision"
    if _has_audio(messages):
        return "audio"

    text = _text_from_messages(messages)
    est_tokens = len(text.split())

    if est_tokens > 50000 or any(word in text for word in PROFILE_KEYWORDS["long"]):
        return "long"
    if any(word in text for word in PROFILE_KEYWORDS["audio"]):
        return "audio"
    if _likely_translation(text):
        return "translate"
    if any(word in text for word in PROFILE_KEYWORDS["coding"]):
        return "coding"
    if any(word in text for word in PROFILE_KEYWORDS["reasoning"]):
        return "reasoning"

    # If no match found, check if there are custom profiles in database
    # Use the first custom profile found instead of defaulting to "chat"
    try:
        chains = _routing_chains_cache if _routing_chains_cache else ROUTING_CHAINS
        # Return the first profile that exists in the database (custom profiles have priority)
        for profile_name in chains.keys():
            # Return the first custom profile found
            if profile_name not in PROFILES:
                return profile_name
    except Exception:
        pass

    return "chat"


def profile_emoji(profile: str) -> str:
    return {
        "coding": "💻",
        "reasoning": "🧠",
        "chat": "💬",
        "long": "📄",
        "vision": "👁️",
        "audio": "🎵",
        "translate": "🌍",
    }.get(profile, "💬")