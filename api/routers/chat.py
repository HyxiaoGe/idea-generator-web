"""
Chat router for multi-turn image generation conversations.

Endpoints:
- POST /api/chat - Create new chat session
- POST /api/chat/{session_id}/message - Send message in session (async task)
- GET /api/chat/task/{task_id} - Poll chat task progress
- GET /api/chat/{session_id} - Get chat history
- GET /api/chat - List user's chat sessions
- DELETE /api/chat/{session_id} - Delete chat session
"""

import base64
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header

from api.dependencies import require_chat_repository
from api.schemas.chat import (
    AsyncChatResponse,
    ChatHistoryResponse,
    ChatMessage,
    ChatSessionInfo,
    ChatTaskProgress,
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from api.schemas.generate import GeneratedImage
from core.auth import AppUser, get_current_user
from core.config import get_settings
from core.exceptions import (
    QuotaExceededError,
    SessionNotFoundError,
    TaskNotFoundError,
    ValidationError,
)
from core.redis import get_redis
from database.repositories import ChatRepository
from services import (
    get_quota_service,
    get_storage_manager,
)
from services.chat_task import execute_chat_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ============ Helpers ============


def get_user_id_from_user(user: AppUser | None) -> str:
    """Get user ID for session storage."""
    if user:
        return user.user_folder_id
    return "anonymous"


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
    user: AppUser | None = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(require_chat_repository),
):
    """
    Create a new chat session for multi-turn image generation.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now()

    await chat_repo.create_session(
        id=uuid.UUID(session_id),
        initial_prompt=None,
        aspect_ratio=request.aspect_ratio.value,
        resolution="1K",
        user_id=None,  # TODO: map AppUser to DB user UUID
    )

    return CreateChatResponse(
        session_id=session_id,
        aspect_ratio=request.aspect_ratio.value,
        created_at=now,
    )


@router.post("/{session_id}/message", response_model=AsyncChatResponse)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user: AppUser | None = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(require_chat_repository),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """
    Send a message in an existing chat session.

    Returns a task_id immediately. Poll GET /api/chat/task/{task_id}
    or listen for WS chat:complete to get the result.
    """
    user_id = get_user_id_from_user(user)
    redis = await get_redis()

    # Load session with messages from DB
    db_session = await chat_repo.get_session_with_messages(uuid.UUID(session_id))
    if not db_session:
        raise SessionNotFoundError()

    # Build snapshot JSON for the background task
    messages_list = []
    for msg in db_session.messages:
        msg_dict = {
            "role": msg.role,
            "content": msg.content,
            "image_key": msg.image_url,
            "thinking": msg.thinking,
            "timestamp": msg.created_at.isoformat(),
        }
        if msg.thought_signature:
            msg_dict["thought_signature"] = base64.b64encode(msg.thought_signature).decode("ascii")
        messages_list.append(msg_dict)

    session_data = {
        "session_id": session_id,
        "aspect_ratio": db_session.aspect_ratio,
        "messages": messages_list,
    }
    session_json = json.dumps(session_data)

    # Check quota (before creating task)
    await check_chat_quota(user_id)

    # Resolve API key
    settings = get_settings()
    api_key = x_api_key or settings.get_google_api_key()

    if not api_key:
        raise ValidationError(message="No API key configured")

    # Create task in Redis
    task_id = f"chat_{uuid.uuid4().hex[:12]}"
    task_key = f"task:{task_id}"
    aspect_ratio = request.aspect_ratio.value if request.aspect_ratio else None

    await redis.hset(
        task_key,
        mapping={
            "status": "queued",
            "stage": "queued",
            "progress": "0.0",
            "user_id": user_id,
            "session_id": session_id,
            "message": request.message,
            "task_type": "chat",
            "created_at": datetime.now().isoformat(),
        },
    )
    # TTL: 1 hour for task data
    await redis.expire(task_key, 3600)

    # Launch background task with serialized session data snapshot
    background_tasks.add_task(
        execute_chat_task,
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        message=request.message,
        aspect_ratio=aspect_ratio,
        safety_level=request.safety_level,
        enable_thinking=request.enable_thinking,
        api_key=api_key,
        session_data_json=session_json,
    )

    return AsyncChatResponse(task_id=task_id, status="queued")


@router.get("/task/{task_id}", response_model=ChatTaskProgress)
async def get_chat_task_progress(task_id: str):
    """
    Poll the progress of a chat message task.
    """
    redis = await get_redis()
    task_data = await redis.hgetall(f"task:{task_id}")

    if not task_data:
        raise TaskNotFoundError()

    result = None
    if task_data.get("result_json"):
        result = SendMessageResponse.model_validate_json(task_data["result_json"])

    return ChatTaskProgress(
        task_id=task_id,
        status=task_data.get("status", "unknown"),
        stage=task_data.get("stage"),
        progress=float(task_data.get("progress", "0.0")),
        result=result,
        error=task_data.get("error"),
        error_code=task_data.get("error_code"),
        started_at=(
            datetime.fromisoformat(task_data["started_at"]) if task_data.get("started_at") else None
        ),
        completed_at=(
            datetime.fromisoformat(task_data["completed_at"])
            if task_data.get("completed_at")
            else None
        ),
    )


@router.get("/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    user: AppUser | None = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(require_chat_repository),
):
    """
    Get the conversation history for a chat session.
    """
    user_id = get_user_id_from_user(user)

    db_session = await chat_repo.get_session_with_messages(uuid.UUID(session_id))
    if not db_session:
        raise SessionNotFoundError()

    messages = []
    for msg in db_session.messages:
        image = None
        if msg.image_url:
            storage = get_storage_manager(user_id=user_id if user_id != "anonymous" else None)
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


@router.get("", response_model=ListChatsResponse)
async def list_chat_sessions(
    user: AppUser | None = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(require_chat_repository),
):
    """
    List all chat sessions for the current user.
    """
    db_sessions = await chat_repo.list_sessions_by_user(
        user_id=None,  # TODO: map AppUser to DB user UUID
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


@router.delete("/{session_id}")
async def delete_chat_session(
    session_id: str,
    user: AppUser | None = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(require_chat_repository),
):
    """
    Delete a chat session.
    """
    deleted = await chat_repo.delete_session(uuid.UUID(session_id))
    if not deleted:
        raise SessionNotFoundError()

    return {"success": True, "message": "Chat session deleted"}
