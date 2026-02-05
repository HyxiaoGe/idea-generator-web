"""
Admin API routers.

All admin endpoints require admin privileges.
"""

from fastapi import APIRouter

from .announcements import router as announcements_router
from .moderation import router as moderation_router
from .providers import router as providers_router
from .quota import router as quota_router
from .system import router as system_router
from .users import router as users_router

# Main admin router
router = APIRouter(prefix="/admin", tags=["admin"])

# Include sub-routers
router.include_router(users_router)
router.include_router(providers_router)
router.include_router(moderation_router)
router.include_router(system_router)
router.include_router(quota_router)
router.include_router(announcements_router)

__all__ = ["router"]
