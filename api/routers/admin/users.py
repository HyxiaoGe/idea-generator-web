"""
Admin user management router.

Endpoints:
- GET /api/admin/users - List users
- GET /api/admin/users/{id} - Get user details
- PUT /api/admin/users/{id} - Update user
- PUT /api/admin/users/{id}/tier - Update user tier
- PUT /api/admin/users/{id}/quota - Adjust user quota
- POST /api/admin/users/{id}/ban - Ban user
- POST /api/admin/users/{id}/unban - Unban user
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_user_repository
from api.routers.auth import require_current_user
from api.schemas.admin import (
    AdminUserInfo,
    BanUserRequest,
    ListUsersResponse,
    UpdateUserQuotaRequest,
    UpdateUserTierRequest,
    UserActionResponse,
    UserTier,
)
from database.repositories import UserRepository
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["admin-users"])


# ============ Admin Check ============


async def require_admin(user: GitHubUser = Depends(require_current_user)) -> GitHubUser:
    """Require admin privileges."""
    # TODO: Implement proper admin check
    # For now, just check if authenticated
    return user


# ============ Endpoints ============


@router.get("", response_model=ListUsersResponse)
async def list_users(
    search: str | None = Query(default=None),
    tier: UserTier | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: GitHubUser = Depends(require_admin),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List all users (admin only)."""
    if not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    # TODO: Implement user listing with filters
    return ListUsersResponse(
        users=[],
        total=0,
        limit=limit,
        offset=offset,
        has_more=False,
    )


@router.get("/{user_id}", response_model=AdminUserInfo)
async def get_user(
    user_id: str,
    admin: GitHubUser = Depends(require_admin),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get user details (admin only)."""
    if not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    db_user = await user_repo.get_by_id(user_uuid)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return AdminUserInfo(
        id=str(db_user.id),
        username=db_user.username,
        email=db_user.email,
        avatar_url=db_user.avatar_url,
        tier=UserTier(db_user.tier),
        is_banned=False,  # TODO: implement ban tracking
        ban_reason=None,
        total_generations=0,
        quota_used=0,
        quota_limit=0,
        created_at=db_user.created_at,
        last_login_at=db_user.last_login_at,
    )


@router.put("/{user_id}/tier", response_model=UserActionResponse)
async def update_user_tier(
    user_id: str,
    request: UpdateUserTierRequest,
    admin: GitHubUser = Depends(require_admin),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Update user tier (admin only)."""
    if not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    db_user = await user_repo.update_tier(user_uuid, request.tier.value)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserActionResponse(
        success=True,
        message=f"User tier updated to {request.tier.value}",
        user=AdminUserInfo(
            id=str(db_user.id),
            username=db_user.username,
            email=db_user.email,
            avatar_url=db_user.avatar_url,
            tier=UserTier(db_user.tier),
            is_banned=False,
            ban_reason=None,
            total_generations=0,
            quota_used=0,
            quota_limit=0,
            created_at=db_user.created_at,
            last_login_at=db_user.last_login_at,
        ),
    )


@router.put("/{user_id}/quota", response_model=UserActionResponse)
async def update_user_quota(
    user_id: str,
    request: UpdateUserQuotaRequest,
    admin: GitHubUser = Depends(require_admin),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Adjust user quota multiplier (admin only)."""
    if not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    db_user = await user_repo.get_by_id(user_uuid)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update quota multiplier
    db_user = await user_repo.update_tier(
        user_uuid,
        db_user.tier,
        quota_multiplier=request.quota_multiplier,
    )

    return UserActionResponse(
        success=True,
        message=f"User quota multiplier updated to {request.quota_multiplier}",
        user=AdminUserInfo(
            id=str(db_user.id),
            username=db_user.username,
            email=db_user.email,
            avatar_url=db_user.avatar_url,
            tier=UserTier(db_user.tier),
            is_banned=False,
            ban_reason=None,
            total_generations=0,
            quota_used=0,
            quota_limit=0,
            created_at=db_user.created_at,
            last_login_at=db_user.last_login_at,
        ),
    )


@router.post("/{user_id}/ban", response_model=UserActionResponse)
async def ban_user(
    user_id: str,
    request: BanUserRequest,
    admin: GitHubUser = Depends(require_admin),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Ban a user (admin only)."""
    # TODO: Implement user banning
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{user_id}/unban", response_model=UserActionResponse)
async def unban_user(
    user_id: str,
    admin: GitHubUser = Depends(require_admin),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Unban a user (admin only)."""
    # TODO: Implement user unbanning
    raise HTTPException(status_code=501, detail="Not implemented")
