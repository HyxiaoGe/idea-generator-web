"""
API Key repository for API key CRUD operations.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import APIKey


class APIKeyRepository:
    """Repository for APIKey model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, key_id: UUID) -> APIKey | None:
        """Get API key by ID."""
        result = await self.session.execute(select(APIKey).where(APIKey.id == key_id))
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> APIKey | None:
        """Get API key by hash value."""
        result = await self.session.execute(select(APIKey).where(APIKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> APIKey:
        """Create a new API key."""
        api_key = APIKey(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            expires_at=expires_at,
        )
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def list_by_user(
        self,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[APIKey]:
        """List API keys for a user."""
        result = await self.session.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(desc(APIKey.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        """Count API keys for a user."""
        result = await self.session.execute(
            select(func.count()).select_from(APIKey).where(APIKey.user_id == user_id)
        )
        return result.scalar_one()

    async def update_last_used(self, key_id: UUID) -> None:
        """Update the last_used_at timestamp."""
        await self.session.execute(
            update(APIKey).where(APIKey.id == key_id).values(last_used_at=func.now())
        )
        await self.session.flush()

    async def delete(self, key_id: UUID) -> bool:
        """Delete an API key."""
        api_key = await self.get_by_id(key_id)
        if api_key:
            await self.session.delete(api_key)
            await self.session.flush()
            return True
        return False

    async def delete_by_user(self, user_id: UUID, key_id: UUID) -> bool:
        """Delete an API key owned by a specific user."""
        result = await self.session.execute(
            select(APIKey).where(
                APIKey.id == key_id,
                APIKey.user_id == user_id,
            )
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            await self.session.delete(api_key)
            await self.session.flush()
            return True
        return False
