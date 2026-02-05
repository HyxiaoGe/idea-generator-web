"""
Prompt library models for storing and managing prompts.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User


class Prompt(Base):
    """
    Model for storing prompt library entries.

    Includes both system-provided prompts and user-created prompts.
    """

    __tablename__ = "prompts"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Classification
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    subcategory: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Content (multi-language support)
    text_en: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    text_zh: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Metadata
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)),
        nullable=True,
    )
    difficulty: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Statistics
    use_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
    )
    favorite_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Source
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by],
    )
    favorited_by: Mapped[list["UserFavoritePrompt"]] = relationship(
        "UserFavoritePrompt",
        back_populates="prompt",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Prompt(id={self.id}, category={self.category}, text={self.text_en[:30]}...)>"

    @property
    def text(self) -> str:
        """Get the primary (English) text."""
        return self.text_en


class UserFavoritePrompt(Base):
    """
    Association table for user favorite prompts.
    """

    __tablename__ = "user_favorite_prompts"

    # Composite primary key
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prompt_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="favorite_prompts",
    )
    prompt: Mapped["Prompt"] = relationship(
        "Prompt",
        back_populates="favorited_by",
    )

    def __repr__(self) -> str:
        return f"<UserFavoritePrompt(user_id={self.user_id}, prompt_id={self.prompt_id})>"


# Indexes
Index("idx_prompts_category", Prompt.category)
Index("idx_prompts_tags", Prompt.tags, postgresql_using="gin")
Index("idx_prompts_use_count", Prompt.use_count.desc())
Index("idx_favorites_user", UserFavoritePrompt.user_id)
