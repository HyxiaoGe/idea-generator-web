"""
Prompt repository for prompt library CRUD operations.
"""

from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Prompt, UserFavoritePrompt


class PromptRepository:
    """Repository for Prompt and UserFavoritePrompt model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Prompt Operations ============

    async def get_by_id(self, prompt_id: UUID) -> Prompt | None:
        """Get prompt by ID."""
        result = await self.session.execute(select(Prompt).where(Prompt.id == prompt_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        category: str,
        text_en: str,
        text_zh: str | None = None,
        subcategory: str | None = None,
        tags: list[str] | None = None,
        difficulty: str | None = None,
        is_system: bool = True,
        created_by: UUID | None = None,
    ) -> Prompt:
        """Create a new prompt."""
        prompt = Prompt(
            category=category,
            text_en=text_en,
            text_zh=text_zh,
            subcategory=subcategory,
            tags=tags,
            difficulty=difficulty,
            is_system=is_system,
            created_by=created_by,
        )
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def list_by_category(
        self,
        category: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Prompt]:
        """List prompts by category."""
        query = select(Prompt).where(Prompt.category == category)
        query = query.order_by(desc(Prompt.use_count))
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_categories(self) -> list[str]:
        """Get all unique categories."""
        query = select(Prompt.category).distinct()
        result = await self.session.execute(query)
        return [row[0] for row in result]

    async def search(
        self,
        query_text: str,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[Prompt]:
        """Search prompts by text and filters."""
        query = select(Prompt).where(Prompt.text_en.ilike(f"%{query_text}%"))

        if category:
            query = query.where(Prompt.category == category)

        if tags:
            query = query.where(Prompt.tags.overlap(tags))

        query = query.order_by(desc(Prompt.use_count))
        query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_random(
        self,
        category: str | None = None,
        count: int = 1,
    ) -> list[Prompt]:
        """Get random prompts."""
        query = select(Prompt)

        if category:
            query = query.where(Prompt.category == category)

        query = query.order_by(func.random())
        query = query.limit(count)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def increment_use_count(self, prompt_id: UUID) -> Prompt | None:
        """Increment prompt usage count."""
        prompt = await self.get_by_id(prompt_id)
        if prompt:
            prompt.use_count += 1
            await self.session.flush()
        return prompt

    async def delete(self, prompt_id: UUID) -> bool:
        """Delete a prompt."""
        prompt = await self.get_by_id(prompt_id)
        if prompt:
            await self.session.delete(prompt)
            await self.session.flush()
            return True
        return False

    # ============ Favorite Operations ============

    async def add_favorite(self, user_id: UUID, prompt_id: UUID) -> bool:
        """Add a prompt to user's favorites."""
        # Check if already favorited
        existing = await self.session.execute(
            select(UserFavoritePrompt).where(
                and_(
                    UserFavoritePrompt.user_id == user_id,
                    UserFavoritePrompt.prompt_id == prompt_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            return False

        favorite = UserFavoritePrompt(
            user_id=user_id,
            prompt_id=prompt_id,
        )
        self.session.add(favorite)

        # Increment favorite count
        prompt = await self.get_by_id(prompt_id)
        if prompt:
            prompt.favorite_count += 1

        await self.session.flush()
        return True

    async def remove_favorite(self, user_id: UUID, prompt_id: UUID) -> bool:
        """Remove a prompt from user's favorites."""
        result = await self.session.execute(
            select(UserFavoritePrompt).where(
                and_(
                    UserFavoritePrompt.user_id == user_id,
                    UserFavoritePrompt.prompt_id == prompt_id,
                )
            )
        )
        favorite = result.scalar_one_or_none()

        if favorite:
            await self.session.delete(favorite)

            # Decrement favorite count
            prompt = await self.get_by_id(prompt_id)
            if prompt and prompt.favorite_count > 0:
                prompt.favorite_count -= 1

            await self.session.flush()
            return True

        return False

    async def list_favorites(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Prompt]:
        """List user's favorite prompts."""
        query = (
            select(Prompt)
            .join(UserFavoritePrompt)
            .where(UserFavoritePrompt.user_id == user_id)
            .order_by(desc(UserFavoritePrompt.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def is_favorited(self, user_id: UUID, prompt_id: UUID) -> bool:
        """Check if a prompt is in user's favorites."""
        result = await self.session.execute(
            select(UserFavoritePrompt).where(
                and_(
                    UserFavoritePrompt.user_id == user_id,
                    UserFavoritePrompt.prompt_id == prompt_id,
                )
            )
        )
        return result.scalar_one_or_none() is not None
