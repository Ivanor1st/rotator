from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROFILES = ["coding", "reasoning", "chat", "long", "vision", "audio", "translate"]

PROFILE_KEYWORDS = {
    "coding": ["code", "fix", "bug", "function", "implement", "debug", "script", "class"],
    "reasoning": ["explain", "why", "analyze", "compare", "reason", "think", "solve", "math", "proof"],
    "long": ["document", "file", "entire", "full"],
    "audio": ["transcribe", "speech", "audio"],
    "translate": ["translate", "translation"],
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


ROUTING_CHAINS: dict[str, list[RouteTarget]] = {
    "coding": [
        RouteTarget("ollama_cloud", "minimax-m2.5:cloud", "shared"),
        RouteTarget("nvidia", "minimaxai/minimax-m2.1", "35/40 rpm"),
        RouteTarget("ollama_cloud", "qwen3-coder-next:cloud", "shared"),
        RouteTarget("nvidia", "qwen/qwen3-coder-480b-a35b-instruct", "35/40 rpm"),
        RouteTarget("nvidia", "mistralai/devstral-2-123b-instruct-2512", "35/40 rpm"),
        RouteTarget("openrouter", "stepfun/step-3.5-flash:free", "free"),
        RouteTarget("local", "qwen3-coder-next:latest", "infinite"),
    ],
    "reasoning": [
        RouteTarget("ollama_cloud", "minimax-m2.5:cloud", "shared"),
        RouteTarget("ollama_cloud", "qwen3.5:cloud", "shared"),
        RouteTarget("nvidia", "z-ai/glm5", "35/40 rpm"),
        RouteTarget("nvidia", "qwen/qwen3-next-80b-a3b-thinking", "35/40 rpm"),
        RouteTarget("nvidia", "openai/gpt-oss-120b", "35/40 rpm"),
        RouteTarget("ollama_cloud", "glm-5:cloud", "shared"),
        RouteTarget("openrouter", "openrouter/free", "free"),
    ],
    "chat": [
        RouteTarget("ollama_cloud", "minimax-m2.5:cloud", "shared"),
        RouteTarget("nvidia", "minimaxai/minimax-m2.1", "35/40 rpm"),
        RouteTarget("google", "gemma-3-27b-it", "14000/14400 day"),
        RouteTarget("openrouter", "meta-llama/llama-3.3-70b-instruct:free", "free"),
        RouteTarget("google", "gemini-2.5-flash", "18/20 day"),
        RouteTarget("local", "lfm2.5-thinking:1.2b", "infinite"),
    ],
    "long": [
        RouteTarget("nvidia", "nvidia/nemotron-3-nano-30b-a3b", "35/40 rpm"),
        RouteTarget("ollama_cloud", "kimi-k2.5:cloud", "shared"),
        RouteTarget("ollama_cloud", "qwen3.5:cloud", "shared"),
        RouteTarget("google", "gemini-2.5-flash", "18/20 day"),
        RouteTarget("openrouter", "openrouter/free", "free"),
    ],
    "vision": [
        RouteTarget("ollama_cloud", "kimi-k2.5:cloud", "shared"),
        RouteTarget("ollama_cloud", "qwen3.5:397b-cloud", "shared"),
        RouteTarget("nvidia", "moonshotai/kimi-k2.5", "35/40 rpm"),
        RouteTarget("google", "gemini-2.5-flash", "18/20 day"),
        RouteTarget("local", "glm-ocr", "infinite"),
    ],
    "audio": [
        RouteTarget("google", "gemini-2.5-flash-native-audio", "unlimited"),
    ],
    "translate": [
        RouteTarget("local", "translategemma:27b", "infinite"),
        RouteTarget("openrouter", "openrouter/free", "free"),
    ],
}

MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    "ollama_cloud": [
        {"model": "minimax-m2.5:cloud", "context": "198K", "emoji": "☁️"},
        {"model": "qwen3.5:cloud", "context": "256K", "emoji": "☁️"},
        {"model": "qwen3.5:397b-cloud", "context": "256K", "emoji": "☁️"},
        {"model": "glm-5:cloud", "context": "198K", "emoji": "☁️"},
        {"model": "qwen3-coder-next:cloud", "context": "256K", "emoji": "☁️"},
        {"model": "kimi-k2.5:cloud", "context": "256K", "emoji": "☁️"},
    ],
    "nvidia": [
        {"model": "minimaxai/minimax-m2.1", "context": "?", "emoji": "🟩"},
        {"model": "minimaxai/minimax-m2", "context": "?", "emoji": "🟩"},
        {"model": "z-ai/glm5", "context": "?", "emoji": "🟩"},
        {"model": "qwen/qwen3-coder-480b-a35b-instruct", "context": "?", "emoji": "🟩"},
        {"model": "qwen/qwen3-next-80b-a3b-thinking", "context": "?", "emoji": "🟩"},
        {"model": "moonshotai/kimi-k2.5", "context": "?", "emoji": "🟩"},
        {"model": "deepseek-ai/deepseek-v3.2", "context": "?", "emoji": "🟩"},
        {"model": "stepfun-ai/step-3-5-flash", "context": "?", "emoji": "🟩"},
        {"model": "nvidia/nemotron-3-nano-30b-a3b", "context": "1M", "emoji": "🟩"},
        {"model": "openai/gpt-oss-120b", "context": "?", "emoji": "🟩"},
        {"model": "mistralai/devstral-2-123b-instruct-2512", "context": "?", "emoji": "🟩"},
    ],
    "openrouter": [
        {"model": "openrouter/free", "context": "auto", "emoji": "🧭"},
        {"model": "stepfun/step-3.5-flash:free", "context": "256K", "emoji": "🧭"},
        {"model": "google/gemma-3-27b-it:free", "context": "131K", "emoji": "🧭"},
        {"model": "meta-llama/llama-3.3-70b-instruct:free", "context": "128K", "emoji": "🧭"},
        {"model": "nousresearch/hermes-3-405b-instruct:free", "context": "131K", "emoji": "🧭"},
    ],
    "google": [
        {"model": "gemma-3-27b-it", "context": "?", "emoji": "🟡"},
        {"model": "gemma-3-12b-it", "context": "?", "emoji": "🟡"},
        {"model": "gemini-2.5-flash", "context": "1M", "emoji": "🟡"},
        {"model": "gemini-2.5-flash-native-audio", "context": "audio", "emoji": "🟡"},
    ],
    "local": [
        {"model": "qwen3-coder-next:latest", "context": "?", "emoji": "🏠"},
        {"model": "glm-ocr", "context": "?", "emoji": "🏠"},
        {"model": "lfm2.5-thinking:1.2b", "context": "?", "emoji": "🏠"},
        {"model": "translategemma:27b", "context": "?", "emoji": "🏠"},
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