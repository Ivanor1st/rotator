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
    Profile.CODING.value: [
        # Ollama Cloud - best for coding
        RouteTarget(Provider.OLLAMA_CLOUD.value, "minimax-m2.5:cloud", "shared"),
        RouteTarget(Provider.OLLAMA_CLOUD.value, "qwen3-coder-next:cloud", "shared"),
        # NVIDIA - top coding models
        RouteTarget(Provider.NVIDIA.value, "qwen/qwen3-coder-480b-a35b-instruct", "35/40 rpm"),
        RouteTarget(Provider.NVIDIA.value, "z-ai/glm5", "35/40 rpm"),
        # OpenRouter - best free coding models (Qwen3 Coder is 7/7!)
        RouteTarget(Provider.OPENROUTER.value, "qwen/qwen3-coder:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "openai/gpt-oss-120b:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "deepseek/deepseek-r1-0528:free", "free"),
        # Google
        RouteTarget(Provider.GOOGLE.value, "gemma-3-27b-it", "14000/14400 day"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.REASONING.value: [
        # Ollama Cloud - best reasoning
        RouteTarget(Provider.OLLAMA_CLOUD.value, "glm-5:cloud", "shared"),
        RouteTarget(Provider.OLLAMA_CLOUD.value, "minimax-m2.5:cloud", "shared"),
        # NVIDIA - top reasoning models
        RouteTarget(Provider.NVIDIA.value, "qwen/qwen3-next-80b-a3b-thinking", "35/40 rpm"),
        RouteTarget(Provider.NVIDIA.value, "deepseek-ai/deepseek-v3.2", "35/40 rpm"),
        RouteTarget(Provider.NVIDIA.value, "openai/gpt-oss-120b", "35/40 rpm"),
        # OpenRouter - best free reasoning models (DeepSeek R1 is 7/7!)
        RouteTarget(Provider.OPENROUTER.value, "deepseek/deepseek-r1-0528:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "qwen/qwen3-vl-235b-a22b-thinking", "free"),
        RouteTarget(Provider.OPENROUTER.value, "qwen/qwen3-next-80b-a3b-instruct:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "nousresearch/hermes-3-llama-3.1-405b:free", "free"),
        # Google
        RouteTarget(Provider.GOOGLE.value, "gemma-3-27b-it", "14000/14400 day"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.CHAT.value: [
        # Ollama Cloud - best chat models
        RouteTarget(Provider.OLLAMA_CLOUD.value, "glm-5:cloud", "shared"),
        RouteTarget(Provider.OLLAMA_CLOUD.value, "minimax-m2.5:cloud", "shared"),
        RouteTarget(Provider.OLLAMA_CLOUD.value, "qwen3.5:397b-cloud", "shared"),
        # NVIDIA
        RouteTarget(Provider.NVIDIA.value, "minimaxai/minimax-m2.1", "35/40 rpm"),
        # OpenRouter - best free chat models (Trinity is 7/7, Dolphin is 7/7!)
        RouteTarget(Provider.OPENROUTER.value, "arcee-ai/trinity-large-preview:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "google/gemma-3-27b-it:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "meta-llama/llama-3.3-70b-instruct:free", "free"),
        RouteTarget(Provider.OPENROUTER.value, "mistralai/mistral-small-3.1-24b-instruct:free", "free"),
        # Google
        RouteTarget(Provider.GOOGLE.value, "gemma-3-27b-it", "14000/14400 day"),
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.LONG.value: [
        # Ollama Cloud - best long context (ONLY models with cloud variants!)
        RouteTarget(Provider.OLLAMA_CLOUD.value, "qwen3-next:80b-cloud", "shared"),  # Has cloud variant!
        RouteTarget(Provider.OLLAMA_CLOUD.value, "qwen3.5:397b-cloud", "shared"),  # 256K context
        RouteTarget(Provider.OLLAMA_CLOUD.value, "kimi-k2.5:cloud", "shared"),  # Large context
        RouteTarget(Provider.OLLAMA_CLOUD.value, "deepseek-v3.2:cloud", "shared"),  # DeepSeek flagship
        # NVIDIA - excellent long context
        RouteTarget(Provider.NVIDIA.value, "nvidia/nemotron-3-nano-30b-a3b", "35/40 rpm"),  # 1M context!
        RouteTarget(Provider.NVIDIA.value, "deepseek-ai/deepseek-v3.2", "35/40 rpm"),  # 256K
        RouteTarget(Provider.NVIDIA.value, "meta/llama-4-maverick-17b-128e-instruct", "35/40 rpm"),
        # OpenRouter - free options
        RouteTarget(Provider.OPENROUTER.value, "qwen/qwen3-next-80b-a3b-instruct:free", "free"),  # 262K
        RouteTarget(Provider.OPENROUTER.value, "stepfun/step-3.5-flash:free", "free"),  # 256K
        # Google - best free tier
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),  # 1M!
    ],
    Profile.VISION.value: [
        # Ollama Cloud - ONLY models with cloud variants!
        RouteTarget(Provider.OLLAMA_CLOUD.value, "qwen3-vl:235b-cloud", "shared"),  # Best VLM, 235B!
        RouteTarget(Provider.OLLAMA_CLOUD.value, "kimi-k2.5:cloud", "shared"),  # Native multimodal agentic
        RouteTarget(Provider.OLLAMA_CLOUD.value, "gemma3:27b-cloud", "shared"),  # Google's flagship
        RouteTarget(Provider.OLLAMA_CLOUD.value, "qwen3.5:397b-cloud", "shared"),  # Best overall?
        RouteTarget(Provider.OLLAMA_CLOUD.value, "mistral-large-3:675b-cloud", "shared"),  # Mistral flagship
        RouteTarget(Provider.OLLAMA_CLOUD.value, "ministral-3:14b-cloud", "shared"),  # Good smaller option
        # OpenRouter - free vision (best scoring!)
        RouteTarget(Provider.OPENROUTER.value, "qwen/qwen3-vl-235b-a22b-thinking", "free"),  # 7/7 vision!
        RouteTarget(Provider.OPENROUTER.value, "qwen/qwen3-vl-30b-a3b-thinking", "free"),
        # NVIDIA
        RouteTarget(Provider.NVIDIA.value, "moonshotai/kimi-k2.5", "35/40 rpm"),
        RouteTarget(Provider.NVIDIA.value, "meta/llama-3.2-90b-vision-instruct", "35/40 rpm"),
        # Google - free option
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash", "18/20 day"),
        # LOCAL: dynamically resolved at runtime if model installed
    ],
    Profile.AUDIO.value: [
        # Google - unlimited audio
        RouteTarget(Provider.GOOGLE.value, "gemini-2.5-flash-native-audio", "unlimited"),
        # NVIDIA
        RouteTarget(Provider.NVIDIA.value, "microsoft/phi-4-multimodal-instruct", "35/40 rpm"),
    ],
    Profile.TRANSLATE.value: [
        # Ollama Cloud - translate specialist (ONLY models with cloud variants!)
        RouteTarget(Provider.OLLAMA_CLOUD.value, "glm-5:cloud", "shared"),  # Google's best!
        RouteTarget(Provider.OLLAMA_CLOUD.value, "gemma3:27b-cloud", "shared"),  # Google flagship
        RouteTarget(Provider.OLLAMA_CLOUD.value, "mistral-large-3:675b-cloud", "shared"),  # Mistral flagship
        # NVIDIA
        RouteTarget(Provider.NVIDIA.value, "nvidia/riva-translate-4b-instruct-v1.1", "35/40 rpm"),  # 12 lang
        # OpenRouter - free options
        RouteTarget(Provider.OPENROUTER.value, "google/gemma-3-27b-it:free", "free"),
        # Google
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
    Provider.OLLAMA_CLOUD.value: [
        {"model": "minimax-m2.5:cloud", "context": "198K", "emoji": "☁️"},
        {"model": "qwen3.5:397b-cloud", "context": "256K", "emoji": "☁️"},
        {"model": "qwen3.5:397b-cloud", "context": "256K", "emoji": "☁️"},
        {"model": "glm-5:cloud", "context": "198K", "emoji": "☁️"},
        {"model": "qwen3-coder-next:cloud", "context": "256K", "emoji": "☁️"},
        {"model": "kimi-k2.5:cloud", "context": "256K", "emoji": "☁️"},
    ],
    Provider.NVIDIA.value: [
        # Top tier - 7/7 in category
        {"model": "openai/gpt-oss-120b", "context": "131K", "emoji": "💻🧠💬"},
        {"model": "qwen/qwen3-235b-a22b", "context": "131K", "emoji": "🧠💻🌍"},
        {"model": "minimaxai/minimax-m2.1", "context": "200K", "emoji": "💬📄"},
        {"model": "qwen/qwen3.5-397b-a17b", "context": "32K", "emoji": "🧠💬🌍"},
        {"model": "mistralai/mistral-large-3-675b-instruct-2512", "context": "32K", "emoji": "💻"},
        {"model": "moonshotai/kimi-k2-instruct", "context": "32K", "emoji": "💻"},
        # Good tier
        {"model": "deepseek-ai/deepseek-v3.2", "context": "32K", "emoji": "💻🧠"},
        {"model": "qwen/qwen3-coder-480b-a35b-instruct", "context": "32K", "emoji": "💻"},
        {"model": "mistralai/devstral-2-123b-instruct-2512", "context": "32K", "emoji": "💻"},
        {"model": "qwen/qwen3-next-80b-a3b-thinking", "context": "32K", "emoji": "🧠"},
        {"model": "meta/llama-4-maverick-17b-128e-instruct", "context": "128K", "emoji": "💬📄👁️"},
        {"model": "meta/llama-3.2-90b-vision-instruct", "context": "128K", "emoji": "👁️"},
        {"model": "nvidia/nemotron-3-nano-30b-a3b", "context": "256K", "emoji": "📄"},
        {"model": "microsoft/phi-4-multimodal-instruct", "context": "32K", "emoji": "👁️🎵"},
        {"model": "nvidia/riva-translate-4b-instruct-v1.1", "context": "4K", "emoji": "🌍"},
    ],
    Provider.OPENROUTER.value: [
        {"model": "qwen/qwen3-vl-235b-a22b-thinking", "context": "262K", "emoji": "👁️"},
        {"model": "deepseek/deepseek-r1-0528:free", "context": "163K", "emoji": "🧠"},
        {"model": "qwen/qwen3-next-80b-a3b-instruct:free", "context": "262K", "emoji": "📄"},
        {"model": "qwen/qwen3-coder:free", "context": "262K", "emoji": "💻"},
        {"model": "meta-llama/llama-3.3-70b-instruct:free", "context": "128K", "emoji": "💬"},
        {"model": "arcee-ai/trinity-large-preview:free", "context": "131K", "emoji": "💬"},
        {"model": "mistralai/mistral-small-3.1-24b-instruct:free", "context": "128K", "emoji": "💬"},
        {"model": "google/gemma-3-27b-it:free", "context": "131K", "emoji": "🧭"},
        {"model": "nousresearch/hermes-3-llama-3.1-405b:free", "context": "131K", "emoji": "🧭"},
    ],
    Provider.GOOGLE.value: [
        {"model": "gemma-3-27b-it", "context": "?", "emoji": "🟡"},
        {"model": "gemma-3-12b-it", "context": "?", "emoji": "🟡"},
        {"model": "gemini-2.5-flash", "context": "1M", "emoji": "🟡"},
        {"model": "gemini-2.5-flash-native-audio", "context": "audio", "emoji": "🟡"},
    ],
    Provider.LOCAL.value: [
        {"model": "qwen3-coder-next:latest", "context": "?", "emoji": "🏠"},
        {"model": "glm-ocr", "context": "?", "emoji": "🏠"},
        {"model": "lfm2.5-thinking:1.2b", "context": "?", "emoji": "🏠"},
        {"model": "translategemma:27b", "context": "?", "emoji": ""},
    ],
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