"""
Quota usage tracking model.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .image import GeneratedImage
    from .user import User


class QuotaUsage(Base):
    """
    Model for tracking per-user generation usage.

    Each row represents a single generation event.
    """

    __tablename__ = "quota_usage"

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

    # Usage details
    mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    points_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Optional metadata for analytics
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    resolution: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    media_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="image",
    )

    # Associated image
    image_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generated_images.id", ondelete="SET NULL"),
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
        back_populates="quota_usage",
    )
    image: Mapped[Optional["GeneratedImage"]] = relationship(
        "GeneratedImage",
        back_populates="quota_usage",
    )

    def __repr__(self) -> str:
        return (
            f"<QuotaUsage(id={self.id}, mode={self.mode}, "
            f"points={self.points_used}, provider={self.provider})>"
        )


# Indexes for analytics queries
Index("idx_quota_usage_user_date", QuotaUsage.user_id, QuotaUsage.created_at)
Index("idx_quota_usage_provider", QuotaUsage.provider)
Index("idx_quota_usage_media_type", QuotaUsage.media_type)
