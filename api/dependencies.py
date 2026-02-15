"""
FastAPI dependency injection for database sessions and repositories.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session, is_database_available
from database.repositories import (
    APIKeyRepository,
    AuditRepository,
    ChatRepository,
    FavoriteRepository,
    ImageRepository,
    NotificationRepository,
    ProjectRepository,
    QuotaRepository,
    SettingsRepository,
    TemplateRepository,
    UserRepository,
)


async def get_db_session() -> AsyncGenerator[AsyncSession | None, None]:
    """
    Get database session dependency.

    Returns None if database is not configured/available.
    """
    if not is_database_available():
        yield None
        return

    async for session in get_session():
        yield session


async def get_user_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> UserRepository | None:
    """Get UserRepository dependency."""
    if session is None:
        return None
    return UserRepository(session)


async def get_image_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> ImageRepository | None:
    """Get ImageRepository dependency."""
    if session is None:
        return None
    return ImageRepository(session)


async def get_chat_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> ChatRepository | None:
    """Get ChatRepository dependency."""
    if session is None:
        return None
    return ChatRepository(session)


async def get_quota_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> QuotaRepository | None:
    """Get QuotaRepository dependency."""
    if session is None:
        return None
    return QuotaRepository(session)


async def get_audit_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> AuditRepository | None:
    """Get AuditRepository dependency."""
    if session is None:
        return None
    return AuditRepository(session)


async def get_settings_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> SettingsRepository | None:
    """Get SettingsRepository dependency."""
    if session is None:
        return None
    return SettingsRepository(session)


async def get_api_key_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> APIKeyRepository | None:
    """Get APIKeyRepository dependency."""
    if session is None:
        return None
    return APIKeyRepository(session)


async def get_favorite_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> FavoriteRepository | None:
    """Get FavoriteRepository dependency."""
    if session is None:
        return None
    return FavoriteRepository(session)


async def get_template_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> TemplateRepository | None:
    """Get TemplateRepository dependency."""
    if session is None:
        return None
    return TemplateRepository(session)


async def get_project_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> ProjectRepository | None:
    """Get ProjectRepository dependency."""
    if session is None:
        return None
    return ProjectRepository(session)


async def get_notification_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> NotificationRepository | None:
    """Get NotificationRepository dependency."""
    if session is None:
        return None
    return NotificationRepository(session)
