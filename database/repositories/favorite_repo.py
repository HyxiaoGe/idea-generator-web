"""
Favorite repository for favorites and folder CRUD operations.
"""

from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Favorite, FavoriteFolder


class FavoriteRepository:
    """Repository for Favorite model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Favorites ============

    async def get_by_id(self, favorite_id: UUID) -> Favorite | None:
        """Get favorite by ID."""
        result = await self.session.execute(
            select(Favorite).options(selectinload(Favorite.image)).where(Favorite.id == favorite_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_image(self, user_id: UUID, image_id: UUID) -> Favorite | None:
        """Check if user has favorited an image."""
        result = await self.session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.image_id == image_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        image_id: UUID,
        folder_id: UUID | None = None,
        note: str | None = None,
    ) -> Favorite:
        """Create a new favorite."""
        favorite = Favorite(
            user_id=user_id,
            image_id=image_id,
            folder_id=folder_id,
            note=note,
        )
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    async def list_by_user(
        self,
        user_id: UUID,
        folder_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Favorite]:
        """List favorites for a user, optionally filtered by folder."""
        query = (
            select(Favorite)
            .options(selectinload(Favorite.image))
            .where(Favorite.user_id == user_id)
        )

        if folder_id is not None:
            query = query.where(Favorite.folder_id == folder_id)

        query = query.order_by(desc(Favorite.created_at)).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID, folder_id: UUID | None = None) -> int:
        """Count favorites for a user."""
        query = select(func.count()).select_from(Favorite).where(Favorite.user_id == user_id)

        if folder_id is not None:
            query = query.where(Favorite.folder_id == folder_id)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        favorite_id: UUID,
        folder_id: UUID | None = None,
        note: str | None = None,
    ) -> Favorite | None:
        """Update a favorite."""
        favorite = await self.get_by_id(favorite_id)
        if not favorite:
            return None

        if folder_id is not None:
            favorite.folder_id = folder_id
        if note is not None:
            favorite.note = note

        await self.session.flush()
        return favorite

    async def delete(self, favorite_id: UUID) -> bool:
        """Delete a favorite."""
        favorite = await self.get_by_id(favorite_id)
        if favorite:
            await self.session.delete(favorite)
            await self.session.flush()
            return True
        return False

    async def delete_by_user_and_image(self, user_id: UUID, image_id: UUID) -> bool:
        """Remove favorite by user and image."""
        favorite = await self.get_by_user_and_image(user_id, image_id)
        if favorite:
            await self.session.delete(favorite)
            await self.session.flush()
            return True
        return False

    async def bulk_create(
        self,
        user_id: UUID,
        image_ids: list[UUID],
        folder_id: UUID | None = None,
    ) -> list[Favorite]:
        """Create multiple favorites at once."""
        favorites = []
        for image_id in image_ids:
            # Check if already exists
            existing = await self.get_by_user_and_image(user_id, image_id)
            if not existing:
                favorite = Favorite(
                    user_id=user_id,
                    image_id=image_id,
                    folder_id=folder_id,
                )
                self.session.add(favorite)
                favorites.append(favorite)

        await self.session.flush()
        return favorites

    async def bulk_delete(self, user_id: UUID, favorite_ids: list[UUID]) -> int:
        """Delete multiple favorites."""
        deleted = 0
        for favorite_id in favorite_ids:
            result = await self.session.execute(
                select(Favorite).where(
                    Favorite.id == favorite_id,
                    Favorite.user_id == user_id,
                )
            )
            favorite = result.scalar_one_or_none()
            if favorite:
                await self.session.delete(favorite)
                deleted += 1

        await self.session.flush()
        return deleted

    # ============ Folders ============

    async def get_folder_by_id(self, folder_id: UUID) -> FavoriteFolder | None:
        """Get folder by ID."""
        result = await self.session.execute(
            select(FavoriteFolder).where(FavoriteFolder.id == folder_id)
        )
        return result.scalar_one_or_none()

    async def create_folder(
        self,
        user_id: UUID,
        name: str,
        description: str | None = None,
    ) -> FavoriteFolder:
        """Create a new folder."""
        folder = FavoriteFolder(
            user_id=user_id,
            name=name,
            description=description,
        )
        self.session.add(folder)
        await self.session.flush()
        return folder

    async def list_folders_by_user(self, user_id: UUID) -> list[FavoriteFolder]:
        """List all folders for a user."""
        result = await self.session.execute(
            select(FavoriteFolder)
            .where(FavoriteFolder.user_id == user_id)
            .order_by(FavoriteFolder.name)
        )
        return list(result.scalars().all())

    async def update_folder(
        self,
        folder_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> FavoriteFolder | None:
        """Update a folder."""
        folder = await self.get_folder_by_id(folder_id)
        if not folder:
            return None

        if name is not None:
            folder.name = name
        if description is not None:
            folder.description = description

        await self.session.flush()
        return folder

    async def delete_folder(self, folder_id: UUID) -> bool:
        """Delete a folder (favorites will have folder_id set to NULL)."""
        folder = await self.get_folder_by_id(folder_id)
        if folder:
            await self.session.delete(folder)
            await self.session.flush()
            return True
        return False
