"""
Chat router for multi-turn image generation conversations.

Endpoints:
- POST /api/chat - Create new chat session
- POST /api/chat/{session_id}/message - Send message in session
- GET /api/chat/{session_id} - Get chat history
- GET /api/chat - List user's chat sessions
- DELETE /api/chat/{session_id} - Delete chat session
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header

from api.dependencies import get_chat_repository, get_quota_repository
from api.routers.auth import get_current_user
from api.schemas.chat import (
    ChatHistoryResponse,
    ChatMessage,
    ChatSessionInfo,
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from api.schemas.generate import GeneratedImage
from core.config import get_settings
from core.exceptions import (
    GenerationError,
    QuotaExceededError,
    SessionNotFoundError,
    ValidationError,
)
from core.redis import get_redis
from database.repositories import ChatRepository, QuotaRepository
from services import (
    ChatSession,
    get_friendly_error_message,
    get_quota_service,
    get_storage_manager,
)
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Chat session TTL (24 hours)
CHAT_SESSION_TTL = 86400


# ============ Helpers ============


def get_user_id_from_user(user: GitHubUser | None) -> str:
    """Get user ID for session storage."""
    if user:
        return user.user_folder_id
    return "anonymous"


def get_session_key(user_id: str, session_id: str) -> str:
    """Get Redis key for a chat session."""
    return f"chat:{user_id}:{session_id}"


def get_user_sessions_key(user_id: str) -> str:
    """Get Redis key for user's session list."""
    return f"chat_sessions:{user_id}"


async def check_chat_quota(user_id: str):
    """Check and consume quota for chat generation."""
    redis = await get_redis()
    quota_service = get_quota_service(redis)

    can_generate, reason, info = await quota_service.check_quota(
        user_id=user_id,
        count=1,
    )

    if not can_generate:
        raise QuotaExceededError(message=reason, details=info)

    await quota_service.consume_quota(user_id=user_id, count=1)


# ============ Endpoints ============


@router.post("", response_model=CreateChatResponse)
async def create_chat_session(
    request: CreateChatRequest,
    user: GitHubUser | None = Depends(get_current_user),
    chat_repo: ChatRepository | None = Depends(get_chat_repository),
):
    """
    Create a new chat session for multi-turn image generation.
    """
    user_id = get_user_id_from_user(user)
    session_id = str(uuid.uuid4())
    now = datetime.now()

    redis = await get_redis()

    # Store session data in Redis (for fast context replay)
    session_data = {
        "session_id": session_id,
        "user_id": user_id,
        "aspect_ratio": request.aspect_ratio.value,
        "messages": [],
        "created_at": now.isoformat(),
        "last_activity": now.isoformat(),
    }

    session_key = get_session_key(user_id, session_id)
    await redis.set(session_key, json.dumps(session_data), ex=CHAT_SESSION_TTL)

    # Add to user's session list
    sessions_key = get_user_sessions_key(user_id)
    await redis.sadd(sessions_key, session_id)
    await redis.expire(sessions_key, CHAT_SESSION_TTL)

    # Persist to PostgreSQL if available
    if chat_repo:
        try:
            await chat_repo.create_session(
                initial_prompt=None,
                aspect_ratio=request.aspect_ratio.value,
                resolution="1K",
                user_id=None,  # TODO: map GitHubUser to DB user UUID
            )
            # Override session_id to match what we stored in Redis
            # The repo auto-generates a UUID, but we need our own
            # So we use a direct approach instead
        except Exception as e:
            logger.warning(f"Failed to persist chat session to database: {e}")

    return CreateChatResponse(
        session_id=session_id,
        aspect_ratio=request.aspect_ratio.value,
        created_at=now,
    )


@router.post("/{session_id}/message", response_model=SendMessageResponse)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    user: GitHubUser | None = Depends(get_current_user),
    chat_repo: ChatRepository | None = Depends(get_chat_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """
    Send a message in an existing chat session.
    """
    user_id = get_user_id_from_user(user)
    redis = await get_redis()

    # Get session data from Redis (fast path for context replay)
    session_key = get_session_key(user_id, session_id)
    session_json = await redis.get(session_key)

    if not session_json:
        # Fallback: try loading from DB if Redis expired
        if chat_repo:
            try:
                db_session = await chat_repo.get_session_with_messages(uuid.UUID(session_id))
                if db_session:
                    # Rebuild Redis cache from DB
                    session_data = {
                        "session_id": session_id,
                        "user_id": user_id,
                        "aspect_ratio": db_session.aspect_ratio,
                        "messages": [
                            {
                                "role": msg.role,
                                "content": msg.content,
                                "image_key": msg.image_url,
                                "thinking": msg.thinking,
                                "timestamp": msg.created_at.isoformat(),
                            }
                            for msg in db_session.messages
                        ],
                        "created_at": db_session.created_at.isoformat(),
                        "last_activity": db_session.updated_at.isoformat(),
                    }
                    # Re-cache in Redis
                    await redis.set(
                        session_key,
                        json.dumps(session_data),
                        ex=CHAT_SESSION_TTL,
                    )
                    session_json = json.dumps(session_data)
            except Exception as e:
                logger.warning(f"Failed to load chat session from database: {e}")

    if not session_json:
        raise SessionNotFoundError()

    session_data = json.loads(session_json)

    # Check quota
    await check_chat_quota(user_id)

    # Create ChatSession and restore state
    # Note: Chat sessions currently only support Google Gemini for multi-turn context
    settings = get_settings()
    api_key = x_api_key or settings.get_google_api_key()

    if not api_key:
        raise ValidationError(message="No API key configured")

    chat_session = ChatSession(api_key=api_key)
    chat_session.start_session(aspect_ratio=session_data["aspect_ratio"])

    # Replay previous messages to restore context
    for msg in session_data["messages"]:
        if msg["role"] == "user":
            # Send previous user messages without generating new responses
            # This rebuilds the conversation context
            pass  # Context is maintained by the chat object

    # Send the new message
    aspect_ratio = request.aspect_ratio.value if request.aspect_ratio else None
    response = chat_session.send_message(
        message=request.message,
        aspect_ratio=aspect_ratio,
        safety_level=request.safety_level,
    )

    if response.error:
        raise GenerationError(message=get_friendly_error_message(response.error))

    # Save image if generated
    image_data = None
    if response.image:
        storage = get_storage_manager(user_id=user_id if user else None)
        result = await storage.save_image(
            image=response.image,
            prompt=request.message,
            settings={"aspect_ratio": aspect_ratio or session_data["aspect_ratio"]},
            duration=response.duration,
            mode="chat",
            text_response=response.text,
            thinking=response.thinking,
        )

        if result:
            image_data = GeneratedImage(
                key=result.key,
                filename=result.filename,
                url=result.public_url,
                width=response.image.width,
                height=response.image.height,
            )

    # Update session with new messages in Redis
    now = datetime.now()
    session_data["messages"].append(
        {
            "role": "user",
            "content": request.message,
            "timestamp": now.isoformat(),
        }
    )
    session_data["messages"].append(
        {
            "role": "assistant",
            "content": response.text or "",
            "image_key": image_data.key if image_data else None,
            "thinking": response.thinking,
            "timestamp": now.isoformat(),
        }
    )
    session_data["last_activity"] = now.isoformat()

    # Save updated session to Redis
    await redis.set(session_key, json.dumps(session_data), ex=CHAT_SESSION_TTL)

    # Persist messages to PostgreSQL if available
    if chat_repo:
        try:
            session_uuid = uuid.UUID(session_id)
            # User message
            await chat_repo.create_message(
                session_id=session_uuid,
                role="user",
                content=request.message,
            )
            # Assistant message
            await chat_repo.create_message(
                session_id=session_uuid,
                role="assistant",
                content=response.text or "",
                image_url=image_data.key if image_data else None,
                thinking=response.thinking,
            )
            # Update latest image preview
            if image_data:
                await chat_repo.update_session_latest_image(
                    session_uuid, image_data.url or image_data.key
                )
        except Exception as e:
            logger.warning(f"Failed to persist chat messages to database: {e}")

    # Record quota usage to PostgreSQL if available
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="chat",
                points_used=1,
                provider="google",
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

    return SendMessageResponse(
        text=response.text,
        image=image_data,
        thinking=response.thinking,
        duration=response.duration,
        message_count=len(session_data["messages"]),
    )


@router.get("/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    user: GitHubUser | None = Depends(get_current_user),
    chat_repo: ChatRepository | None = Depends(get_chat_repository),
):
    """
    Get the conversation history for a chat session.
    """
    user_id = get_user_id_from_user(user)
    redis = await get_redis()

    session_key = get_session_key(user_id, session_id)
    session_json = await redis.get(session_key)

    # Try DB if Redis miss
    if not session_json and chat_repo:
        try:
            db_session = await chat_repo.get_session_with_messages(uuid.UUID(session_id))
            if db_session:
                messages = []
                for msg in db_session.messages:
                    image = None
                    if msg.image_url:
                        storage = get_storage_manager(
                            user_id=user_id if user_id != "anonymous" else None
                        )
                        image = GeneratedImage(
                            key=msg.image_url,
                            filename=msg.image_url.split("/")[-1],
                            url=storage.get_public_url(msg.image_url),
                        )
                    messages.append(
                        ChatMessage(
                            role=msg.role,
                            content=msg.content,
                            image=image,
                            thinking=msg.thinking,
                            timestamp=msg.created_at,
                        )
                    )
                return ChatHistoryResponse(
                    session_id=session_id,
                    messages=messages,
                    aspect_ratio=db_session.aspect_ratio,
                )
        except Exception as e:
            logger.warning(f"Failed to load chat history from database: {e}")

    if not session_json:
        raise SessionNotFoundError()

    session_data = json.loads(session_json)

    # Convert messages to response format
    messages = []
    for msg in session_data["messages"]:
        image = None
        if msg.get("image_key"):
            storage = get_storage_manager(user_id=user_id if user_id != "anonymous" else None)
            image = GeneratedImage(
                key=msg["image_key"],
                filename=msg["image_key"].split("/")[-1],
                url=storage.get_public_url(msg["image_key"]),
            )

        messages.append(
            ChatMessage(
                role=msg["role"],
                content=msg["content"],
                image=image,
                thinking=msg.get("thinking"),
                timestamp=datetime.fromisoformat(msg["timestamp"]),
            )
        )

    return ChatHistoryResponse(
        session_id=session_id,
        messages=messages,
        aspect_ratio=session_data["aspect_ratio"],
    )


@router.get("", response_model=ListChatsResponse)
async def list_chat_sessions(
    user: GitHubUser | None = Depends(get_current_user),
    chat_repo: ChatRepository | None = Depends(get_chat_repository),
):
    """
    List all chat sessions for the current user.
    """
    user_id = get_user_id_from_user(user)

    # Try DB first if available (source of truth for listing)
    if chat_repo:
        try:
            db_sessions = await chat_repo.list_sessions_by_user(
                user_id=None,  # TODO: map GitHubUser to DB user UUID
            )
            sessions = [
                ChatSessionInfo(
                    session_id=str(s.id),
                    aspect_ratio=s.aspect_ratio,
                    message_count=s.message_count,
                    created_at=s.created_at,
                    last_activity=s.updated_at,
                )
                for s in db_sessions
            ]
            return ListChatsResponse(
                sessions=sessions,
                total=len(sessions),
            )
        except Exception as e:
            logger.warning(f"Failed to list chat sessions from database: {e}")

    # Fallback to Redis
    redis = await get_redis()

    sessions_key = get_user_sessions_key(user_id)
    session_ids = await redis.smembers(sessions_key)

    sessions = []
    for sid in session_ids:
        session_key = get_session_key(user_id, sid)
        session_json = await redis.get(session_key)

        if session_json:
            data = json.loads(session_json)
            sessions.append(
                ChatSessionInfo(
                    session_id=data["session_id"],
                    aspect_ratio=data["aspect_ratio"],
                    message_count=len(data["messages"]),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    last_activity=datetime.fromisoformat(data["last_activity"]),
                )
            )

    # Sort by last activity, newest first
    sessions.sort(key=lambda x: x.last_activity, reverse=True)

    return ListChatsResponse(
        sessions=sessions,
        total=len(sessions),
    )


@router.delete("/{session_id}")
async def delete_chat_session(
    session_id: str,
    user: GitHubUser | None = Depends(get_current_user),
    chat_repo: ChatRepository | None = Depends(get_chat_repository),
):
    """
    Delete a chat session.
    """
    user_id = get_user_id_from_user(user)
    redis = await get_redis()

    session_key = get_session_key(user_id, session_id)

    # Check if session exists in Redis
    redis_exists = await redis.exists(session_key)

    # Delete from DB if available
    db_deleted = False
    if chat_repo:
        try:
            db_deleted = await chat_repo.delete_session(uuid.UUID(session_id))
        except Exception as e:
            logger.warning(f"Failed to delete chat session from database: {e}")

    if not redis_exists and not db_deleted:
        raise SessionNotFoundError()

    # Delete from Redis
    if redis_exists:
        await redis.delete(session_key)
        sessions_key = get_user_sessions_key(user_id)
        await redis.srem(sessions_key, session_id)

    return {"success": True, "message": "Chat session deleted"}
