"""
Admin quota management router.

Endpoints:
- GET /api/admin/quota/config - Get quota configuration
- POST /api/admin/quota/reset/{user_id} - Reset user quota
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.routers.auth import require_current_user
from api.schemas.admin import (
    ResetUserQuotaRequest,
    ResetUserQuotaResponse,
)
from core.redis import get_redis
from services import COOLDOWN_SECONDS, DAILY_LIMIT, MAX_BATCH_SIZE, get_quota_service
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quota", tags=["admin-quota"])


# ============ Admin Check ============


async def require_admin(user: GitHubUser = Depends(require_current_user)) -> GitHubUser:
    """Require admin privileges."""
    return user


# ============ Endpoints ============


@router.get("/config")
async def get_quota_config(
    admin: GitHubUser = Depends(require_admin),
):
    """Get current quota configuration."""
    return {
        "daily_limit": DAILY_LIMIT,
        "cooldown_seconds": COOLDOWN_SECONDS,
        "max_batch_size": MAX_BATCH_SIZE,
    }


@router.post("/reset/{user_id}", response_model=ResetUserQuotaResponse)
async def reset_user_quota(
    user_id: str,
    request: ResetUserQuotaRequest | None = None,
    admin: GitHubUser = Depends(require_admin),
):
    """Reset a user's daily quota."""
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not configured")

    quota_service = get_quota_service(redis)
    await quota_service.reset_user_quota(user_id)

    logger.info(f"Admin {admin.login} reset quota for user {user_id}")

    return ResetUserQuotaResponse(
        success=True,
        message=f"Quota reset for user {user_id}",
        new_quota=0,
    )
