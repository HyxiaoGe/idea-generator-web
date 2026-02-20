"""
Application configuration using Pydantic Settings.

Supports loading from environment variables and .env files.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============ Application ============
    app_name: str = "Nano Banana Lab"
    app_version: str = "2.0.0"
    debug: bool = False
    environment: str = "development"  # development, staging, production

    # ============ Server ============
    host: str = "0.0.0.0"
    port: int = 8888

    # ============ Security ============
    secret_key: str = "change-me-in-production-use-a-long-random-string"

    # ============ CORS ============
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # ============ Redis ============
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 10

    # ============ Multi-Provider Configuration ============

    # Google Gemini/Imagen (default provider)
    provider_google_enabled: bool = True
    provider_google_api_key: str | None = None
    provider_google_priority: int = 1

    # OpenAI GPT-Image/DALL-E (supports third-party proxies like OpenRouter)
    provider_openai_enabled: bool = False
    provider_openai_api_key: str | None = None
    provider_openai_base_url: str | None = None  # e.g. https://openrouter.ai/api/v1
    provider_openai_referer: str | None = (
        None  # Required by some proxies (e.g., OpenRouter HTTP-Referer)
    )
    provider_openai_priority: int = 2

    # Black Forest Labs (FLUX)
    provider_bfl_enabled: bool = False
    provider_bfl_api_key: str | None = None
    provider_bfl_priority: int = 3

    # Stability AI
    provider_stability_enabled: bool = False
    provider_stability_api_key: str | None = None
    provider_stability_priority: int = 4

    # Runway (Video)
    provider_runway_enabled: bool = False
    provider_runway_api_key: str | None = None
    provider_runway_priority: int = 1

    # Kling (Video)
    provider_kling_enabled: bool = False
    provider_kling_api_key: str | None = None
    provider_kling_secret_key: str | None = None  # Kling requires both access key and secret key
    provider_kling_priority: int = 2

    # Pika Labs (Video)
    provider_pika_enabled: bool = False
    provider_pika_api_key: str | None = None
    provider_pika_priority: int = 3

    # ============ Chinese Image Providers ============

    # Alibaba (通义万相 / Wanxiang)
    provider_alibaba_enabled: bool = False
    provider_alibaba_api_key: str | None = None  # DashScope API key
    provider_alibaba_priority: int = 10

    # Zhipu AI (智谱 / CogView)
    provider_zhipu_enabled: bool = False
    provider_zhipu_api_key: str | None = None
    provider_zhipu_priority: int = 11

    # ByteDance (即梦 / Jimeng)
    provider_bytedance_enabled: bool = False
    provider_bytedance_access_key: str | None = None  # Volcano Engine access key
    provider_bytedance_secret_key: str | None = None  # Volcano Engine secret key
    provider_bytedance_priority: int = 12

    # MiniMax
    provider_minimax_enabled: bool = False
    provider_minimax_api_key: str | None = None
    provider_minimax_group_id: str | None = None  # Optional group ID
    provider_minimax_priority: int = 13

    # ============ Provider Routing ============
    default_image_provider: str = "google"
    default_video_provider: str = "runway"
    default_routing_strategy: str = "priority"  # priority, cost, quality, speed
    enable_fallback: bool = True
    fallback_image_providers: list[str] = ["google", "openai", "bfl"]
    fallback_video_providers: list[str] = ["runway", "kling", "pika"]
    provider_timeout: int = 15  # Max seconds per provider in fallback chain

    # ============ Storage Configuration ============
    # Backend: local, minio, oss
    storage_backend: str = "local"
    storage_bucket: str = "nano-banana-images"
    storage_public_url: str | None = None  # CDN URL
    storage_local_path: str = "outputs/web"

    # MinIO Configuration
    minio_endpoint: str | None = None  # e.g., localhost:9000
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str | None = None  # Override storage_bucket for MinIO
    minio_use_ssl: bool = False

    # Alibaba Cloud OSS Configuration
    oss_endpoint: str | None = None  # e.g., oss-cn-hangzhou.aliyuncs.com
    oss_access_key: str | None = None
    oss_secret_key: str | None = None

    # ============ Auth Service ============
    auth_enabled: bool = False
    auth_service_url: str = "http://localhost:8100"
    auth_service_client_id: str | None = None  # app_xxx from auth-service

    # ============ PostgreSQL Database ============
    database_enabled: bool = False
    database_url: str | None = None  # postgresql+asyncpg://user:pass@host:port/db
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False  # Echo SQL statements (debug only)

    # ============ Logging ============
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ============ Rate Limiting ============
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60  # requests per minute
    rate_limit_window: int = 60  # seconds

    # ============ Prompt Pipeline ============
    prompthub_enabled: bool = False
    prompthub_base_url: str = "https://api.prompthub.dev"
    prompthub_api_key: str | None = None
    prompthub_project_id: str | None = None
    prompthub_cache_ttl: int = 3600  # seconds

    # OpenRouter LLM (for prompt processing)
    openrouter_api_key: str | None = None
    openrouter_model: str = "anthropic/claude-sonnet-4-5"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Pipeline defaults
    prompt_auto_translate: bool = True
    prompt_auto_enhance: bool = False
    prompt_auto_negative: bool = False

    # ============ Defaults ============
    default_language: str = "en"
    default_resolution: str = "1K"
    default_aspect_ratio: str = "16:9"
    default_safety_level: str = "moderate"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_storage_configured(self) -> bool:
        """Check if storage is properly configured."""
        backend = self.storage_backend.lower()
        if backend == "local":
            return True
        elif backend == "minio":
            return all([self.minio_endpoint, self.minio_access_key, self.minio_secret_key])
        elif backend == "oss":
            return all([self.oss_endpoint, self.oss_access_key, self.oss_secret_key])
        return False

    @property
    def is_auth_configured(self) -> bool:
        """Check if auth-service is properly configured."""
        return self.auth_enabled and bool(self.auth_service_url)

    @property
    def is_database_configured(self) -> bool:
        """Check if PostgreSQL database is properly configured."""
        return self.database_enabled and bool(self.database_url)

    @property
    def is_prompt_pipeline_configured(self) -> bool:
        """Check if prompt pipeline is properly configured."""
        return (
            self.prompthub_enabled
            and bool(self.prompthub_api_key)
            and bool(self.openrouter_api_key)
        )

    # ============ Provider Helper Methods ============

    def get_google_api_key(self) -> str | None:
        """Get Google API key."""
        return self.provider_google_api_key

    def get_enabled_image_providers(self) -> list[str]:
        """Get list of enabled image providers sorted by priority."""
        providers = []
        # Global providers
        if self.provider_google_enabled and self.get_google_api_key():
            providers.append(("google", self.provider_google_priority))
        if self.provider_openai_enabled and self.provider_openai_api_key:
            providers.append(("openai", self.provider_openai_priority))
        if self.provider_bfl_enabled and self.provider_bfl_api_key:
            providers.append(("bfl", self.provider_bfl_priority))
        if self.provider_stability_enabled and self.provider_stability_api_key:
            providers.append(("stability", self.provider_stability_priority))
        # Chinese providers
        if self.provider_alibaba_enabled and self.provider_alibaba_api_key:
            providers.append(("alibaba", self.provider_alibaba_priority))
        if self.provider_zhipu_enabled and self.provider_zhipu_api_key:
            providers.append(("zhipu", self.provider_zhipu_priority))
        if self.provider_bytedance_enabled and self.provider_bytedance_access_key:
            providers.append(("bytedance", self.provider_bytedance_priority))
        if self.provider_minimax_enabled and self.provider_minimax_api_key:
            providers.append(("minimax", self.provider_minimax_priority))

        # Sort by priority (lower = higher priority)
        providers.sort(key=lambda x: x[1])
        return [p[0] for p in providers]

    def get_enabled_video_providers(self) -> list[str]:
        """Get list of enabled video providers sorted by priority."""
        providers = []
        if self.provider_runway_enabled and self.provider_runway_api_key:
            providers.append(("runway", self.provider_runway_priority))
        if self.provider_kling_enabled and self.provider_kling_api_key:
            providers.append(("kling", self.provider_kling_priority))
        if self.provider_pika_enabled and self.provider_pika_api_key:
            providers.append(("pika", self.provider_pika_priority))

        providers.sort(key=lambda x: x[1])
        return [p[0] for p in providers]

    def get_provider_api_key(self, provider: str) -> str | None:
        """Get API key for a specific provider."""
        provider_keys = {
            # Global providers
            "google": self.get_google_api_key(),
            "openai": self.provider_openai_api_key,
            "bfl": self.provider_bfl_api_key,
            "stability": self.provider_stability_api_key,
            "runway": self.provider_runway_api_key,
            "kling": self.provider_kling_api_key,
            "pika": self.provider_pika_api_key,
            # Chinese providers
            "alibaba": self.provider_alibaba_api_key,
            "zhipu": self.provider_zhipu_api_key,
            "bytedance": self.provider_bytedance_access_key,
            "minimax": self.provider_minimax_api_key,
        }
        return provider_keys.get(provider)

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if a specific provider is enabled."""
        provider_enabled = {
            # Global providers
            "google": self.provider_google_enabled,
            "openai": self.provider_openai_enabled,
            "bfl": self.provider_bfl_enabled,
            "stability": self.provider_stability_enabled,
            "runway": self.provider_runway_enabled,
            "kling": self.provider_kling_enabled,
            "pika": self.provider_pika_enabled,
            # Chinese providers
            "alibaba": self.provider_alibaba_enabled,
            "zhipu": self.provider_zhipu_enabled,
            "bytedance": self.provider_bytedance_enabled,
            "minimax": self.provider_minimax_enabled,
        }
        return provider_enabled.get(provider, False)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
