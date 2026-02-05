"""
Settings repository for user settings CRUD operations.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserSettings


class SettingsRepository:
    """Repository for UserSettings model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> UserSettings | None:
        """Get settings by user ID."""
        result = await self.session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        preferences: dict | None = None,
        api_settings: dict | None = None,
    ) -> UserSettings:
        """Create new user settings."""
        settings = UserSettings(
            user_id=user_id,
            preferences=preferences or {},
            api_settings=api_settings or {},
        )
        self.session.add(settings)
        await self.session.flush()
        return settings

    async def update(
        self,
        user_id: UUID,
        preferences: dict | None = None,
        api_settings: dict | None = None,
    ) -> UserSettings | None:
        """Update user settings."""
        settings = await self.get_by_user_id(user_id)
        if not settings:
            return None

        if preferences is not None:
            settings.preferences = preferences
        if api_settings is not None:
            settings.api_settings = api_settings

        await self.session.flush()
        return settings

    async def upsert(
        self,
        user_id: UUID,
        preferences: dict | None = None,
        api_settings: dict | None = None,
    ) -> UserSettings:
        """Create or update user settings."""
        settings = await self.get_by_user_id(user_id)
        if settings:
            if preferences is not None:
                settings.preferences = preferences
            if api_settings is not None:
                settings.api_settings = api_settings
            await self.session.flush()
            return settings
        return await self.create(user_id, preferences, api_settings)

    async def update_preferences(
        self,
        user_id: UUID,
        **kwargs,
    ) -> UserSettings | None:
        """Update specific preference fields (merge with existing)."""
        settings = await self.get_by_user_id(user_id)
        if not settings:
            # Create with defaults
            settings = await self.create(user_id, preferences=kwargs)
            return settings

        # Merge preferences
        current = dict(settings.preferences)
        current.update(kwargs)
        settings.preferences = current
        await self.session.flush()
        return settings

    async def delete(self, user_id: UUID) -> bool:
        """Delete user settings."""
        settings = await self.get_by_user_id(user_id)
        if settings:
            await self.session.delete(settings)
            await self.session.flush()
            return True
        return False
