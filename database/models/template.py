"""
PromptTemplate model for the prompt template library.

Replaces the old simple Template model with a full-featured prompt library system
including bilingual support, engagement metrics, and trending scores.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class PromptTemplate(Base, TimestampMixin):
    """
    Prompt template for the image generation template library.

    Features bilingual display names, engagement tracking (likes, favorites, usage),
    trending score computation, and soft-delete support.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index(
            "ix_prompt_templates_category",
            "category",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_prompt_templates_trending",
            "trending_score",
            postgresql_where=text("deleted_at IS NULL AND is_active = TRUE"),
        ),
        Index(
            "ix_prompt_templates_tags",
            "tags",
            postgresql_using="gin",
        ),
        Index(
            "ix_prompt_templates_use_count",
            "use_count",
            postgresql_where=text("deleted_at IS NULL AND is_active = TRUE"),
        ),
        Index(
            "ix_prompt_templates_media_type",
            "media_type",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Core prompt content
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Bilingual display
    display_name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name_zh: Mapped[str] = mapped_column(String(200), nullable=False)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_zh: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Preview
    preview_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Classification
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default=text("'{}'::varchar[]"),
        nullable=False,
    )
    style_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default=text("'{}'::varchar[]"),
        nullable=False,
    )

    # Parameters / metadata
    parameters: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="bilingual", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="curated", nullable=False)
    media_type: Mapped[str] = mapped_column(
        String(20), default="image", server_default=text("'image'"), nullable=False
    )

    # Engagement metrics
    use_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    like_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    favorite_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    trending_score: Mapped[float] = mapped_column(
        Float, default=0.0, server_default=text("0.0"), nullable=False
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Creator (FK to users, nullable for system/seed templates)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationship
    creator: Mapped["User | None"] = relationship(
        "User",
        back_populates="templates",
    )

    def __repr__(self) -> str:
        return f"<PromptTemplate(id={self.id}, name={self.display_name_en})>"
