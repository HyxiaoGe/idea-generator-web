"""
Chat-related Pydantic schemas for multi-turn image generation.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .generate import AspectRatio, GeneratedImage


class ChatMessage(BaseModel):
    """A single message in the chat conversation."""

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message text content")
    image: GeneratedImage | None = Field(None, description="Generated image if any")
    thinking: str | None = Field(None, description="Model thinking process")
    timestamp: datetime = Field(default_factory=datetime.now)


class CreateChatRequest(BaseModel):
    """Request to create a new chat session."""

    aspect_ratio: AspectRatio = Field(
        default=AspectRatio.LANDSCAPE, description="Default aspect ratio for the session"
    )


class CreateChatResponse(BaseModel):
    """Response for chat session creation."""

    session_id: str = Field(..., description="Unique chat session ID")
    aspect_ratio: str = Field(..., description="Session aspect ratio")
    created_at: datetime = Field(default_factory=datetime.now)


class SendMessageRequest(BaseModel):
    """Request to send a message in a chat session."""

    message: str = Field(..., min_length=1, max_length=2000, description="User message/prompt")
    aspect_ratio: AspectRatio | None = Field(
        None, description="Override aspect ratio for this message"
    )
    safety_level: str = Field(default="moderate", description="Safety filter level")
    enable_thinking: bool = Field(default=False, description="Enable model thinking process")


class SendMessageResponse(BaseModel):
    """Response from sending a chat message."""

    text: str | None = Field(None, description="Assistant text response")
    image: GeneratedImage | None = Field(None, description="Generated image")
    thinking: str | None = Field(None, description="Model thinking process")
    duration: float = Field(..., description="Response time in seconds")
    message_count: int = Field(..., description="Total messages in conversation")


class ChatSessionInfo(BaseModel):
    """Information about a chat session."""

    session_id: str = Field(..., description="Unique session ID")
    aspect_ratio: str = Field(..., description="Session aspect ratio")
    message_count: int = Field(..., description="Number of messages")
    created_at: datetime
    last_activity: datetime


class ChatHistoryResponse(BaseModel):
    """Response containing chat history."""

    session_id: str = Field(..., description="Session ID")
    messages: list[ChatMessage] = Field(default_factory=list)
    aspect_ratio: str = Field(..., description="Session aspect ratio")


class ListChatsResponse(BaseModel):
    """Response listing user's chat sessions."""

    sessions: list[ChatSessionInfo] = Field(default_factory=list)
    total: int = Field(default=0)


class AsyncChatResponse(BaseModel):
    """POST /api/chat/{id}/message async mode response."""

    task_id: str = Field(..., description="Task ID for polling")
    status: str = Field(default="queued", description="Initial task status")
    message: str = Field(default="Chat message queued", description="Status message")


class ChatTaskProgress(BaseModel):
    """GET /api/chat/task/{task_id} polling response."""

    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="queued / generating / completed / failed")
    stage: str | None = Field(None, description="loading_history / thinking / saving")
    progress: float = Field(default=0.0, description="Progress 0.0-1.0")
    result: SendMessageResponse | None = Field(None, description="Full result when completed")
    error: str | None = Field(None, description="Error message if failed")
    error_code: str | None = Field(None, description="Machine-readable error code")
    started_at: datetime | None = Field(None, description="When task started")
    completed_at: datetime | None = Field(None, description="When task completed")
