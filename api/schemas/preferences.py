"""
Pydantic schemas for user preferences API.

Universal preferences (language, theme, notifications) come from prefhub.
Domain-specific fields (generation defaults, provider preferences) are defined here.
"""

from datetime import datetime
from enum import StrEnum

from prefhub.schemas.preferences import BasePreferences
from pydantic import BaseModel, Field


class RoutingStrategy(StrEnum):
    """Provider routing strategies."""

    PRIORITY = "priority"
    COST = "cost"
    QUALITY = "quality"
    SPEED = "speed"
    ROUND_ROBIN = "round_robin"
    ADAPTIVE = "adaptive"


class GenerationDefaults(BaseModel):
    """Image generation specific defaults."""

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


class UserPreferences(BasePreferences):
    """
    Idea-generator preferences = universal (from prefhub) + domain-specific.

    Inherits from BasePreferences:
      - ui: UIPreferences (language, theme, timezone, hour_cycle)
      - notifications: NotificationPreferences (enabled, task_completed, task_failed, sound)
      - extra: dict
    """

    generation: GenerationDefaults = Field(default_factory=GenerationDefaults)
    providers: ProviderPreferences = Field(default_factory=ProviderPreferences)


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


# ============ Request/Response Schemas ============


class GetPreferencesResponse(BaseModel):
    """Response for GET /api/preferences."""

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


class UpdatePreferencesRequest(BaseModel):
    """Request for PUT /api/preferences."""

    preferences: UserPreferences | None = Field(
        default=None,
        description="User preferences to update",
    )
    api_settings: APISettings | None = Field(
        default=None,
        description="API settings to update",
    )


class UpdatePreferencesResponse(BaseModel):
    """Response for PUT /api/preferences."""

    success: bool = True
    preferences: UserPreferences
    api_settings: APISettings
    updated_at: datetime


class GetProviderPreferencesResponse(BaseModel):
    """Response for GET /api/preferences/providers."""

    provider_preferences: ProviderPreferences


class UpdateProviderPreferencesRequest(BaseModel):
    """Request for PUT /api/preferences/providers."""

    provider_preferences: ProviderPreferences


class UpdateProviderPreferencesResponse(BaseModel):
    """Response for PUT /api/preferences/providers."""

    success: bool = True
    provider_preferences: ProviderPreferences
    updated_at: datetime
