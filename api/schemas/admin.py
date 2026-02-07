"""
Pydantic schemas for admin API.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ============ User Management ============


class UserTier(StrEnum):
    """User tier levels."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class AdminUserInfo(BaseModel):
    """User information for admin views."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str | None = Field(None, description="Email")
    avatar_url: str | None = Field(None, description="Avatar URL")
    tier: UserTier = Field(..., description="User tier")
    is_banned: bool = Field(default=False, description="Whether user is banned")
    ban_reason: str | None = Field(None, description="Ban reason")
    total_generations: int = Field(default=0, description="Total generations")
    quota_used: int = Field(default=0, description="Current quota used")
    quota_limit: int = Field(default=0, description="Current quota limit")
    created_at: datetime = Field(..., description="Registration date")
    last_login_at: datetime | None = Field(None, description="Last login")


class ListUsersResponse(BaseModel):
    """Response for GET /api/admin/users."""

    users: list[AdminUserInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total users")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="More items exist")


class UpdateUserTierRequest(BaseModel):
    """Request for PUT /api/admin/users/{id}/tier."""

    tier: UserTier = Field(..., description="New tier")
    reason: str | None = Field(None, description="Reason for change")


class UpdateUserQuotaRequest(BaseModel):
    """Request for PUT /api/admin/users/{id}/quota."""

    quota_multiplier: float = Field(
        ...,
        ge=0.1,
        le=100.0,
        description="Quota multiplier",
    )
    reason: str | None = Field(None, description="Reason for change")


class BanUserRequest(BaseModel):
    """Request for POST /api/admin/users/{id}/ban."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Ban reason",
    )
    duration_days: int | None = Field(
        None,
        ge=1,
        description="Ban duration in days (None = permanent)",
    )


class UserActionResponse(BaseModel):
    """Response for user management actions."""

    success: bool = True
    message: str
    user: AdminUserInfo


# ============ Provider Management ============


class ProviderStatus(StrEnum):
    """Provider status."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    CIRCUIT_OPEN = "circuit_open"
    DEGRADED = "degraded"


class AdminProviderInfo(BaseModel):
    """Provider information for admin views."""

    name: str = Field(..., description="Provider name")
    status: ProviderStatus = Field(..., description="Current status")
    priority: int = Field(..., description="Routing priority")
    enabled: bool = Field(..., description="Whether enabled")
    supports_image: bool = Field(default=False, description="Supports image gen")
    supports_video: bool = Field(default=False, description="Supports video gen")
    health_score: float = Field(default=100.0, description="Health score 0-100")
    total_requests_24h: int = Field(default=0, description="Requests in last 24h")
    success_rate_24h: float = Field(default=100.0, description="Success rate 24h")
    avg_latency_ms: float = Field(default=0.0, description="Average latency")
    circuit_breaker_state: str | None = Field(
        None,
        description="Circuit breaker state",
    )
    last_error: str | None = Field(None, description="Last error message")
    last_error_at: datetime | None = Field(None, description="Last error time")


class ListProvidersResponse(BaseModel):
    """Response for GET /api/admin/providers."""

    providers: list[AdminProviderInfo] = Field(default_factory=list)


class UpdateProviderRequest(BaseModel):
    """Request for PUT /api/admin/providers/{name}."""

    priority: int | None = Field(None, ge=1, description="New priority")
    enabled: bool | None = Field(None, description="Enable/disable")


class ProviderActionResponse(BaseModel):
    """Response for provider management actions."""

    success: bool = True
    message: str
    provider: AdminProviderInfo


class ResetCircuitBreakersResponse(BaseModel):
    """Response for POST /api/admin/providers/circuit-breakers/reset."""

    success: bool = True
    reset_count: int = Field(..., description="Number of circuit breakers reset")


# ============ Content Moderation ============


class ModerationLogEntry(BaseModel):
    """Moderation log entry."""

    id: str = Field(..., description="Log entry ID")
    user_id: str | None = Field(None, description="User ID")
    action: str = Field(..., description="Action taken")
    reason: str = Field(..., description="Reason for action")
    content_preview: str | None = Field(None, description="Content preview")
    rule_matched: str | None = Field(None, description="Rule that triggered")
    created_at: datetime = Field(..., description="Timestamp")


class ListModerationLogsResponse(BaseModel):
    """Response for GET /api/admin/moderation/logs."""

    logs: list[ModerationLogEntry] = Field(default_factory=list)
    total: int = Field(..., description="Total entries")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="More items exist")


class ModerationRule(BaseModel):
    """Content moderation rule."""

    id: str = Field(..., description="Rule ID")
    name: str = Field(..., description="Rule name")
    type: str = Field(..., description="Rule type (keyword, regex, ai)")
    pattern: str = Field(..., description="Pattern to match")
    action: str = Field(..., description="Action to take")
    severity: str = Field(..., description="Severity level")
    enabled: bool = Field(default=True, description="Whether rule is active")
    hit_count: int = Field(default=0, description="Number of times triggered")
    created_at: datetime = Field(..., description="Creation timestamp")


class ListModerationRulesResponse(BaseModel):
    """Response for GET /api/admin/moderation/rules."""

    rules: list[ModerationRule] = Field(default_factory=list)
    total: int = Field(..., description="Total rules")


class CreateModerationRuleRequest(BaseModel):
    """Request for POST /api/admin/moderation/rules."""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="keyword, regex, or ai")
    pattern: str = Field(..., min_length=1)
    action: str = Field(default="block", description="block, warn, or log")
    severity: str = Field(default="medium", description="low, medium, high, critical")


class ModerationStatsResponse(BaseModel):
    """Response for GET /api/admin/moderation/stats."""

    total_checks: int = Field(..., description="Total content checks")
    blocked_count: int = Field(..., description="Content blocked")
    warned_count: int = Field(..., description="Content warned")
    passed_count: int = Field(..., description="Content passed")
    top_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most triggered rules",
    )


# ============ System Monitoring ============


class SystemStatusResponse(BaseModel):
    """Response for GET /api/admin/system/status."""

    status: str = Field(..., description="Overall system status")
    uptime_seconds: float = Field(..., description="System uptime")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Environment")
    components: dict[str, str] = Field(
        default_factory=dict,
        description="Component statuses",
    )


class SystemMetricsResponse(BaseModel):
    """Response for GET /api/admin/system/metrics."""

    cpu_percent: float = Field(..., description="CPU usage percentage")
    memory_percent: float = Field(..., description="Memory usage percentage")
    disk_percent: float = Field(..., description="Disk usage percentage")
    active_connections: int = Field(..., description="Active WebSocket connections")
    requests_per_minute: float = Field(..., description="Requests per minute")
    average_latency_ms: float = Field(..., description="Average request latency")


class SystemLogsResponse(BaseModel):
    """Response for GET /api/admin/system/logs."""

    logs: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(..., description="Total log entries")
    limit: int = Field(..., description="Items returned")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="More items exist")


class StorageStatusResponse(BaseModel):
    """Response for GET /api/admin/system/storage."""

    backend: str = Field(..., description="Storage backend (r2, local)")
    total_files: int = Field(..., description="Total files stored")
    total_size_bytes: int = Field(..., description="Total size in bytes")
    usage_by_user: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Top users by storage",
    )


class RedisStatusResponse(BaseModel):
    """Response for GET /api/admin/system/redis."""

    connected: bool = Field(..., description="Whether connected")
    version: str | None = Field(None, description="Redis version")
    memory_used: int = Field(default=0, description="Memory used in bytes")
    total_keys: int = Field(default=0, description="Total keys")
    connected_clients: int = Field(default=0, description="Connected clients")


class DatabaseStatusResponse(BaseModel):
    """Response for GET /api/admin/system/database."""

    connected: bool = Field(..., description="Whether connected")
    version: str | None = Field(None, description="PostgreSQL version")
    pool_size: int = Field(default=0, description="Connection pool size")
    pool_in_use: int = Field(default=0, description="Connections in use")
    total_tables: int = Field(default=0, description="Total tables")
    total_rows: dict[str, int] = Field(
        default_factory=dict,
        description="Row counts by table",
    )


# ============ Quota Management ============


class QuotaTierConfig(BaseModel):
    """Quota configuration for a tier."""

    tier: UserTier = Field(..., description="Tier name")
    daily_limit: int = Field(..., description="Daily generation limit")
    monthly_limit: int | None = Field(None, description="Monthly limit")
    max_resolution: str = Field(..., description="Max resolution allowed")
    features: list[str] = Field(default_factory=list, description="Enabled features")


class QuotaConfigResponse(BaseModel):
    """Response for GET /api/admin/quota/config."""

    tiers: list[QuotaTierConfig] = Field(default_factory=list)


class UpdateQuotaConfigRequest(BaseModel):
    """Request for PUT /api/admin/quota/config."""

    tiers: list[QuotaTierConfig] = Field(...)


class ResetUserQuotaRequest(BaseModel):
    """Request for POST /api/admin/quota/reset/{user_id}."""

    reason: str | None = Field(None, description="Reason for reset")


class ResetUserQuotaResponse(BaseModel):
    """Response for POST /api/admin/quota/reset/{user_id}."""

    success: bool = True
    message: str
    new_quota: int = Field(..., description="New quota value")


# ============ Announcements ============


class AnnouncementInfo(BaseModel):
    """Announcement information."""

    id: str = Field(..., description="Announcement ID")
    title: str = Field(..., description="Title")
    content: str = Field(..., description="Content (markdown)")
    type: str = Field(default="info", description="Type: info, warning, critical")
    is_active: bool = Field(default=True, description="Whether active")
    starts_at: datetime | None = Field(None, description="Start time")
    ends_at: datetime | None = Field(None, description="End time")
    target_tiers: list[UserTier] | None = Field(
        None,
        description="Target tiers (None = all)",
    )
    created_at: datetime = Field(..., description="Creation timestamp")


class ListAnnouncementsResponse(BaseModel):
    """Response for GET /api/admin/announcements."""

    announcements: list[AnnouncementInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total announcements")


class CreateAnnouncementRequest(BaseModel):
    """Request for POST /api/admin/announcements."""

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    type: str = Field(default="info", description="info, warning, critical")
    starts_at: datetime | None = Field(None, description="Start time")
    ends_at: datetime | None = Field(None, description="End time")
    target_tiers: list[UserTier] | None = Field(None, description="Target tiers")


class AnnouncementResponse(BaseModel):
    """Response for announcement operations."""

    success: bool = True
    announcement: AnnouncementInfo


class BroadcastNotificationRequest(BaseModel):
    """Request for POST /api/admin/notifications/broadcast."""

    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=1000)
    type: str = Field(default="announcement", description="Notification type")
    target_tiers: list[UserTier] | None = Field(None, description="Target tiers")
    target_user_ids: list[str] | None = Field(None, description="Specific user IDs")


class BroadcastNotificationResponse(BaseModel):
    """Response for POST /api/admin/notifications/broadcast."""

    success: bool = True
    recipients: int = Field(..., description="Number of recipients")
    message: str
