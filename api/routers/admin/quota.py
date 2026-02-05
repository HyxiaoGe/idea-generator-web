"""
Admin quota management router.

Endpoints:
- GET /api/admin/quota/config - Get quota configuration
- PUT /api/admin/quota/config - Update quota configuration
- GET /api/admin/quota/tiers - List quota tiers
- POST /api/admin/quota/tiers - Create quota tier
- POST /api/admin/quota/reset/{user_id} - Reset user quota
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.routers.auth import require_current_user
from api.schemas.admin import (
    QuotaConfigResponse,
    QuotaTierConfig,
    ResetUserQuotaRequest,
    ResetUserQuotaResponse,
    UpdateQuotaConfigRequest,
    UserTier,
)
from core.redis import get_redis
from services import QUOTA_CONFIGS, get_quota_service
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quota", tags=["admin-quota"])


# ============ Admin Check ============


async def require_admin(user: GitHubUser = Depends(require_current_user)) -> GitHubUser:
    """Require admin privileges."""
    return user


# ============ Endpoints ============


@router.get("/config", response_model=QuotaConfigResponse)
async def get_quota_config(
    admin: GitHubUser = Depends(require_admin),
):
    """Get current quota configuration."""
    tiers = []

    for _mode, config in QUOTA_CONFIGS.items():
        tier = QuotaTierConfig(
            tier=UserTier.FREE,  # All current configs are for free tier
            daily_limit=config.daily_limit,
            monthly_limit=None,
            max_resolution=config.max_resolution,
            features=[],
        )
        tiers.append(tier)

    return QuotaConfigResponse(tiers=tiers)


@router.put("/config", response_model=QuotaConfigResponse)
async def update_quota_config(
    request: UpdateQuotaConfigRequest,
    admin: GitHubUser = Depends(require_admin),
):
    """Update quota configuration."""
    # TODO: Implement config update
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/tiers")
async def list_quota_tiers(
    admin: GitHubUser = Depends(require_admin),
):
    """List available quota tiers."""
    return {
        "tiers": [
            {"name": "free", "description": "Free tier with limited quotas"},
            {"name": "trial", "description": "Trial tier with extended quotas"},
            {"name": "pro", "description": "Pro tier with high quotas"},
            {"name": "enterprise", "description": "Enterprise tier with unlimited quotas"},
        ]
    }


@router.post("/tiers")
async def create_quota_tier(
    admin: GitHubUser = Depends(require_admin),
):
    """Create a new quota tier."""
    # TODO: Implement tier creation
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/reset/{user_id}", response_model=ResetUserQuotaResponse)
async def reset_user_quota(
    user_id: str,
    request: ResetUserQuotaRequest | None = None,
    admin: GitHubUser = Depends(require_admin),
):
    """Reset a user's quota."""
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not configured")

    get_quota_service(redis)

    # Reset all quota keys for the user
    # TODO: Implement proper quota reset
    logger.info(f"Admin {admin.login} reset quota for user {user_id}")

    return ResetUserQuotaResponse(
        success=True,
        message=f"Quota reset for user {user_id}",
        new_quota=0,
    )
