"""
API routers for different endpoints.
"""

from .health import router as health_router
from .auth import router as auth_router
from .generate import router as generate_router
from .quota import router as quota_router
from .chat import router as chat_router
from .history import router as history_router
from .prompts import router as prompts_router

__all__ = [
    "health_router",
    "auth_router",
    "generate_router",
    "quota_router",
    "chat_router",
    "history_router",
    "prompts_router",
]
