"""
Notification model for in-app notifications.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class Notification(Base, TimestampMixin):
    """
    Notification model for in-app notifications.

    Supports various notification types with optional data payload.
    """

    __tablename__ = "notifications"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Recipient
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Notification type (system, quota_warning, task_complete, etc.)
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Title and message
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Additional data (links, action buttons, etc.)
    data: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default="{}",
    )

    # Read status
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    # When the notification was read
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationship
    user: Mapped["User"] = relationship(
        "User",
        back_populates="notifications",
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.type}, is_read={self.is_read})>"


# Indexes
Index("idx_notifications_user_id", Notification.user_id)
Index("idx_notifications_type", Notification.type)
Index("idx_notifications_is_read", Notification.is_read)
Index("idx_notifications_created_at", Notification.created_at.desc())
# Composite index for common query: unread notifications for user
Index("idx_notifications_user_unread", Notification.user_id, Notification.is_read)
