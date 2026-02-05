"""
Pydantic schemas for notifications API.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NotificationType(StrEnum):
    """Types of notifications."""

    SYSTEM = "system"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    QUOTA_WARNING = "quota_warning"
    QUOTA_RESET = "quota_reset"
    ANNOUNCEMENT = "announcement"
    FEATURE = "feature"


class NotificationInfo(BaseModel):
    """Notification information."""

    id: str = Field(..., description="Notification ID")
    type: NotificationType = Field(..., description="Notification type")
    title: str = Field(..., description="Notification title")
    message: str | None = Field(None, description="Notification message")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional data (links, actions, etc.)",
    )
    is_read: bool = Field(default=False, description="Whether notification is read")
    read_at: datetime | None = Field(None, description="When notification was read")
    created_at: datetime = Field(..., description="Creation timestamp")


class NotificationListItem(BaseModel):
    """Abbreviated notification for list views."""

    id: str = Field(..., description="Notification ID")
    type: NotificationType = Field(..., description="Notification type")
    title: str = Field(..., description="Notification title")
    is_read: bool = Field(default=False, description="Whether notification is read")
    created_at: datetime = Field(..., description="Creation timestamp")


# ============ Request/Response Schemas ============


class ListNotificationsResponse(BaseModel):
    """Response for listing notifications."""

    notifications: list[NotificationInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of notifications")
    unread_count: int = Field(..., description="Number of unread notifications")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more items exist")


class UnreadCountResponse(BaseModel):
    """Response for getting unread count."""

    unread_count: int = Field(..., description="Number of unread notifications")


class MarkReadRequest(BaseModel):
    """Request for marking notifications as read."""

    notification_ids: list[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="Notification IDs to mark as read",
    )


class MarkReadResponse(BaseModel):
    """Response for marking notifications as read."""

    success: bool = True
    marked_count: int = Field(..., description="Number of notifications marked as read")


class MarkAllReadResponse(BaseModel):
    """Response for marking all notifications as read."""

    success: bool = True
    marked_count: int = Field(..., description="Number of notifications marked as read")


class DeleteNotificationResponse(BaseModel):
    """Response for deleting a notification."""

    success: bool = True
    message: str = Field(default="Notification deleted successfully")


class GetNotificationResponse(BaseModel):
    """Response for getting a single notification."""

    notification: NotificationInfo
