"""
Template model for reusable prompt templates.
"""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class Template(Base, TimestampMixin):
    """
    Template model for reusable prompt templates.

    Templates contain prompt patterns with variables that can be filled in.
    """

    __tablename__ = "templates"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Owner (None for system templates)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Template name
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Description
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Prompt template with {{variable}} placeholders
    prompt_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Variable definitions
    # [{"name": "product_name", "type": "string", "required": true, "default": ""}]
    variables: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        server_default="[]",
    )

    # Default generation settings
    # {"aspect_ratio": "1:1", "resolution": "2K", "provider": "google"}
    default_settings: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default="{}",
    )

    # Category for organization
    category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    # Tags for search
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )

    # Visibility
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Usage tracking
    use_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Thumbnail/preview image URL
    preview_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationship
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="templates",
    )

    def __repr__(self) -> str:
        return f"<Template(id={self.id}, name={self.name})>"


# Indexes
Index("idx_templates_user_id", Template.user_id)
Index("idx_templates_category", Template.category)
Index("idx_templates_is_public", Template.is_public)
Index("idx_templates_use_count", Template.use_count.desc())
