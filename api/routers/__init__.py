"""
API routers for different endpoints.
"""

from .admin import router as admin_router
from .analytics import router as analytics_router
from .auth import router as auth_router
from .chat import router as chat_router
from .favorites import router as favorites_router
from .generate import router as generate_router
from .health import router as health_router
from .history import router as history_router
from .images import router as images_router
from .models import router as models_router
from .notifications import router as notifications_router
from .preferences import router as preferences_router
from .projects import router as projects_router
from .quota import router as quota_router
from .search import router as search_router
from .templates import router as templates_router
from .video import router as video_router
from .websocket import router as websocket_router

__all__ = [
    "health_router",
    "auth_router",
    "generate_router",
    "quota_router",
    "chat_router",
    "history_router",
    "video_router",
    "images_router",
    "models_router",
    "preferences_router",
    "favorites_router",
    "templates_router",
    "projects_router",
    "notifications_router",
    "analytics_router",
    "search_router",
    "websocket_router",
    "admin_router",
]
