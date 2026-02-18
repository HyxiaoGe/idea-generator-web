"""
Quota management router.

Endpoints:
- GET /api/quota - Get current quota status
- POST /api/quota/check - Check if quota is available
- GET /api/quota/config - Get quota configuration
"""

import logging

from fastapi import APIRouter, Depends

from api.schemas.quota import (
    QuotaCheckRequest,
    QuotaCheckResponse,
    QuotaConfigResponse,
    QuotaStatusResponse,
)
from core.auth import AppUser, get_current_user
from core.redis import get_redis
from services import COOLDOWN_SECONDS, DAILY_LIMIT, MAX_BATCH_SIZE, get_quota_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quota", tags=["quota"])


# ============ Helpers ============


def get_user_id_from_user(user: AppUser | None) -> str:
    """Get user ID for quota tracking."""
    if user:
        return user.user_folder_id
    return "anonymous"


# ============ Endpoints ============


@router.get("", response_model=QuotaStatusResponse)
async def get_quota_status(
    user: AppUser | None = Depends(get_current_user),
):
    """Get current quota status for the user."""
    user_id = get_user_id_from_user(user)

    redis = await get_redis()
    quota_service = get_quota_service(redis)

    status = await quota_service.get_quota_status(user_id)

    return QuotaStatusResponse(
        date=status.get("date"),
        used=status.get("used", 0),
        limit=status.get("limit", 0),
        remaining=status.get("remaining", 0),
        cooldown_active=status.get("cooldown_active", False),
        cooldown_remaining=status.get("cooldown_remaining", 0),
        resets_at=status.get("resets_at"),
    )


@router.post("/check", response_model=QuotaCheckResponse)
async def check_quota(
    request: QuotaCheckRequest,
    user: AppUser | None = Depends(get_current_user),
):
    """Check if quota is available. Does NOT consume quota."""
    user_id = get_user_id_from_user(user)

    redis = await get_redis()
    quota_service = get_quota_service(redis)

    can_generate, reason, info = await quota_service.check_quota(
        user_id=user_id,
        count=request.count,
    )

    cost = info.get("cost", 0)
    remaining = info.get("remaining", 0) - cost if can_generate else info.get("remaining", 0)

    return QuotaCheckResponse(
        can_generate=can_generate,
        reason=reason,
        cost=cost,
        remaining_after=max(0, remaining),
    )


@router.get("/config", response_model=QuotaConfigResponse)
async def get_quota_config():
    """Get quota configuration."""
    return QuotaConfigResponse(
        daily_limit=DAILY_LIMIT,
        cooldown_seconds=COOLDOWN_SECONDS,
        max_batch_size=MAX_BATCH_SIZE,
    )
