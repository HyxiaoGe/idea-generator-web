"""
FastAPI application entry point.

This is the main entry point for the Nano Banana Lab API.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.redis import init_redis, close_redis
from api.middleware import setup_exception_handlers
from api.routers import health_router

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

    logger.info("Application startup complete")

    yield

    # ============ Shutdown ============
    logger.info("Shutting down application...")

    # Close Redis
    await close_redis()

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
        description="AI Image Generation API powered by Google Gemini",
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

    # Health check (no prefix)
    app.include_router(health_router, prefix="/api")

    # API routes (to be added)
    # app.include_router(auth_router, prefix="/api")
    # app.include_router(generate_router, prefix="/api")
    # app.include_router(chat_router, prefix="/api")
    # app.include_router(history_router, prefix="/api")
    # app.include_router(prompts_router, prefix="/api")
    # app.include_router(quota_router, prefix="/api")

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
