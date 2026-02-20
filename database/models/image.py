"""
GeneratedImage model for storing image generation history.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .chat import ChatMessage, ChatSession
    from .favorite import Favorite
    from .project import ProjectImage
    from .quota import QuotaUsage
    from .user import User


class GeneratedImage(Base):
    """
    Model for storing generated image metadata and history.

    Replaces the history.json file storage.
    """

    __tablename__ = "generated_images"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # User relationship (nullable for anonymous users)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Storage information
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    storage_backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="local",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    public_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Generation parameters
    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="basic",
        index=True,
    )
    aspect_ratio: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    resolution: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    # Provider information
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Image metadata
    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    content_type: Mapped[str] = mapped_column(
        String(50),
        default="image/png",
        nullable=False,
    )
    media_type: Mapped[str] = mapped_column(
        String(20),
        default="image",
        server_default="image",
        nullable=False,
        index=True,
    )

    # Performance data
    generation_duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Additional generation outputs
    text_response: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    thinking: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Associations (for chat/batch generations)
    chat_session_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="generated_images",
    )
    chat_session: Mapped[Optional["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="generated_images",
    )
    chat_message: Mapped[Optional["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="image",
        uselist=False,
    )
    quota_usage: Mapped[Optional["QuotaUsage"]] = relationship(
        "QuotaUsage",
        back_populates="image",
        uselist=False,
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        "Favorite",
        back_populates="image",
        cascade="all, delete-orphan",
    )
    project_images: Mapped[list["ProjectImage"]] = relationship(
        "ProjectImage",
        back_populates="image",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<GeneratedImage(id={self.id}, mode={self.mode}, prompt={self.prompt[:30]}...)>"

    @property
    def duration(self) -> float | None:
        """Get duration in seconds (for backward compatibility)."""
        if self.generation_duration_ms is not None:
            return self.generation_duration_ms / 1000.0
        return None

    @duration.setter
    def duration(self, value: float | None) -> None:
        """Set duration from seconds."""
        if value is not None:
            self.generation_duration_ms = int(value * 1000)
        else:
            self.generation_duration_ms = None


# Indexes for common queries
Index("idx_images_user_id", GeneratedImage.user_id)
Index("idx_images_created_at", GeneratedImage.created_at.desc())
Index("idx_images_mode", GeneratedImage.mode)
Index("idx_images_provider", GeneratedImage.provider)
Index("idx_images_chat_session", GeneratedImage.chat_session_id)
