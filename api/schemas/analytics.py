"""
Pydantic schemas for analytics API.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TimeRange(StrEnum):
    """Time range options for analytics."""

    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ALL = "all"


class DailyUsage(BaseModel):
    """Daily usage statistics."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    count: int = Field(..., description="Number of generations")
    credits: float = Field(default=0.0, description="Credits consumed")


class ProviderUsage(BaseModel):
    """Provider-specific usage statistics."""

    provider: str = Field(..., description="Provider name")
    count: int = Field(..., description="Number of generations")
    percentage: float = Field(..., description="Percentage of total")
    average_duration_ms: float = Field(
        default=0.0,
        description="Average generation time in milliseconds",
    )
    success_rate: float = Field(
        default=100.0,
        description="Success rate percentage",
    )


class ModeUsage(BaseModel):
    """Mode-specific usage statistics."""

    mode: str = Field(..., description="Generation mode")
    count: int = Field(..., description="Number of generations")
    percentage: float = Field(..., description="Percentage of total")


class ResolutionUsage(BaseModel):
    """Resolution-specific usage statistics."""

    resolution: str = Field(..., description="Resolution")
    count: int = Field(..., description="Number of generations")
    percentage: float = Field(..., description="Percentage of total")


class CostBreakdown(BaseModel):
    """Cost breakdown by category."""

    category: str = Field(..., description="Cost category")
    amount: float = Field(..., description="Amount spent")
    percentage: float = Field(..., description="Percentage of total")


# ============ Response Schemas ============


class OverviewResponse(BaseModel):
    """Response for GET /api/analytics/overview."""

    total_generations: int = Field(..., description="Total number of generations")
    total_credits_used: float = Field(
        default=0.0,
        description="Total credits consumed",
    )
    average_duration_ms: float = Field(
        default=0.0,
        description="Average generation time",
    )
    success_rate: float = Field(
        default=100.0,
        description="Overall success rate",
    )
    favorite_provider: str | None = Field(
        None,
        description="Most used provider",
    )
    favorite_mode: str | None = Field(
        None,
        description="Most used generation mode",
    )
    period_start: datetime | None = Field(
        None,
        description="Start of analysis period",
    )
    period_end: datetime | None = Field(
        None,
        description="End of analysis period",
    )


class UsageResponse(BaseModel):
    """Response for GET /api/analytics/usage."""

    daily_usage: list[DailyUsage] = Field(
        default_factory=list,
        description="Daily usage statistics",
    )
    total_generations: int = Field(..., description="Total generations in period")
    average_daily: float = Field(..., description="Average daily generations")
    peak_day: str | None = Field(None, description="Day with most generations")
    peak_count: int = Field(default=0, description="Count on peak day")
    by_mode: list[ModeUsage] = Field(
        default_factory=list,
        description="Usage by generation mode",
    )
    by_resolution: list[ResolutionUsage] = Field(
        default_factory=list,
        description="Usage by resolution",
    )


class CostsResponse(BaseModel):
    """Response for GET /api/analytics/costs."""

    total_cost: float = Field(..., description="Total cost in period")
    currency: str = Field(default="credits", description="Cost unit")
    daily_costs: list[DailyUsage] = Field(
        default_factory=list,
        description="Daily cost breakdown",
    )
    by_provider: list[CostBreakdown] = Field(
        default_factory=list,
        description="Cost by provider",
    )
    by_mode: list[CostBreakdown] = Field(
        default_factory=list,
        description="Cost by generation mode",
    )
    by_resolution: list[CostBreakdown] = Field(
        default_factory=list,
        description="Cost by resolution",
    )


class ProvidersResponse(BaseModel):
    """Response for GET /api/analytics/providers."""

    providers: list[ProviderUsage] = Field(
        default_factory=list,
        description="Provider usage statistics",
    )
    total_requests: int = Field(..., description="Total requests")
    fallback_count: int = Field(
        default=0,
        description="Number of requests that used fallback",
    )
    fallback_rate: float = Field(
        default=0.0,
        description="Percentage of requests using fallback",
    )


class TrendPoint(BaseModel):
    """A point in a trend line."""

    date: str = Field(..., description="Date")
    value: float = Field(..., description="Value at this point")


class Trend(BaseModel):
    """Trend analysis result."""

    metric: str = Field(..., description="Metric being analyzed")
    direction: str = Field(
        ...,
        description="Trend direction: 'up', 'down', 'stable'",
    )
    change_percentage: float = Field(
        ...,
        description="Percentage change from start to end",
    )
    data_points: list[TrendPoint] = Field(
        default_factory=list,
        description="Trend data points",
    )


class TrendsResponse(BaseModel):
    """Response for GET /api/analytics/trends."""

    usage_trend: Trend = Field(..., description="Usage trend")
    cost_trend: Trend | None = Field(None, description="Cost trend")
    quality_trend: Trend | None = Field(None, description="Quality/success rate trend")
    insights: list[str] = Field(
        default_factory=list,
        description="AI-generated insights about the trends",
    )
