"""
Pydantic schemas for WebSocket messages.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WSMessageType(StrEnum):
    """WebSocket message types."""

    # Client → Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    GENERATE = "generate"
    CANCEL = "cancel"

    # Server → Client
    CONNECTED = "connected"
    PONG = "pong"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    ERROR = "error"

    # Task events
    TASK_PROGRESS = "task:progress"
    TASK_COMPLETE = "task:complete"
    TASK_ERROR = "task:error"

    # Generation events
    GENERATE_QUEUED = "generate:queued"
    GENERATE_PROGRESS = "generate:progress"
    GENERATE_COMPLETE = "generate:complete"
    GENERATE_ERROR = "generate:error"

    # Notifications
    NOTIFICATION = "notification"
    QUOTA_WARNING = "quota:warning"
    QUOTA_RESET = "quota:reset"


# ============ Client → Server Messages ============


class WSClientMessage(BaseModel):
    """Base client message."""

    type: WSMessageType = Field(..., description="Message type")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Message payload",
    )


class SubscribePayload(BaseModel):
    """Payload for subscribe message."""

    channel: str = Field(..., description="Channel to subscribe to")
    task_id: str | None = Field(None, description="Task ID for task channel")


class GeneratePayload(BaseModel):
    """Payload for generate message (WebSocket-based generation)."""

    prompt: str = Field(..., description="Generation prompt")
    aspect_ratio: str | None = Field(None, description="Aspect ratio")
    resolution: str | None = Field(None, description="Resolution")
    provider: str | None = Field(None, description="Preferred provider")
    mode: str = Field(default="basic", description="Generation mode")


class CancelPayload(BaseModel):
    """Payload for cancel message."""

    request_id: str = Field(..., description="Request ID to cancel")


# ============ Server → Client Messages ============


class WSServerMessage(BaseModel):
    """Base server message."""

    type: WSMessageType = Field(..., description="Message type")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Message payload",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Server timestamp",
    )


class ConnectedPayload(BaseModel):
    """Payload for connected message."""

    connection_id: str = Field(..., description="WebSocket connection ID")
    user_id: str | None = Field(None, description="Authenticated user ID")
    server_time: int = Field(
        ...,
        description="Server time as Unix timestamp (ms)",
    )


class PongPayload(BaseModel):
    """Payload for pong message."""

    server_time: int = Field(
        ...,
        description="Server time as Unix timestamp (ms)",
    )


class ErrorPayload(BaseModel):
    """Payload for error message."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    request_id: str | None = Field(None, description="Related request ID")


class TaskProgressPayload(BaseModel):
    """Payload for task progress message."""

    task_id: str = Field(..., description="Task ID")
    progress: int = Field(..., description="Current progress")
    total: int = Field(..., description="Total items")
    stage: str | None = Field(None, description="Current stage name")
    message: str | None = Field(None, description="Progress message")


class TaskCompletePayload(BaseModel):
    """Payload for task complete message."""

    task_id: str = Field(..., description="Task ID")
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Task results",
    )


class TaskErrorPayload(BaseModel):
    """Payload for task error message."""

    task_id: str = Field(..., description="Task ID")
    error: str = Field(..., description="Error message")
    code: str | None = Field(None, description="Error code")


class GenerateProgressPayload(BaseModel):
    """Payload for generate progress message."""

    request_id: str = Field(..., description="Request ID")
    stage: str = Field(..., description="Current stage (queued, generating, uploading)")
    progress: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Progress percentage (0-1)",
    )


class GenerateCompletePayload(BaseModel):
    """Payload for generate complete message."""

    request_id: str = Field(..., description="Request ID")
    image_id: str = Field(..., description="Generated image ID")
    url: str = Field(..., description="Image URL")
    prompt: str = Field(..., description="Generation prompt")
    provider: str = Field(..., description="Provider used")
    duration_ms: int = Field(..., description="Generation time in ms")


class GenerateErrorPayload(BaseModel):
    """Payload for generate error message."""

    request_id: str = Field(..., description="Request ID")
    error: str = Field(..., description="Error message")
    code: str | None = Field(None, description="Error code")


class NotificationPayload(BaseModel):
    """Payload for notification message."""

    id: str = Field(..., description="Notification ID")
    type: str = Field(..., description="Notification type")
    title: str = Field(..., description="Notification title")
    message: str | None = Field(None, description="Notification message")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional data",
    )


class QuotaWarningPayload(BaseModel):
    """Payload for quota warning message."""

    remaining: int = Field(..., description="Remaining quota")
    limit: int = Field(..., description="Total limit")
    resets_at: datetime | None = Field(None, description="When quota resets")
