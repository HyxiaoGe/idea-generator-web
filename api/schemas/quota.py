"""
Quota-related Pydantic schemas.
"""

from pydantic import BaseModel, Field


class QuotaStatusResponse(BaseModel):
    """Quota status response."""

    date: str | None = Field(None, description="Current date (UTC)")
    used: int = Field(default=0, description="Generations used today")
    limit: int = Field(default=0, description="Daily generation limit")
    remaining: int = Field(default=0, description="Remaining generations")
    cooldown_active: bool = Field(default=False, description="Whether cooldown is active")
    cooldown_remaining: int = Field(default=0, description="Seconds until cooldown ends")
    resets_at: str | None = Field(None, description="When quota resets (ISO timestamp)")


class QuotaCheckRequest(BaseModel):
    """Request to check if quota is available."""

    count: int = Field(default=1, ge=1, le=10, description="Number of generations")


class QuotaCheckResponse(BaseModel):
    """Response for quota check."""

    can_generate: bool = Field(..., description="Whether generation is allowed")
    reason: str = Field(default="OK", description="Reason if not allowed")
    cost: int = Field(default=0, description="How many points this will cost")
    remaining_after: int = Field(default=0, description="Remaining quota after generation")


class QuotaConfigResponse(BaseModel):
    """Quota configuration response."""

    daily_limit: int = Field(..., description="Daily generation limit per user")
    cooldown_seconds: int = Field(..., description="Cooldown between generations")
    max_batch_size: int = Field(..., description="Max images per batch")
