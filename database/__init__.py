"""
Database module for Nano Banana Lab.

Provides async SQLAlchemy database connection management and session handling.
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_async_session_factory = None


def get_database_url() -> str:
    """Get the database URL from settings."""
    settings = get_settings()
    return settings.database_url


async def init_database() -> None:
    """
    Initialize the database engine and session factory.

    Should be called during application startup.
    """
    global _engine, _async_session_factory

    settings = get_settings()

    if not settings.database_enabled:
        logger.info("Database is disabled, skipping initialization")
        return

    database_url = settings.database_url
    if not database_url:
        logger.warning("DATABASE_URL not configured, database features disabled")
        return

    logger.info("Initializing database connection...")

    _engine = create_async_engine(
        database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        echo=settings.debug and settings.db_echo,
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    logger.info("Database initialized successfully")


async def close_database() -> None:
    """
    Close the database connection.

    Should be called during application shutdown.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        logger.info("Closing database connection...")
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connection closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session.

    Use as a dependency in FastAPI:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_database() first or check DATABASE_URL."
        )

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def is_database_available() -> bool:
    """Check if database is available and initialized."""
    return _engine is not None and _async_session_factory is not None


# Export commonly used items
__all__ = [
    "init_database",
    "close_database",
    "get_session",
    "is_database_available",
]
