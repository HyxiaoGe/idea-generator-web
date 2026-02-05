"""
Project repository for project and project image CRUD operations.
"""

from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Project, ProjectImage


class ProjectRepository:
    """Repository for Project model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Projects ============

    async def get_by_id(self, project_id: UUID) -> Project | None:
        """Get project by ID."""
        result = await self.session.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def get_by_id_with_images(self, project_id: UUID) -> Project | None:
        """Get project by ID with images loaded."""
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.project_images).selectinload(ProjectImage.image))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        name: str,
        description: str | None = None,
        settings: dict | None = None,
        is_public: bool = False,
        cover_url: str | None = None,
    ) -> Project:
        """Create a new project."""
        project = Project(
            user_id=user_id,
            name=name,
            description=description,
            settings=settings or {},
            is_public=is_public,
            cover_url=cover_url,
        )
        self.session.add(project)
        await self.session.flush()
        return project

    async def list_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List projects for a user."""
        result = await self.session.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(desc(Project.updated_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_public(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List public projects."""
        result = await self.session.execute(
            select(Project)
            .where(Project.is_public)
            .order_by(desc(Project.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        """Count projects for a user."""
        result = await self.session.execute(
            select(func.count()).select_from(Project).where(Project.user_id == user_id)
        )
        return result.scalar_one()

    async def update(
        self,
        project_id: UUID,
        name: str | None = None,
        description: str | None = None,
        settings: dict | None = None,
        is_public: bool | None = None,
        cover_url: str | None = None,
    ) -> Project | None:
        """Update a project."""
        project = await self.get_by_id(project_id)
        if not project:
            return None

        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if settings is not None:
            project.settings = settings
        if is_public is not None:
            project.is_public = is_public
        if cover_url is not None:
            project.cover_url = cover_url

        await self.session.flush()
        return project

    async def delete(self, project_id: UUID) -> bool:
        """Delete a project."""
        project = await self.get_by_id(project_id)
        if project:
            await self.session.delete(project)
            await self.session.flush()
            return True
        return False

    async def delete_by_user(self, user_id: UUID, project_id: UUID) -> bool:
        """Delete a project owned by a specific user."""
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id,
            )
        )
        project = result.scalar_one_or_none()
        if project:
            await self.session.delete(project)
            await self.session.flush()
            return True
        return False

    # ============ Project Images ============

    async def get_project_image(self, project_id: UUID, image_id: UUID) -> ProjectImage | None:
        """Get a project-image association."""
        result = await self.session.execute(
            select(ProjectImage).where(
                ProjectImage.project_id == project_id,
                ProjectImage.image_id == image_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_image(
        self,
        project_id: UUID,
        image_id: UUID,
        note: str | None = None,
        sort_order: int = 0,
    ) -> ProjectImage:
        """Add an image to a project."""
        project_image = ProjectImage(
            project_id=project_id,
            image_id=image_id,
            note=note,
            sort_order=sort_order,
        )
        self.session.add(project_image)
        await self.session.flush()
        return project_image

    async def list_images(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProjectImage]:
        """List images in a project."""
        result = await self.session.execute(
            select(ProjectImage)
            .options(selectinload(ProjectImage.image))
            .where(ProjectImage.project_id == project_id)
            .order_by(ProjectImage.sort_order, desc(ProjectImage.added_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_images(self, project_id: UUID) -> int:
        """Count images in a project."""
        result = await self.session.execute(
            select(func.count())
            .select_from(ProjectImage)
            .where(ProjectImage.project_id == project_id)
        )
        return result.scalar_one()

    async def update_image(
        self,
        project_id: UUID,
        image_id: UUID,
        note: str | None = None,
        sort_order: int | None = None,
    ) -> ProjectImage | None:
        """Update a project-image association."""
        project_image = await self.get_project_image(project_id, image_id)
        if not project_image:
            return None

        if note is not None:
            project_image.note = note
        if sort_order is not None:
            project_image.sort_order = sort_order

        await self.session.flush()
        return project_image

    async def remove_image(self, project_id: UUID, image_id: UUID) -> bool:
        """Remove an image from a project."""
        project_image = await self.get_project_image(project_id, image_id)
        if project_image:
            await self.session.delete(project_image)
            await self.session.flush()
            return True
        return False

    async def bulk_add_images(
        self,
        project_id: UUID,
        image_ids: list[UUID],
    ) -> list[ProjectImage]:
        """Add multiple images to a project."""
        project_images = []
        for i, image_id in enumerate(image_ids):
            existing = await self.get_project_image(project_id, image_id)
            if not existing:
                project_image = ProjectImage(
                    project_id=project_id,
                    image_id=image_id,
                    sort_order=i,
                )
                self.session.add(project_image)
                project_images.append(project_image)

        await self.session.flush()
        return project_images

    async def bulk_remove_images(self, project_id: UUID, image_ids: list[UUID]) -> int:
        """Remove multiple images from a project."""
        removed = 0
        for image_id in image_ids:
            project_image = await self.get_project_image(project_id, image_id)
            if project_image:
                await self.session.delete(project_image)
                removed += 1

        await self.session.flush()
        return removed
