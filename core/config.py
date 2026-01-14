"""
Application configuration using Pydantic Settings.

Supports loading from environment variables and .env files.
"""

from functools import lru_cache
from typing import Optional, List
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
    port: int = 8000

    # ============ Security ============
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # ============ CORS ============
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]

    # ============ Redis ============
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 10

    # ============ Google Gemini API ============
    google_api_key: Optional[str] = None

    # ============ Cloudflare R2 Storage ============
    r2_enabled: bool = True
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_name: str = "nano-banana-images"
    r2_public_url: Optional[str] = None

    # ============ GitHub OAuth ============
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    github_redirect_uri: Optional[str] = None
    auth_enabled: bool = False

    # ============ Trial Mode ============
    trial_enabled: bool = False
    trial_global_quota: int = 50
    trial_quota_mode: str = "manual"  # auto or manual
    trial_cooldown_seconds: int = 3

    # Trial quota limits (manual mode)
    trial_basic_1k_limit: int = 30
    trial_basic_4k_limit: int = 10
    trial_chat_limit: int = 20
    trial_batch_1k_limit: int = 15
    trial_batch_4k_limit: int = 5
    trial_search_limit: int = 15
    trial_blend_limit: int = 10

    # ============ Logging ============
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ============ Rate Limiting ============
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60  # requests per minute
    rate_limit_window: int = 60  # seconds

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
    def is_r2_configured(self) -> bool:
        """Check if R2 storage is properly configured."""
        return all([
            self.r2_enabled,
            self.r2_account_id,
            self.r2_access_key_id,
            self.r2_secret_access_key,
        ])

    @property
    def is_auth_configured(self) -> bool:
        """Check if GitHub OAuth is properly configured."""
        return all([
            self.auth_enabled,
            self.github_client_id,
            self.github_client_secret,
        ])


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
