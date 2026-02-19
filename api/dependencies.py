"""
FastAPI dependency injection for database sessions and repositories.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import AppUser, require_current_user
from database import get_session, is_database_available
from database.repositories import (
    APIKeyRepository,
    AuditRepository,
    ChatRepository,
    FavoriteRepository,
    ImageRepository,
    NotificationRepository,
    PreferencesRepository,
    ProjectRepository,
    QuotaRepository,
    TemplateRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


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


async def get_preferences_repository(
    session: AsyncSession | None = Depends(get_db_session),
) -> PreferencesRepository | None:
    """Get PreferencesRepository dependency."""
    if session is None:
        return None
    return PreferencesRepository(session)


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


async def ensure_db_user(
    user: AppUser = Depends(require_current_user),
    user_repo: UserRepository | None = Depends(get_user_repository),
) -> str | None:
    """
    Ensure the authenticated user exists in the database.

    Auto-syncs from auth-service JWT on first access.
    Returns the database user UUID string, or None if DB is unavailable.
    """
    if not user_repo:
        return None

    db_user = await user_repo.create_or_update_from_auth(
        auth_id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
    )
    return str(db_user.id)
