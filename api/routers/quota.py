"""
Quota management router.

Endpoints:
- GET /api/quota - Get current quota status
- POST /api/quota/check - Check if quota is available
- GET /api/quota/config - Get quota configuration
"""

import logging

from fastapi import APIRouter, Depends, Header

from api.routers.auth import get_current_user
from api.schemas.quota import (
    ModeQuota,
    QuotaCheckRequest,
    QuotaCheckResponse,
    QuotaConfigResponse,
    QuotaStatusResponse,
)
from core.redis import get_redis
from services import (
    GENERATION_COOLDOWN,
    GLOBAL_DAILY_QUOTA,
    QUOTA_CONFIGS,
    get_quota_service,
    is_trial_mode,
)
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quota", tags=["quota"])


# ============ Helpers ============


def get_user_id_from_user(user: GitHubUser | None) -> str:
    """Get user ID for quota tracking."""
    if user:
        return user.user_folder_id
    return "anonymous"


# ============ Endpoints ============


@router.get("", response_model=QuotaStatusResponse)
async def get_quota_status(
    user: GitHubUser | None = Depends(get_current_user),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """
    Get current quota status for the user.

    Returns quota usage, limits, and cooldown status.
    """
    # If user has own API key, they're not in trial mode
    if x_api_key and not is_trial_mode(x_api_key):
        return QuotaStatusResponse(
            is_trial_mode=False,
            global_used=0,
            global_limit=0,
            global_remaining=0,
            modes={},
            cooldown_active=False,
            cooldown_remaining=0,
        )

    user_id = get_user_id_from_user(user)

    redis = await get_redis()
    quota_service = get_quota_service(redis)

    if not quota_service.is_trial_enabled:
        return QuotaStatusResponse(
            is_trial_mode=False,
            global_used=0,
            global_limit=0,
            global_remaining=0,
            modes={},
        )

    status = await quota_service.get_quota_status(user_id)

    # Convert modes to ModeQuota objects
    modes = {key: ModeQuota(**mode_data) for key, mode_data in status.get("modes", {}).items()}

    return QuotaStatusResponse(
        is_trial_mode=status.get("is_trial_mode", False),
        date=status.get("date"),
        global_used=status.get("global_used", 0),
        global_limit=status.get("global_limit", 0),
        global_remaining=status.get("global_remaining", 0),
        modes=modes,
        cooldown_active=status.get("cooldown_active", False),
        cooldown_remaining=status.get("cooldown_remaining", 0),
        resets_at=status.get("resets_at"),
    )


@router.post("/check", response_model=QuotaCheckResponse)
async def check_quota(
    request: QuotaCheckRequest,
    user: GitHubUser | None = Depends(get_current_user),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """
    Check if quota is available for a generation request.

    Does NOT consume quota, only checks availability.
    """
    # If user has own API key, always allow
    if x_api_key and not is_trial_mode(x_api_key):
        return QuotaCheckResponse(
            can_generate=True,
            reason="OK",
            cost=0,
            remaining_after=0,
        )

    user_id = get_user_id_from_user(user)

    redis = await get_redis()
    quota_service = get_quota_service(redis)

    if not quota_service.is_trial_enabled:
        return QuotaCheckResponse(
            can_generate=True,
            reason="Trial mode disabled",
            cost=0,
            remaining_after=0,
        )

    can_generate, reason, info = await quota_service.check_quota(
        user_id=user_id,
        mode=request.mode,
        resolution=request.resolution,
        count=request.count,
    )

    cost = info.get("cost", 0)
    remaining = (
        info.get("global_remaining", 0) - cost if can_generate else info.get("global_remaining", 0)
    )

    return QuotaCheckResponse(
        can_generate=can_generate,
        reason=reason,
        cost=cost,
        remaining_after=max(0, remaining),
    )


@router.get("/config", response_model=QuotaConfigResponse)
async def get_quota_config():
    """
    Get quota configuration.

    Returns global limits and per-mode configurations.
    """
    modes = {
        key: ModeQuota(
            name=config.display_name,
            used=0,
            limit=config.daily_limit,
            remaining=config.daily_limit,
            cost=config.cost,
        )
        for key, config in QUOTA_CONFIGS.items()
    }

    return QuotaConfigResponse(
        global_daily_quota=GLOBAL_DAILY_QUOTA,
        cooldown_seconds=GENERATION_COOLDOWN,
        modes=modes,
    )
