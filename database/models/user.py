"""
User model for storing user information from GitHub OAuth.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .api_key import APIKey
    from .audit import AuditLog
    from .chat import ChatSession
    from .favorite import Favorite, FavoriteFolder
    from .image import GeneratedImage
    from .notification import Notification
    from .project import Project
    from .quota import QuotaUsage
    from .template import PromptTemplate
    from .user_preferences import UserPreference


class User(Base, TimestampMixin):
    """
    User model representing authenticated users.

    Users are created/updated during GitHub OAuth login.
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # GitHub OAuth info
    github_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Quota settings
    tier: Mapped[str] = mapped_column(
        String(50),
        default="free",
        nullable=False,
    )
    custom_quota_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        default=Decimal("1.0"),
        nullable=False,
    )

    # Last login tracking
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    generated_images: Mapped[list["GeneratedImage"]] = relationship(
        "GeneratedImage",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    quota_usage: Mapped[list["QuotaUsage"]] = relationship(
        "QuotaUsage",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
    )
    preferences: Mapped["UserPreference | None"] = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        "Favorite",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    favorite_folders: Mapped[list["FavoriteFolder"]] = relationship(
        "FavoriteFolder",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    templates: Mapped[list["PromptTemplate"]] = relationship(
        "PromptTemplate",
        back_populates="creator",
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, github_id={self.github_id})>"

    @property
    def user_folder_id(self) -> str:
        """Get the folder ID used for storage (matches auth service format)."""
        return f"u_{self.github_id}"


# Indexes
Index("idx_users_github_id", User.github_id)
Index("idx_users_username", User.username)
