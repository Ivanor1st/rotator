"""
Constants, enums and configuration defaults for API Rotator.

This module centralizes all hardcoded values to improve maintainability
and avoid code duplication across the codebase.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Any


# =============================================================================
# ENUMS
# =============================================================================

class Profile(str, Enum):
    """Routing profiles for different task types."""
    CODING = "coding"
    REASONING = "reasoning"
    CHAT = "chat"
    LONG = "long"
    VISION = "vision"
    AUDIO = "audio"
    TRANSLATE = "translate"

    @classmethod
    def all(cls) -> List[str]:
        """Return all profile names as a list."""
        return [p.value for p in cls]

    @classmethod
    def from_string(cls, value: str) -> "Profile":
        """Parse a string to Profile enum."""
        value = value.lower().strip()
        for profile in cls:
            if profile.value == value:
                return profile
        return cls.CHAT  # Default fallback


class Provider(str, Enum):
    """Supported AI providers."""
    # Free / Self-hosted
    OLLAMA_CLOUD = "ollama_cloud"
    LOCAL = "local"

    # Free tier available
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"
    GOOGLE = "google"

    # Paid providers
    OPENAI = "openai"        # ChatGPT
    ANTHROPIC = "anthropic"  # Claude

    # Custom / Other
    CUSTOM = "custom"

    @classmethod
    def all(cls) -> List[str]:
        """Return all provider names as a list."""
        return [p.value for p in cls]

    @classmethod
    def is_cloud(cls, provider: str) -> bool:
        """Check if provider is a cloud provider (requires API key)."""
        return provider in {
            cls.OLLAMA_CLOUD.value,
            cls.NVIDIA.value,
            cls.OPENROUTER.value,
            cls.GOOGLE.value,
            cls.OPENAI.value,
            cls.ANTHROPIC.value,
        }

    @classmethod
    def is_paid(cls, provider: str) -> bool:
        """Check if provider is a paid provider."""
        return provider in {
            cls.OPENAI.value,
            cls.ANTHROPIC.value,
        }

    @classmethod
    def is_free(cls, provider: str) -> bool:
        """Check if provider has free tier."""
        return provider in {
            cls.OLLAMA_CLOUD.value,
            cls.LOCAL.value,
            cls.NVIDIA.value,
            cls.OPENROUTER.value,
            cls.GOOGLE.value,
        }


class KeyStatus(str, Enum):
    """Status of an API key."""
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    ERROR = "error"
    QUOTA_EXCEEDED = "quota_exceeded"


class OverrideMode(str, Enum):
    """Override modes for routing."""
    AUTO = "auto"
    MANUAL = "manual"


# =============================================================================
# CONSTANTS
# =============================================================================

class Defaults:
    """Default configuration values."""

    # Server
    PORT: int = 47822
    DEFAULT_API_KEY: str = "rotator"
    LOGGER_NAME: str = "rotator"

    # Rate limits (requests per minute)
    RPM_LIMIT_NVIDIA: int = 35
    RPM_LIMIT_OPENROUTER: int = 5
    RPM_LIMIT_GOOGLE: int = 3

    # Security
    DEFAULT_INVALID_TOKEN_LIMIT_PER_MINUTE: int = 12
    DEFAULT_INVALID_TOKEN_WINDOW_SECONDS: int = 60
    DEFAULT_INVALID_TOKEN_BLOCK_SECONDS: int = 120

    # Database
    DEFAULT_DB_FILE: str = "rotator.db"

    # Timeouts (seconds)
    DEFAULT_REQUEST_TIMEOUT: int = 120
    CATALOGUE_REFRESH_TIMEOUT: int = 30


class ProviderEndpoints:
    """Base URLs for provider APIs."""

    # Free / Self-hosted
    NVIDIA: str = "https://integrate.api.nvidia.com/v1"
    OPENROUTER: str = "https://openrouter.ai/api/v1"
    GOOGLE: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    OLLAMA: str = "http://localhost:11434"
    OLLAMA_CLOUD: str = "https://cloud.ollama.ai"

    # Paid providers
    OPENAI: str = "https://api.openai.com/v1"
    ANTHROPIC: str = "https://api.anthropic.com"

    @classmethod
    def get(cls, provider: str) -> str:
        """Get base URL for a provider."""
        endpoints = {
            Provider.NVIDIA.value: cls.NVIDIA,
            Provider.OPENROUTER.value: cls.OPENROUTER,
            Provider.GOOGLE.value: cls.GOOGLE,
            "ollama": cls.OLLAMA,
            Provider.OLLAMA_CLOUD.value: cls.OLLAMA_CLOUD,
            Provider.OPENAI.value: cls.OPENAI,
            Provider.ANTHROPIC.value: cls.ANTHROPIC,
        }
        return endpoints.get(provider, "")


class ProviderKeyValidation:
    """Validation functions for provider API keys."""

    @staticmethod
    def google(key: str) -> bool:
        """Validate Google API key format."""
        return key.startswith("AIza") and len(key) > 30

    @staticmethod
    def nvidia(key: str) -> bool:
        """Validate NVIDIA API key format."""
        return key.startswith("nvapi-") and len(key) > 20

    @staticmethod
    def openrouter(key: str) -> bool:
        """Validate OpenRouter API key format."""
        return key.startswith("sk-or-") and len(key) > 20

    @staticmethod
    def ollama_cloud(token: str) -> bool:
        """Validate Ollama Cloud token format."""
        return len(token) > 10

    @staticmethod
    def openai(key: str) -> bool:
        """Validate OpenAI API key format."""
        return key.startswith("sk-") and len(key) > 20

    @staticmethod
    def anthropic(key: str) -> bool:
        """Validate Anthropic API key format."""
        return key.startswith("sk-ant-") and len(key) > 20

    @classmethod
    def validate(cls, provider: str, key: str) -> bool:
        """Validate key format for a provider."""
        validators = {
            Provider.GOOGLE.value: cls.google,
            Provider.NVIDIA.value: cls.nvidia,
            Provider.OPENROUTER.value: cls.openrouter,
            Provider.OLLAMA_CLOUD.value: cls.ollama_cloud,
            Provider.OPENAI.value: cls.openai,
            Provider.ANTHROPIC.value: cls.anthropic,
        }
        validator = validators.get(provider)
        if validator:
            return validator(key)
        return True  # No validation for unknown providers


class CatalogueFiles:
    """File paths for model catalogues."""

    @staticmethod
    def get_path(provider: str, base_dir: str = ".") -> str:
        """Get catalogue file path for a provider."""
        filenames = {
            "ollama": "ollama_models_cloud.json",
            Provider.OPENROUTER.value: "openrouter_models.json",
            Provider.NVIDIA.value: "nvidia_models.json",
        }
        filename = filenames.get(provider, f"{provider}_models.json")
        from pathlib import Path
        return str(Path(base_dir) / filename)


class APIEndpoints:
    """API endpoint paths."""

    # Main proxy endpoints
    V1_CHAT_COMPLETIONS = "/v1/chat/completions"
    V1_MESSAGES = "/v1/messages"
    V1_MODELS = "/v1/models"

    # Dashboard
    DASHBOARD = "/dashboard"

    # Management API
    API_CONFIG = "/api/config"
    API_CONFIG_KEYS = "/api/config/keys"
    API_CONFIG_KEYS_TEST = "/api/config/keys/test"
    API_STATUS = "/api/status"
    API_HEALTH = "/api/health"
    API_QUOTA = "/api/quota"
    API_LOGS = "/api/logs"
    API_STATS = "/api/stats"
    API_RELOAD_CONFIG = "/api/reload-config"
    API_PAUSE = "/api/pause"
    API_RESUME = "/api/resume"
    API_RESTART = "/api/restart"

    # Overrides
    API_OVERRIDE_FORCE = "/api/override/force"
    API_OVERRIDE_BLOCK = "/api/override/block"
    API_OVERRIDE_UNBLOCK = "/api/override/unblock"
    API_OVERRIDE_RESET = "/api/override/reset"

    # Locks
    API_LOCK = "/api/lock"

    # Catalogues
    API_CATALOGUE_OLLAMA = "/api/catalogue/ollama"
    API_CATALOGUE_OPENROUTER = "/api/catalogue/openrouter"
    API_CATALOGUE_NVIDIA = "/api/catalogue/nvidia"
    API_CATALOGUE_LOCAL = "/api/catalogue/local"
    API_CATALOGUE_REFRESH = "/api/catalogue/refresh"
    API_CATALOGUE_INSTALL = "/api/catalogue/install"
    API_CATALOGUE_ADD = "/api/catalogue/add-to-rotator"

    # Projects & Claude Code
    API_PROJECTS = "/api/projects"
    API_CLAUDE_ONBOARDING = "/api/projects/claude-onboarding"
    API_CLAUDE_MEMORY = "/api/claude-code/memory"

    # OpenClaw
    API_OPENCLAW_STATUS = "/api/openclaw/status"
    API_OPENCLAW_CONFIG = "/api/openclaw/config"
    API_OPENCLAW_INSTALL = "/api/openclaw/install"
    API_OPENCLAW_CONFIGURE = "/api/openclaw/configure-rotator"
    API_OPENCLAW_GATEWAY_START = "/api/openclaw/gateway/start"
    API_OPENCLAW_GATEWAY_STOP = "/api/openclaw/gateway/stop"

    # Maintenance
    API_MAINTENANCE_BACKUPS = "/api/maintenance/backups"
    API_MAINTENANCE_BACKUP = "/api/maintenance/backup"
    API_MAINTENANCE_RESTORE = "/api/maintenance/restore"
    API_MAINTENANCE_RESET = "/api/maintenance/reset-all"

    # Security
    API_SECURITY_STATUS = "/api/security/status"

    # Tests & Benchmark
    API_TESTS_RUN = "/api/tests/run"
    API_BENCHMARK_START = "/api/benchmark/start"
    API_COMPARE = "/api/compare"


class ErrorMessages:
    """Standardized error messages."""

    # General
    INTERNAL_ERROR = "Internal server error"
    NOT_FOUND = "Resource not found"
    UNAUTHORIZED = "Unauthorized"
    FORBIDDEN = "Forbidden"

    # Configuration
    CONFIG_NOT_FOUND = "Configuration not found"
    INVALID_CONFIG = "Invalid configuration format"

    # Keys
    KEY_NOT_FOUND = "API key not found"
    KEY_INVALID_FORMAT = "Invalid API key format"
    KEY_TEST_FAILED = "Failed to validate API key"

    # Providers
    PROVIDER_NOT_FOUND = "Provider not found"
    PROVIDER_NOT_SUPPORTED = "Provider not supported"
    PROVIDER_BLOCKED = "Provider is blocked"
    PROVIDER_SUSPENDED = "Provider is temporarily suspended"
    PROVIDER_NO_KEYS = "No valid API keys available for provider"

    # Quota
    QUOTA_EXCEEDED = "Provider quota exceeded"
    QUOTA_NOT_FOUND = "Quota information not found"

    # Routing
    ROUTING_FAILED = "Failed to route request"
    NO_PROVIDER_AVAILABLE = "No provider available for this profile"

    # Catalogue
    CATALOGUE_NOT_FOUND = "Model catalogue not found"
    CATALOGUE_REFRESH_FAILED = "Failed to refresh model catalogue"
    MODEL_NOT_FOUND = "Model not found in catalogue"

    # Projects
    PROJECT_NOT_FOUND = "Project not found"
    PROJECT_TOKEN_INVALID = "Invalid project token"

    # OpenClaw
    OPENCLAW_NOT_INSTALLED = "OpenClaw is not installed"
    OPENCLAW_NOT_CONFIGURED = "OpenClaw is not configured"


class SuccessMessages:
    """Standardized success messages."""

    CONFIG_RELOADED = "Configuration reloaded successfully"
    KEY_ADDED = "API key added successfully"
    KEY_REMOVED = "API key removed successfully"
    KEY_TESTED = "API key validated successfully"
    PROVIDER_BLOCKED = "Provider blocked successfully"
    PROVIDER_UNBLOCKED = "Provider unblocked successfully"
    PROVIDER_SUSPENDED = "Provider suspended successfully"
    PROVIDER_RESUMED = "Provider resumed successfully"
    OVERRIDE_APPLIED = "Override applied successfully"
    OVERRIDE_RESET = "Overrides reset successfully"
    BACKUP_CREATED = "Backup created successfully"
    BACKUP_RESTORED = "Backup restored successfully"
    CATALOGUE_REFRESHED = "Model catalogue refreshed successfully"


# =============================================================================
# CONFIGURATION SCHEMA
# =============================================================================

@dataclass
class ConfigSchema:
    """Expected configuration structure."""

    @dataclass
    class Keys:
        """Keys configuration."""
        ollama_cloud: List[Dict[str, str]] = field(default_factory=list)
        nvidia: List[Dict[str, str]] = field(default_factory=list)
        openrouter: List[Dict[str, str]] = field(default_factory=list)
        google: List[Dict[str, str]] = field(default_factory=list)
        custom: List[Dict[str, str]] = field(default_factory=list)

    @dataclass
    class Settings:
        """Settings configuration."""
        port: int = Defaults.PORT
        db_file: str = Defaults.DEFAULT_DB_FILE
        expose_network: bool = False
        dashboard_password: str = ""
        require_auth_header: bool = False
        auth_bruteforce_protection: bool = True
        invalid_token_limit_per_minute: int = Defaults.DEFAULT_INVALID_TOKEN_LIMIT_PER_MINUTE
        invalid_token_window_seconds: int = Defaults.DEFAULT_INVALID_TOKEN_WINDOW_SECONDS
        invalid_token_block_seconds: int = Defaults.DEFAULT_INVALID_TOKEN_BLOCK_SECONDS
        notify_on_rotation: bool = True
        dashboard_language: str = "fr"

        @dataclass
        class Backups:
            auto_backup_on_shutdown: bool = True
            auto_restore_latest_on_startup: bool = True

        backups: Backups = field(default_factory=Backups)

    @dataclass
    class Webhooks:
        """Webhook configuration."""
        discord: str = ""
        slack: str = ""
        telegram_token: str = ""
        telegram_chat_id: str = ""

    @dataclass
    class Overrides:
        """Overrides configuration."""
        coding: str = "auto"
        reasoning: str = "auto"
        chat: str = "auto"
        long: str = "auto"
        vision: str = "auto"
        audio: str = "auto"
        translate: str = "auto"
        blocked: List[str] = field(default_factory=list)

    keys: Keys = field(default_factory=Keys)
    settings: Settings = field(default_factory=Settings)
    webhooks: Webhooks = field(default_factory=Webhooks)
    overrides: Overrides = field(default_factory=Overrides)


# =============================================================================
# RATE LIMIT DEFAULTS
# =============================================================================

class RateLimits:
    """Default rate limits for providers."""

    # RPM (requests per minute)
    RPM: Dict[str, int] = {
        Provider.NVIDIA.value: Defaults.RPM_LIMIT_NVIDIA,
        Provider.OPENROUTER.value: Defaults.RPM_LIMIT_OPENROUTER,
        Provider.GOOGLE.value: Defaults.RPM_LIMIT_GOOGLE,
    }

    # Daily limits (requests per day) - provider: {model: limit}
    DAILY: Dict[str, Dict[str, int]] = {}

    @classmethod
    def get_rpm(cls, provider: str) -> int:
        """Get RPM limit for a provider."""
        return cls.RPM.get(provider, 60)  # Default 60 RPM

    @classmethod
    def get_daily(cls, provider: str, model: str) -> int:
        """Get daily limit for a provider/model combination."""
        if provider in cls.DAILY and model in cls.DAILY[provider]:
            return cls.DAILY[provider][model]
        return 0  # No limit


# =============================================================================
# PROVIDER DISPLAY NAMES
# =============================================================================

class ProviderDisplayNames:
    """Human-readable names for providers."""

    NAMES: Dict[str, str] = {
        Provider.OLLAMA_CLOUD.value: "Ollama Cloud",
        Provider.NVIDIA.value: "NVIDIA NIM",
        Provider.OPENROUTER.value: "OpenRouter",
        Provider.GOOGLE.value: "Google AI",
        Provider.LOCAL.value: "Local (Ollama)",
        Provider.CUSTOM.value: "Custom",
    }

    @classmethod
    def get(cls, provider: str) -> str:
        """Get display name for a provider."""
        return cls.NAMES.get(provider, provider.title())


class ProfileDisplayNames:
    """Human-readable names for profiles."""

    NAMES: Dict[str, str] = {
        Profile.CODING.value: "Coding",
        Profile.REASONING.value: "Reasoning",
        Profile.CHAT.value: "Chat",
        Profile.LONG.value: "Long Context",
        Profile.VISION.value: "Vision",
        Profile.AUDIO.value: "Audio",
        Profile.TRANSLATE.value: "Translation",
    }

    EMOJIS: Dict[str, str] = {
        Profile.CODING.value: "💻",
        Profile.REASONING.value: "🧠",
        Profile.CHAT.value: "💬",
        Profile.LONG.value: "📄",
        Profile.VISION.value: "👁️",
        Profile.AUDIO.value: "🎵",
        Profile.TRANSLATE.value: "🌍",
    }

    @classmethod
    def get_name(cls, profile: str) -> str:
        """Get display name for a profile."""
        return cls.NAMES.get(profile, profile.title())

    @classmethod
    def get_emoji(cls, profile: str) -> str:
        """Get emoji for a profile."""
        return cls.EMOJIS.get(profile, "📌")


# =============================================================================
# DATABASE LOADERS - Functions to load data from DB at runtime
# =============================================================================

class DatabaseLoaders:
    """Loaders for reading data from database at runtime."""

    _db_instance = None

    @classmethod
    def set_db(cls, db_instance: "RotatorDB") -> None:
        """Set the database instance to use for loading data."""
        cls._db_instance = db_instance

    @classmethod
    def get_db(cls) -> "RotatorDB | None":
        """Get the database instance."""
        return cls._db_instance

    @classmethod
    async def load_providers(cls) -> dict[str, dict[str, Any]]:
        """Load providers from database."""
        if not cls._db_instance:
            return {}

        providers = await cls._db_instance.list_providers(active_only=False)
        return {p["name"]: p for p in providers}

    @classmethod
    async def load_profiles(cls) -> list[str]:
        """Load profiles from database."""
        if not cls._db_instance:
            return Profile.all()

        profiles = await cls._db_instance.list_profiles(active_only=False)
        return [p["name"] for p in profiles]

    @classmethod
    async def load_routing_chains(cls) -> dict[str, list[dict[str, Any]]]:
        """Load routing chains from database."""
        if not cls._db_instance:
            return {}

        profiles = await cls._db_instance.list_profiles(active_only=False)
        routing_chains = {}

        for profile in profiles:
            chain = await cls._db_instance.get_profile_routing_chain(profile["name"])
            if chain:
                routing_chains[profile["name"]] = chain

        return routing_chains

    @classmethod
    async def get_routing_for_profile(cls, profile: str) -> list[dict[str, Any]]:
        """Get routing chain for a specific profile."""
        if not cls._db_instance:
            # Fallback to hardcoded
            from router import ROUTING_CHAINS
            return [
                {"provider": t.provider, "model": t.model, "quota_hint": t.quota_hint}
                for t in ROUTING_CHAINS.get(profile, [])
            ]

        return await cls._db_instance.get_profile_routing_chain(profile)
