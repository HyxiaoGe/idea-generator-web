"""
Project models for organizing images into workspaces.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .image import GeneratedImage
    from .user import User


class Project(Base, TimestampMixin):
    """
    Project model for organizing images into workspaces.

    Projects can contain multiple images and have shared settings.
    """

    __tablename__ = "projects"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Owner
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Project name
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Description
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Project settings
    # {"default_aspect_ratio": "16:9", "default_resolution": "1K", "default_provider": "google"}
    settings: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default="{}",
    )

    # Visibility
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Cover image URL
    cover_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="projects",
    )
    project_images: Mapped[list["ProjectImage"]] = relationship(
        "ProjectImage",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name})>"


class ProjectImage(Base):
    """
    Association table for project-image relationships.

    Includes additional metadata about when the image was added.
    """

    __tablename__ = "project_images"

    # Composite primary key
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    image_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # When the image was added to the project
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Optional note about the image in this project context
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Sort order within the project
    sort_order: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="project_images",
    )
    image: Mapped["GeneratedImage"] = relationship(
        "GeneratedImage",
        back_populates="project_images",
    )

    def __repr__(self) -> str:
        return f"<ProjectImage(project_id={self.project_id}, image_id={self.image_id})>"


# Indexes
Index("idx_projects_user_id", Project.user_id)
Index("idx_projects_is_public", Project.is_public)
Index("idx_project_images_project_id", ProjectImage.project_id)
Index("idx_project_images_image_id", ProjectImage.image_id)
