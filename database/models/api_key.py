"""
API Key model for user-generated API keys.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class APIKey(Base, TimestampMixin):
    """
    API Key model for programmatic access.

    Keys are stored as hashed values for security.
    Only the prefix is stored in plaintext for identification.
    """

    __tablename__ = "api_keys"

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

    # Key identification
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Hashed key value (SHA-256)
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    # Key prefix for identification (e.g., "nb_sk_abc...")
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    # Scopes/permissions
    scopes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )

    # Usage tracking
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Expiration (optional)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationship
    user: Mapped["User"] = relationship(
        "User",
        back_populates="api_keys",
    )

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"

    @property
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    @property
    def masked_key(self) -> str:
        """Return masked key for display (e.g., nb_sk_abc...xyz)."""
        return f"{self.key_prefix}..."


# Indexes
Index("idx_api_keys_user_id", APIKey.user_id)
Index("idx_api_keys_key_hash", APIKey.key_hash)
