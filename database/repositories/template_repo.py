"""
Template repository for template CRUD operations.
"""

from uuid import UUID

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Template


class TemplateRepository:
    """Repository for Template model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, template_id: UUID) -> Template | None:
        """Get template by ID."""
        result = await self.session.execute(select(Template).where(Template.id == template_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        prompt_template: str,
        user_id: UUID | None = None,
        description: str | None = None,
        variables: list[dict] | None = None,
        default_settings: dict | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        is_public: bool = False,
        preview_url: str | None = None,
    ) -> Template:
        """Create a new template."""
        template = Template(
            user_id=user_id,
            name=name,
            description=description,
            prompt_template=prompt_template,
            variables=variables or [],
            default_settings=default_settings or {},
            category=category,
            tags=tags,
            is_public=is_public,
            preview_url=preview_url,
        )
        self.session.add(template)
        await self.session.flush()
        return template

    async def list_by_user(
        self,
        user_id: UUID,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Template]:
        """List templates owned by a user."""
        query = select(Template).where(Template.user_id == user_id)

        if category:
            query = query.where(Template.category == category)

        query = query.order_by(desc(Template.created_at)).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_public(
        self,
        category: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Template]:
        """List public templates."""
        query = select(Template).where(Template.is_public)

        if category:
            query = query.where(Template.category == category)

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Template.name.ilike(search_pattern),
                    Template.description.ilike(search_pattern),
                )
            )

        # Sort by popularity (use_count) then recency
        query = (
            query.order_by(desc(Template.use_count), desc(Template.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_accessible(
        self,
        user_id: UUID | None,
        category: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Template]:
        """List templates accessible to a user (own + public)."""
        if user_id:
            query = select(Template).where(
                or_(
                    Template.user_id == user_id,
                    Template.is_public,
                )
            )
        else:
            query = select(Template).where(Template.is_public)

        if category:
            query = query.where(Template.category == category)

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Template.name.ilike(search_pattern),
                    Template.description.ilike(search_pattern),
                )
            )

        query = query.order_by(desc(Template.created_at)).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        """Count templates owned by a user."""
        result = await self.session.execute(
            select(func.count()).select_from(Template).where(Template.user_id == user_id)
        )
        return result.scalar_one()

    async def count_public(self) -> int:
        """Count public templates."""
        result = await self.session.execute(
            select(func.count()).select_from(Template).where(Template.is_public)
        )
        return result.scalar_one()

    async def update(
        self,
        template_id: UUID,
        name: str | None = None,
        description: str | None = None,
        prompt_template: str | None = None,
        variables: list[dict] | None = None,
        default_settings: dict | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        is_public: bool | None = None,
        preview_url: str | None = None,
    ) -> Template | None:
        """Update a template."""
        template = await self.get_by_id(template_id)
        if not template:
            return None

        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if prompt_template is not None:
            template.prompt_template = prompt_template
        if variables is not None:
            template.variables = variables
        if default_settings is not None:
            template.default_settings = default_settings
        if category is not None:
            template.category = category
        if tags is not None:
            template.tags = tags
        if is_public is not None:
            template.is_public = is_public
        if preview_url is not None:
            template.preview_url = preview_url

        await self.session.flush()
        return template

    async def increment_use_count(self, template_id: UUID) -> None:
        """Increment the use count for a template."""
        await self.session.execute(
            update(Template)
            .where(Template.id == template_id)
            .values(use_count=Template.use_count + 1)
        )
        await self.session.flush()

    async def delete(self, template_id: UUID) -> bool:
        """Delete a template."""
        template = await self.get_by_id(template_id)
        if template:
            await self.session.delete(template)
            await self.session.flush()
            return True
        return False

    async def delete_by_user(self, user_id: UUID, template_id: UUID) -> bool:
        """Delete a template owned by a specific user."""
        result = await self.session.execute(
            select(Template).where(
                Template.id == template_id,
                Template.user_id == user_id,
            )
        )
        template = result.scalar_one_or_none()
        if template:
            await self.session.delete(template)
            await self.session.flush()
            return True
        return False

    async def get_categories(self, user_id: UUID | None = None) -> list[str]:
        """Get distinct categories for templates."""
        if user_id:
            query = (
                select(Template.category)
                .where(
                    or_(
                        Template.user_id == user_id,
                        Template.is_public,
                    )
                )
                .where(Template.category.isnot(None))
                .distinct()
            )
        else:
            query = (
                select(Template.category)
                .where(Template.is_public)
                .where(Template.category.isnot(None))
                .distinct()
            )

        result = await self.session.execute(query)
        return [row[0] for row in result.all()]
