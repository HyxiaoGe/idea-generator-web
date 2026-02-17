"""
Preferences repository for user preferences CRUD operations.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserPreference


class PreferencesRepository:
    """Repository for UserPreference model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> UserPreference | None:
        """Get preferences by user ID."""
        result = await self.session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        preferences: dict | None = None,
        api_settings: dict | None = None,
    ) -> UserPreference:
        """Create new user preferences."""
        record = UserPreference(
            user_id=user_id,
            preferences=preferences or {},
            api_settings=api_settings or {},
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(
        self,
        user_id: UUID,
        preferences: dict | None = None,
        api_settings: dict | None = None,
    ) -> UserPreference | None:
        """Update user preferences."""
        record = await self.get_by_user_id(user_id)
        if not record:
            return None

        if preferences is not None:
            record.preferences = preferences
        if api_settings is not None:
            record.api_settings = api_settings

        await self.session.flush()
        return record

    async def upsert(
        self,
        user_id: UUID,
        preferences: dict | None = None,
        api_settings: dict | None = None,
    ) -> UserPreference:
        """Create or update user preferences."""
        record = await self.get_by_user_id(user_id)
        if record:
            if preferences is not None:
                record.preferences = preferences
            if api_settings is not None:
                record.api_settings = api_settings
            await self.session.flush()
            return record
        return await self.create(user_id, preferences, api_settings)

    async def update_preferences(
        self,
        user_id: UUID,
        **kwargs,
    ) -> UserPreference | None:
        """Update specific preference fields (merge with existing)."""
        record = await self.get_by_user_id(user_id)
        if not record:
            record = await self.create(user_id, preferences=kwargs)
            return record

        current = dict(record.preferences)
        current.update(kwargs)
        record.preferences = current
        await self.session.flush()
        return record

    async def delete(self, user_id: UUID) -> bool:
        """Delete user preferences."""
        record = await self.get_by_user_id(user_id)
        if record:
            await self.session.delete(record)
            await self.session.flush()
            return True
        return False
