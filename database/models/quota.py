"""
Quota usage model for tracking generation quota consumption.
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
    Model for tracking quota usage history.

    Supplements Redis real-time quota tracking with persistent records
    for analytics and historical queries.
    """

    __tablename__ = "quota_usage"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # User relationship (nullable for anonymous/trial users)
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
        return f"<QuotaUsage(id={self.id}, mode={self.mode}, points={self.points_used})>"


# Indexes for analytics queries
Index("idx_quota_usage_user_id", QuotaUsage.user_id)
Index("idx_quota_usage_created", QuotaUsage.created_at)
Index("idx_quota_usage_mode", QuotaUsage.mode)
