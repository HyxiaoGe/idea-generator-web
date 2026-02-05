"""
Quota-related Pydantic schemas.
"""

from pydantic import BaseModel, Field


class ModeQuota(BaseModel):
    """Quota status for a specific generation mode."""

    name: str = Field(..., description="Display name")
    used: int = Field(..., description="Used count today")
    limit: int = Field(..., description="Daily limit")
    remaining: int = Field(..., description="Remaining count")
    cost: int = Field(..., description="Cost in quota points per generation")


class QuotaStatusResponse(BaseModel):
    """Full quota status response."""

    is_trial_mode: bool = Field(..., description="Whether user is in trial mode")
    date: str | None = Field(None, description="Current date (UTC)")
    global_used: int = Field(default=0, description="Global quota used")
    global_limit: int = Field(default=0, description="Global quota limit")
    global_remaining: int = Field(default=0, description="Global quota remaining")
    modes: dict[str, ModeQuota] = Field(default_factory=dict, description="Per-mode quota status")
    cooldown_active: bool = Field(default=False, description="Whether cooldown is active")
    cooldown_remaining: int = Field(default=0, description="Seconds until cooldown ends")
    resets_at: str | None = Field(None, description="When quota resets (ISO timestamp)")


class QuotaCheckRequest(BaseModel):
    """Request to check if quota is available."""

    mode: str = Field(..., description="Generation mode")
    resolution: str = Field(default="1K", description="Resolution")
    count: int = Field(default=1, ge=1, le=10, description="Number of generations")


class QuotaCheckResponse(BaseModel):
    """Response for quota check."""

    can_generate: bool = Field(..., description="Whether generation is allowed")
    reason: str = Field(default="OK", description="Reason if not allowed")
    cost: int = Field(default=0, description="Total cost for the request")
    remaining_after: int = Field(default=0, description="Remaining quota after generation")


class QuotaConfigResponse(BaseModel):
    """Quota configuration response."""

    global_daily_quota: int = Field(..., description="Total daily quota pool")
    cooldown_seconds: int = Field(..., description="Cooldown between generations")
    modes: dict[str, ModeQuota] = Field(..., description="Per-mode limits and costs")
