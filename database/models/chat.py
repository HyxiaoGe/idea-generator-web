"""
Chat session and message models for multi-turn conversations.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .image import GeneratedImage
    from .user import User


class ChatSession(Base, TimestampMixin):
    """
    Model for chat sessions (multi-turn image generation conversations).

    Replaces the in-memory _sessions dictionary in ChatSessionManager.
    """

    __tablename__ = "chat_sessions"

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

    # Session configuration
    initial_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    aspect_ratio: Mapped[str] = mapped_column(
        String(20),
        default="1:1",
        nullable=False,
    )
    resolution: Mapped[str] = mapped_column(
        String(10),
        default="1K",
        nullable=False,
    )
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
        index=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Latest image for preview (denormalized for list queries)
    latest_image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="chat_sessions",
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sequence_number",
    )
    generated_images: Mapped[list["GeneratedImage"]] = relationship(
        "GeneratedImage",
        back_populates="chat_session",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, status={self.status}, messages={self.message_count})>"


class ChatMessage(Base):
    """
    Model for individual messages within a chat session.
    """

    __tablename__ = "chat_messages"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Session relationship
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Message content
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Associated image (for assistant responses)
    image_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generated_images.id", ondelete="SET NULL"),
        nullable=True,
    )
    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Thinking content (for assistant responses with reasoning)
    thinking: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Sequence number for ordering
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship(
        "ChatSession",
        back_populates="messages",
    )
    image: Mapped[Optional["GeneratedImage"]] = relationship(
        "GeneratedImage",
        back_populates="chat_message",
    )

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role}, seq={self.sequence_number})>"


# Indexes
Index("idx_chat_sessions_user_id", ChatSession.user_id)
Index("idx_chat_sessions_status", ChatSession.status)
Index("idx_chat_sessions_updated", ChatSession.updated_at.desc())
Index("idx_chat_messages_session", ChatMessage.session_id)
Index("idx_chat_messages_sequence", ChatMessage.session_id, ChatMessage.sequence_number)
