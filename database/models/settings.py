"""
User settings model for storing user preferences.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User


class UserSettings(Base):
    """
    User settings model for storing preferences and API settings.

    One-to-one relationship with User.
    """

    __tablename__ = "user_settings"

    # Primary key is user_id (one-to-one with users)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # User preferences (default resolution, aspect ratio, provider, etc.)
    preferences: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default="{}",
    )

    # API-specific settings (webhook URLs, etc.)
    api_settings: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default="{}",
    )

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship
    user: Mapped["User"] = relationship(
        "User",
        back_populates="settings",
    )

    def __repr__(self) -> str:
        return f"<UserSettings(user_id={self.user_id})>"
