"""
FastAPI application entry point.

This is the main entry point for the Nano Banana Lab API.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import setup_exception_handlers
from api.routers import (
    admin_router,
    analytics_router,
    auth_router,
    chat_router,
    favorites_router,
    generate_router,
    health_router,
    history_router,
    images_router,
    notifications_router,
    projects_router,
    prompts_router,
    quota_router,
    search_router,
    settings_router,
    templates_router,
    video_router,
    websocket_router,
)
from core.config import get_settings
from core.redis import close_redis, init_redis
from database import close_database, init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    settings = get_settings()

    # ============ Startup ============
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize Redis
    try:
        await init_redis()
        logger.info("Redis initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise

    # Initialize PostgreSQL Database
    if settings.is_database_configured:
        try:
            await init_database()
            logger.info("PostgreSQL database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Don't raise - database is optional, services can fall back to file storage
    else:
        logger.info("Database not configured, using file-based storage")

    logger.info("Application startup complete")

    yield

    # ============ Shutdown ============
    logger.info("Shutting down application...")

    # Close Redis
    await close_redis()

    # Close Database
    await close_database()

    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="AI Image & Video Generation API with multi-provider support",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ============ Middleware ============

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # ============ Exception Handlers ============
    setup_exception_handlers(app)

    # ============ Routers ============

    # Health check
    app.include_router(health_router, prefix="/api")

    # Authentication
    app.include_router(auth_router, prefix="/api")

    # Image generation
    app.include_router(generate_router, prefix="/api")

    # Quota management
    app.include_router(quota_router, prefix="/api")

    # Chat (multi-turn conversations)
    app.include_router(chat_router, prefix="/api")

    # History management
    app.include_router(history_router, prefix="/api")

    # Prompt library
    app.include_router(prompts_router, prefix="/api")

    # Video generation
    app.include_router(video_router, prefix="/api")

    # Image serving (for local storage proxy)
    app.include_router(images_router, prefix="/api")

    # User settings
    app.include_router(settings_router, prefix="/api")

    # Favorites (bookmarks)
    app.include_router(favorites_router, prefix="/api")

    # Templates
    app.include_router(templates_router, prefix="/api")

    # Projects (workspaces)
    app.include_router(projects_router, prefix="/api")

    # Notifications
    app.include_router(notifications_router, prefix="/api")

    # Analytics
    app.include_router(analytics_router, prefix="/api")

    # Search
    app.include_router(search_router, prefix="/api")

    # WebSocket
    app.include_router(websocket_router, prefix="/api")

    # Admin
    app.include_router(admin_router, prefix="/api")

    # ============ Root Endpoint ============

    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if not settings.is_production else None,
            "health": "/api/health",
        }

    return app


# Create application instance
app = create_app()


def run():
    """Run the application with uvicorn (for development)."""
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
