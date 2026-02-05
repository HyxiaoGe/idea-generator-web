"""
Image repository for generated image CRUD operations.
"""

from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GeneratedImage


class ImageRepository:
    """Repository for GeneratedImage model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, image_id: UUID) -> GeneratedImage | None:
        """Get image by ID."""
        result = await self.session.execute(
            select(GeneratedImage).where(GeneratedImage.id == image_id)
        )
        return result.scalar_one_or_none()

    async def get_by_storage_key(self, storage_key: str) -> GeneratedImage | None:
        """Get image by storage key."""
        result = await self.session.execute(
            select(GeneratedImage).where(GeneratedImage.storage_key == storage_key)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        storage_key: str,
        filename: str,
        prompt: str,
        mode: str = "basic",
        storage_backend: str = "local",
        public_url: str | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        width: int | None = None,
        height: int | None = None,
        file_size: int | None = None,
        generation_duration_ms: int | None = None,
        text_response: str | None = None,
        thinking: str | None = None,
        user_id: UUID | None = None,
        chat_session_id: UUID | None = None,
        batch_id: UUID | None = None,
    ) -> GeneratedImage:
        """Create a new generated image record."""
        image = GeneratedImage(
            storage_key=storage_key,
            filename=filename,
            prompt=prompt,
            mode=mode,
            storage_backend=storage_backend,
            public_url=public_url,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            provider=provider,
            model=model,
            width=width,
            height=height,
            file_size=file_size,
            generation_duration_ms=generation_duration_ms,
            text_response=text_response,
            thinking=thinking,
            user_id=user_id,
            chat_session_id=chat_session_id,
            batch_id=batch_id,
        )
        self.session.add(image)
        await self.session.flush()
        return image

    async def list_by_user(
        self,
        user_id: UUID | None,
        limit: int = 20,
        offset: int = 0,
        mode: str | None = None,
        search: str | None = None,
    ) -> list[GeneratedImage]:
        """
        List images for a user with pagination and filtering.

        Args:
            user_id: User ID (None for anonymous users)
            limit: Max number of results
            offset: Number of results to skip
            mode: Filter by generation mode
            search: Search in prompt text
        """
        query = select(GeneratedImage).where(GeneratedImage.user_id == user_id)

        if mode:
            query = query.where(GeneratedImage.mode == mode)

        if search:
            query = query.where(GeneratedImage.prompt.ilike(f"%{search}%"))

        query = query.order_by(desc(GeneratedImage.created_at))
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: UUID | None,
        mode: str | None = None,
        search: str | None = None,
    ) -> int:
        """Count images for a user with optional filtering."""
        query = select(func.count()).select_from(GeneratedImage)
        query = query.where(GeneratedImage.user_id == user_id)

        if mode:
            query = query.where(GeneratedImage.mode == mode)

        if search:
            query = query.where(GeneratedImage.prompt.ilike(f"%{search}%"))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_stats_by_user(self, user_id: UUID | None) -> dict:
        """
        Get generation statistics for a user.

        Returns:
            Dict with total_images, images_by_mode, total_duration, etc.
        """
        # Total count
        total_query = select(func.count()).select_from(GeneratedImage)
        total_query = total_query.where(GeneratedImage.user_id == user_id)
        total_result = await self.session.execute(total_query)
        total_images = total_result.scalar_one()

        # Count by mode
        mode_query = (
            select(GeneratedImage.mode, func.count().label("count"))
            .where(GeneratedImage.user_id == user_id)
            .group_by(GeneratedImage.mode)
        )
        mode_result = await self.session.execute(mode_query)
        images_by_mode = {row.mode: row.count for row in mode_result}

        # Duration stats
        duration_query = select(
            func.sum(GeneratedImage.generation_duration_ms).label("total"),
            func.avg(GeneratedImage.generation_duration_ms).label("avg"),
        ).where(GeneratedImage.user_id == user_id)
        duration_result = await self.session.execute(duration_query)
        duration_row = duration_result.first()

        # Date range
        date_query = select(
            func.min(GeneratedImage.created_at).label("earliest"),
            func.max(GeneratedImage.created_at).label("latest"),
        ).where(GeneratedImage.user_id == user_id)
        date_result = await self.session.execute(date_query)
        date_row = date_result.first()

        return {
            "total_images": total_images,
            "images_by_mode": images_by_mode,
            "total_duration": (duration_row.total or 0) / 1000.0,  # Convert to seconds
            "average_duration": (duration_row.avg or 0) / 1000.0,
            "earliest_date": date_row.earliest,
            "latest_date": date_row.latest,
        }

    async def delete(self, image_id: UUID) -> bool:
        """Delete an image record."""
        image = await self.get_by_id(image_id)
        if image:
            await self.session.delete(image)
            await self.session.flush()
            return True
        return False

    async def delete_by_storage_key(self, storage_key: str) -> bool:
        """Delete an image by storage key."""
        image = await self.get_by_storage_key(storage_key)
        if image:
            await self.session.delete(image)
            await self.session.flush()
            return True
        return False
