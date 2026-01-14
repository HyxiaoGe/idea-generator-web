"""
API routers for different endpoints.
"""

from .health import router as health_router
from .auth import router as auth_router
from .generate import router as generate_router
from .quota import router as quota_router

__all__ = [
    "health_router",
    "auth_router",
    "generate_router",
    "quota_router",
]
