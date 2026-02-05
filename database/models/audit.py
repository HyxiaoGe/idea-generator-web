"""
Audit and monitoring models for logging and provider health tracking.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User


class AuditLog(Base):
    """
    Model for audit logging of generation requests and content moderation.

    Replaces R2 storage-based audit logs with queryable database records.
    """

    __tablename__ = "audit_logs"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # User relationship (nullable for anonymous users)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Request information
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    method: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    # Content
    prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    filter_result: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    blocked_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Context
    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Associated image
    image_id: Mapped[UUID | None] = mapped_column(
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
        back_populates="audit_logs",
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, result={self.filter_result})>"


class ProviderHealthLog(Base):
    """
    Model for logging provider health and performance metrics.

    Used for adaptive routing and monitoring provider reliability.
    """

    __tablename__ = "provider_health_logs"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Provider information
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Result
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        index=True,
    )
    error_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Performance
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProviderHealthLog(id={self.id}, provider={self.provider}, success={self.success})>"
        )


# Indexes for audit queries
Index("idx_audit_user", AuditLog.user_id)
Index("idx_audit_action", AuditLog.action)
Index("idx_audit_filter", AuditLog.filter_result)
Index("idx_audit_created", AuditLog.created_at.desc())

# Indexes for health queries
Index("idx_health_provider", ProviderHealthLog.provider)
Index("idx_health_created", ProviderHealthLog.created_at.desc())
Index("idx_health_success", ProviderHealthLog.success)
