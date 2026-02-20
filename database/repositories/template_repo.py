"""
Template repository for the prompt template library.

Provides data access for PromptTemplate, likes, favorites, and usage tracking.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.template import PromptTemplate
from database.models.template_favorite import UserTemplateFavorite
from database.models.template_like import UserTemplateLike
from database.models.template_usage import UserTemplateUsage


class TemplateRepository:
    """Repository for PromptTemplate and related models."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    async def get_by_id(self, template_id: UUID) -> PromptTemplate | None:
        """Get a template by ID (excludes soft-deleted)."""
        result = await self.session.execute(
            select(PromptTemplate).where(
                PromptTemplate.id == template_id,
                PromptTemplate.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        prompt_text: str,
        display_name_en: str,
        display_name_zh: str,
        category: str,
        description_en: str | None = None,
        description_zh: str | None = None,
        preview_image_url: str | None = None,
        tags: list[str] | None = None,
        style_keywords: list[str] | None = None,
        parameters: dict | None = None,
        difficulty: str = "beginner",
        media_type: str = "image",
        language: str = "bilingual",
        source: str = "curated",
        created_by: UUID | None = None,
    ) -> PromptTemplate:
        """Create a new template."""
        template = PromptTemplate(
            prompt_text=prompt_text,
            display_name_en=display_name_en,
            display_name_zh=display_name_zh,
            category=category,
            description_en=description_en,
            description_zh=description_zh,
            preview_image_url=preview_image_url,
            tags=tags or [],
            style_keywords=style_keywords or [],
            parameters=parameters or {},
            difficulty=difficulty,
            media_type=media_type,
            language=language,
            source=source,
            created_by=created_by,
        )
        self.session.add(template)
        await self.session.flush()
        return template

    async def update(
        self,
        template_id: UUID,
        **kwargs,
    ) -> PromptTemplate | None:
        """Update a template with arbitrary fields (partial update)."""
        template = await self.get_by_id(template_id)
        if not template:
            return None

        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)

        await self.session.flush()
        return template

    async def soft_delete(self, template_id: UUID) -> bool:
        """Soft-delete a template by setting deleted_at."""
        template = await self.get_by_id(template_id)
        if not template:
            return False

        template.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Listing / filtering / search
    # ------------------------------------------------------------------

    async def list_templates(
        self,
        category: str | None = None,
        tags: list[str] | None = None,
        difficulty: str | None = None,
        media_type: str | None = None,
        search: str | None = None,
        sort_by: str = "trending",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[PromptTemplate], int]:
        """List templates with multi-dimensional filtering, search, and sorting."""
        query = select(PromptTemplate).where(
            PromptTemplate.deleted_at.is_(None),
            PromptTemplate.is_active.is_(True),
        )

        if category:
            query = query.where(PromptTemplate.category == category)

        if tags:
            query = query.where(PromptTemplate.tags.overlap(tags))

        if difficulty:
            query = query.where(PromptTemplate.difficulty == difficulty)

        if media_type:
            query = query.where(PromptTemplate.media_type == media_type)

        if search:
            pattern = f"%{search}%"
            query = query.where(
                PromptTemplate.display_name_en.ilike(pattern)
                | PromptTemplate.display_name_zh.ilike(pattern)
                | PromptTemplate.prompt_text.ilike(pattern)
            )

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        # Sorting
        sort_map = {
            "trending": PromptTemplate.trending_score.desc(),
            "newest": PromptTemplate.created_at.desc(),
            "most_used": PromptTemplate.use_count.desc(),
            "most_liked": PromptTemplate.like_count.desc(),
        }
        order = sort_map.get(sort_by, PromptTemplate.trending_score.desc())
        query = query.order_by(order)

        # Pagination
        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        templates = list(result.scalars().all())

        return templates, total

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    async def get_categories_with_count(
        self, media_type: str | None = None
    ) -> list[tuple[str, int]]:
        """Get all categories with their active template counts."""
        query = (
            select(PromptTemplate.category, func.count().label("count"))
            .where(
                PromptTemplate.deleted_at.is_(None),
                PromptTemplate.is_active.is_(True),
            )
            .group_by(PromptTemplate.category)
            .order_by(func.count().desc())
        )
        if media_type:
            query = query.where(PromptTemplate.media_type == media_type)
        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    # ------------------------------------------------------------------
    # Like / Favorite toggles
    # ------------------------------------------------------------------

    async def is_liked(self, template_id: UUID, user_id: UUID) -> bool:
        """Check if a user has liked a template."""
        result = await self.session.execute(
            select(UserTemplateLike).where(
                UserTemplateLike.user_id == user_id,
                UserTemplateLike.template_id == template_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def is_favorited(self, template_id: UUID, user_id: UUID) -> bool:
        """Check if a user has favorited a template."""
        result = await self.session.execute(
            select(UserTemplateFavorite).where(
                UserTemplateFavorite.user_id == user_id,
                UserTemplateFavorite.template_id == template_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def toggle_like(self, template_id: UUID, user_id: UUID) -> tuple[str, int]:
        """Toggle like on a template. Returns (action, new_count)."""
        template = await self.get_by_id(template_id)
        if not template:
            raise ValueError("Template not found")

        existing = await self.session.execute(
            select(UserTemplateLike).where(
                UserTemplateLike.user_id == user_id,
                UserTemplateLike.template_id == template_id,
            )
        )

        if existing.scalar_one_or_none():
            # Remove like
            await self.session.execute(
                delete(UserTemplateLike).where(
                    UserTemplateLike.user_id == user_id,
                    UserTemplateLike.template_id == template_id,
                )
            )
            await self.session.execute(
                update(PromptTemplate)
                .where(PromptTemplate.id == template_id)
                .values(like_count=PromptTemplate.like_count - 1)
            )
            action = "removed"
        else:
            # Add like
            self.session.add(UserTemplateLike(user_id=user_id, template_id=template_id))
            await self.session.execute(
                update(PromptTemplate)
                .where(PromptTemplate.id == template_id)
                .values(like_count=PromptTemplate.like_count + 1)
            )
            action = "added"

        await self.session.flush()

        # Refresh trending score
        await self.refresh_trending_score(template_id)

        await self.session.refresh(template)
        return action, template.like_count

    async def toggle_favorite(self, template_id: UUID, user_id: UUID) -> tuple[str, int]:
        """Toggle favorite on a template. Returns (action, new_count)."""
        template = await self.get_by_id(template_id)
        if not template:
            raise ValueError("Template not found")

        existing = await self.session.execute(
            select(UserTemplateFavorite).where(
                UserTemplateFavorite.user_id == user_id,
                UserTemplateFavorite.template_id == template_id,
            )
        )

        if existing.scalar_one_or_none():
            # Remove favorite
            await self.session.execute(
                delete(UserTemplateFavorite).where(
                    UserTemplateFavorite.user_id == user_id,
                    UserTemplateFavorite.template_id == template_id,
                )
            )
            await self.session.execute(
                update(PromptTemplate)
                .where(PromptTemplate.id == template_id)
                .values(favorite_count=PromptTemplate.favorite_count - 1)
            )
            action = "removed"
        else:
            # Add favorite
            self.session.add(UserTemplateFavorite(user_id=user_id, template_id=template_id))
            await self.session.execute(
                update(PromptTemplate)
                .where(PromptTemplate.id == template_id)
                .values(favorite_count=PromptTemplate.favorite_count + 1)
            )
            action = "added"

        await self.session.flush()

        # Refresh trending score
        await self.refresh_trending_score(template_id)

        await self.session.refresh(template)
        return action, template.favorite_count

    # ------------------------------------------------------------------
    # User favorites list
    # ------------------------------------------------------------------

    async def get_user_favorites(
        self,
        user_id: UUID,
        media_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[PromptTemplate], int]:
        """Get user's favorited templates, paginated."""
        query = (
            select(PromptTemplate)
            .join(
                UserTemplateFavorite,
                UserTemplateFavorite.template_id == PromptTemplate.id,
            )
            .where(
                UserTemplateFavorite.user_id == user_id,
                PromptTemplate.deleted_at.is_(None),
            )
        )
        if media_type:
            query = query.where(PromptTemplate.media_type == media_type)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.order_by(UserTemplateFavorite.created_at.desc())
        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        templates = list(result.scalars().all())

        return templates, total

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    async def get_recommendations(
        self,
        based_on: UUID | None = None,
        tags: list[str] | None = None,
        media_type: str | None = None,
        limit: int = 10,
    ) -> list[PromptTemplate]:
        """Get recommended templates based on tags or a source template."""
        target_tags: list[str] = []

        if based_on:
            result = await self.session.execute(
                select(PromptTemplate.tags).where(
                    PromptTemplate.id == based_on,
                    PromptTemplate.deleted_at.is_(None),
                )
            )
            row = result.scalar_one_or_none()
            if row:
                target_tags = list(row)

        if tags:
            target_tags.extend(tags)

        if not target_tags:
            # Fallback: top trending
            query = (
                select(PromptTemplate)
                .where(
                    PromptTemplate.deleted_at.is_(None),
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.trending_score.desc())
                .limit(limit)
            )
            if media_type:
                query = query.where(PromptTemplate.media_type == media_type)
            result = await self.session.execute(query)
            return list(result.scalars().all())

        query = (
            select(PromptTemplate)
            .where(
                PromptTemplate.deleted_at.is_(None),
                PromptTemplate.is_active.is_(True),
                PromptTemplate.tags.overlap(target_tags),
            )
            .order_by(PromptTemplate.trending_score.desc())
            .limit(limit)
        )

        if based_on:
            query = query.where(PromptTemplate.id != based_on)

        if media_type:
            query = query.where(PromptTemplate.media_type == media_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    async def record_usage(
        self, template_id: UUID, user_id: UUID | None = None
    ) -> PromptTemplate | None:
        """Record template usage and increment use_count."""
        template = await self.get_by_id(template_id)
        if not template:
            return None

        # Insert usage record
        self.session.add(UserTemplateUsage(template_id=template_id, user_id=user_id))

        # Increment use_count
        await self.session.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .values(use_count=PromptTemplate.use_count + 1)
        )

        await self.session.flush()

        # Refresh trending score
        await self.refresh_trending_score(template_id)

        await self.session.refresh(template)
        return template

    # ------------------------------------------------------------------
    # Trending score
    # ------------------------------------------------------------------

    @staticmethod
    def compute_trending_score(
        like_count: int,
        use_count: int,
        favorite_count: int,
        created_at: datetime,
    ) -> float:
        """Compute trending score: (like*3 + use*1 + fav*2) / (hours + 2)^1.5"""
        now = datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        hours = (now - created_at).total_seconds() / 3600
        numerator = like_count * 3 + use_count * 1 + favorite_count * 2
        denominator = (hours + 2) ** 1.5
        return numerator / denominator

    async def refresh_trending_score(self, template_id: UUID) -> None:
        """Recompute and update the trending score for a single template."""
        result = await self.session.execute(
            select(PromptTemplate).where(PromptTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            return

        score = self.compute_trending_score(
            template.like_count,
            template.use_count,
            template.favorite_count,
            template.created_at,
        )
        await self.session.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .values(trending_score=score)
        )
        await self.session.flush()
