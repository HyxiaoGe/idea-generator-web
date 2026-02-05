"""
Pydantic schemas for user settings API.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Theme(StrEnum):
    """UI theme options."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class Language(StrEnum):
    """Supported languages."""

    EN = "en"
    ZH_CN = "zh-CN"
    ZH_TW = "zh-TW"
    JA = "ja"


class RoutingStrategy(StrEnum):
    """Provider routing strategies."""

    PRIORITY = "priority"
    COST = "cost"
    QUALITY = "quality"
    SPEED = "speed"
    ROUND_ROBIN = "round_robin"
    ADAPTIVE = "adaptive"


class UserPreferences(BaseModel):
    """User preference settings."""

    # Generation defaults
    default_aspect_ratio: str | None = Field(
        default=None,
        description="Default aspect ratio for generation (e.g., '16:9', '1:1')",
    )
    default_resolution: str | None = Field(
        default=None,
        description="Default resolution (e.g., '1K', '2K', '4K')",
    )
    default_provider: str | None = Field(
        default=None,
        description="Preferred provider (e.g., 'google', 'openai', 'flux')",
    )
    routing_strategy: RoutingStrategy | None = Field(
        default=None,
        description="Provider routing strategy",
    )

    # UI preferences
    language: Language = Field(
        default=Language.EN,
        description="UI language",
    )
    theme: Theme = Field(
        default=Theme.SYSTEM,
        description="UI theme",
    )

    # Feature toggles
    enable_notifications: bool = Field(
        default=True,
        description="Enable in-app notifications",
    )
    enable_sound: bool = Field(
        default=False,
        description="Enable sound effects",
    )


class APISettings(BaseModel):
    """API-specific settings."""

    # Webhook configuration
    webhook_url: str | None = Field(
        default=None,
        description="Webhook URL for async notifications",
    )
    webhook_secret: str | None = Field(
        default=None,
        description="Webhook secret for signature verification",
    )

    # Rate limiting preferences
    max_concurrent_requests: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent generation requests",
    )


class ProviderPreference(BaseModel):
    """Provider-specific preference."""

    provider: str = Field(..., description="Provider name")
    enabled: bool = Field(default=True, description="Whether provider is enabled")
    priority: int = Field(default=100, ge=1, description="Priority (lower = higher)")
    max_daily_usage: int | None = Field(
        default=None,
        ge=0,
        description="Maximum daily usage limit",
    )


class ProviderPreferences(BaseModel):
    """Collection of provider preferences."""

    providers: list[ProviderPreference] = Field(
        default_factory=list,
        description="Provider preferences",
    )
    fallback_enabled: bool = Field(
        default=True,
        description="Enable automatic fallback on provider failure",
    )


# ============ Request/Response Schemas ============


class GetSettingsResponse(BaseModel):
    """Response for GET /api/settings."""

    preferences: UserPreferences = Field(
        default_factory=UserPreferences,
        description="User preferences",
    )
    api_settings: APISettings = Field(
        default_factory=APISettings,
        description="API settings",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Last update timestamp",
    )


class UpdateSettingsRequest(BaseModel):
    """Request for PUT /api/settings."""

    preferences: UserPreferences | None = Field(
        default=None,
        description="User preferences to update",
    )
    api_settings: APISettings | None = Field(
        default=None,
        description="API settings to update",
    )


class UpdateSettingsResponse(BaseModel):
    """Response for PUT /api/settings."""

    success: bool = True
    preferences: UserPreferences
    api_settings: APISettings
    updated_at: datetime


class GetProviderPreferencesResponse(BaseModel):
    """Response for GET /api/settings/providers."""

    provider_preferences: ProviderPreferences


class UpdateProviderPreferencesRequest(BaseModel):
    """Request for PUT /api/settings/providers."""

    provider_preferences: ProviderPreferences


class UpdateProviderPreferencesResponse(BaseModel):
    """Response for PUT /api/settings/providers."""

    success: bool = True
    provider_preferences: ProviderPreferences
    updated_at: datetime
