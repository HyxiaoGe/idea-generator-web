"""
Chat repository for chat session and message CRUD operations.
"""

from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import ChatMessage, ChatSession


class ChatRepository:
    """Repository for ChatSession and ChatMessage model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Session Operations ============

    async def get_session_by_id(
        self,
        session_id: UUID,
        include_messages: bool = False,
    ) -> ChatSession | None:
        """Get chat session by ID."""
        query = select(ChatSession).where(ChatSession.id == session_id)

        if include_messages:
            query = query.options(selectinload(ChatSession.messages))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_session(
        self,
        initial_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        provider: str | None = None,
        user_id: UUID | None = None,
    ) -> ChatSession:
        """Create a new chat session."""
        chat_session = ChatSession(
            initial_prompt=initial_prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            provider=provider,
            user_id=user_id,
            status="active",
            message_count=0,
        )
        self.session.add(chat_session)
        await self.session.flush()
        return chat_session

    async def list_sessions_by_user(
        self,
        user_id: UUID | None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChatSession]:
        """List chat sessions for a user."""
        query = select(ChatSession).where(ChatSession.user_id == user_id)

        if status:
            query = query.where(ChatSession.status == status)

        query = query.order_by(desc(ChatSession.updated_at))
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_session_status(
        self,
        session_id: UUID,
        status: str,
    ) -> ChatSession | None:
        """Update session status (active, archived, deleted)."""
        chat_session = await self.get_session_by_id(session_id)
        if chat_session:
            chat_session.status = status
            await self.session.flush()
        return chat_session

    async def update_session_latest_image(
        self,
        session_id: UUID,
        image_url: str,
    ) -> ChatSession | None:
        """Update session's latest image URL."""
        chat_session = await self.get_session_by_id(session_id)
        if chat_session:
            chat_session.latest_image_url = image_url
            await self.session.flush()
        return chat_session

    async def increment_message_count(
        self,
        session_id: UUID,
    ) -> ChatSession | None:
        """Increment session's message count."""
        chat_session = await self.get_session_by_id(session_id)
        if chat_session:
            chat_session.message_count += 1
            await self.session.flush()
        return chat_session

    async def delete_session(self, session_id: UUID) -> bool:
        """Delete a chat session (cascades to messages)."""
        chat_session = await self.get_session_by_id(session_id)
        if chat_session:
            await self.session.delete(chat_session)
            await self.session.flush()
            return True
        return False

    # ============ Message Operations ============

    async def get_message_by_id(self, message_id: UUID) -> ChatMessage | None:
        """Get chat message by ID."""
        result = await self.session.execute(select(ChatMessage).where(ChatMessage.id == message_id))
        return result.scalar_one_or_none()

    async def create_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        image_id: UUID | None = None,
        image_url: str | None = None,
    ) -> ChatMessage:
        """Create a new chat message."""
        # Get next sequence number
        seq_query = select(func.coalesce(func.max(ChatMessage.sequence_number), 0) + 1)
        seq_query = seq_query.where(ChatMessage.session_id == session_id)
        seq_result = await self.session.execute(seq_query)
        sequence_number = seq_result.scalar_one()

        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            image_id=image_id,
            image_url=image_url,
            sequence_number=sequence_number,
        )
        self.session.add(message)
        await self.session.flush()

        # Update session message count
        await self.increment_message_count(session_id)

        return message

    async def list_messages_by_session(
        self,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessage]:
        """List messages for a session in order."""
        query = select(ChatMessage).where(ChatMessage.session_id == session_id)
        query = query.order_by(ChatMessage.sequence_number)
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_session_with_messages(
        self,
        session_id: UUID,
    ) -> ChatSession | None:
        """Get session with all messages loaded."""
        return await self.get_session_by_id(session_id, include_messages=True)

    async def count_messages_by_session(self, session_id: UUID) -> int:
        """Count messages in a session."""
        query = select(func.count()).select_from(ChatMessage)
        query = query.where(ChatMessage.session_id == session_id)
        result = await self.session.execute(query)
        return result.scalar_one()
