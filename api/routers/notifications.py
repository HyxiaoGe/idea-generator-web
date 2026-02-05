"""
Notifications router for managing in-app notifications.

Endpoints:
- GET /api/notifications - List notifications
- GET /api/notifications/unread-count - Get unread count
- POST /api/notifications/mark-read - Mark notifications as read
- POST /api/notifications/mark-all-read - Mark all as read
- DELETE /api/notifications/{id} - Delete notification
"""

import contextlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_notification_repository, get_user_repository
from api.routers.auth import require_current_user
from api.schemas.notifications import (
    DeleteNotificationResponse,
    GetNotificationResponse,
    ListNotificationsResponse,
    MarkAllReadResponse,
    MarkReadRequest,
    MarkReadResponse,
    NotificationInfo,
    NotificationType,
    UnreadCountResponse,
)
from database.models import Notification
from database.repositories import NotificationRepository, UserRepository
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ============ Helpers ============


def notification_to_info(notification: Notification) -> NotificationInfo:
    """Convert database notification to response model."""
    return NotificationInfo(
        id=str(notification.id),
        type=NotificationType(notification.type),
        title=notification.title,
        message=notification.message,
        data=notification.data,
        is_read=notification.is_read,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


async def get_db_user_id(
    user: GitHubUser,
    user_repo: UserRepository | None,
) -> UUID:
    """Get database user ID from GitHub user."""
    if not user_repo:
        raise HTTPException(
            status_code=503,
            detail="Database not configured",
        )

    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return db_user.id


# ============ Endpoints ============


@router.get("", response_model=ListNotificationsResponse)
async def list_notifications(
    is_read: bool | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser = Depends(require_current_user),
    notification_repo: NotificationRepository | None = Depends(get_notification_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List notifications for the current user."""
    if not notification_repo:
        return ListNotificationsResponse(
            notifications=[],
            total=0,
            unread_count=0,
            limit=limit,
            offset=offset,
            has_more=False,
        )

    user_id = await get_db_user_id(user, user_repo)

    notifications = await notification_repo.list_by_user(
        user_id=user_id,
        is_read=is_read,
        type=type,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(notifications) > limit
    notifications = notifications[:limit]

    total = await notification_repo.count_by_user(user_id, is_read=is_read)
    unread_count = await notification_repo.count_unread(user_id)

    return ListNotificationsResponse(
        notifications=[notification_to_info(n) for n in notifications],
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: GitHubUser = Depends(require_current_user),
    notification_repo: NotificationRepository | None = Depends(get_notification_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get the count of unread notifications."""
    if not notification_repo:
        return UnreadCountResponse(unread_count=0)

    user_id = await get_db_user_id(user, user_repo)
    count = await notification_repo.count_unread(user_id)

    return UnreadCountResponse(unread_count=count)


@router.get("/{notification_id}", response_model=GetNotificationResponse)
async def get_notification(
    notification_id: str,
    user: GitHubUser = Depends(require_current_user),
    notification_repo: NotificationRepository | None = Depends(get_notification_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get a specific notification."""
    if not notification_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        notification_uuid = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID")

    user_id = await get_db_user_id(user, user_repo)

    notification = await notification_repo.get_by_id(notification_uuid)
    if not notification or notification.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    return GetNotificationResponse(notification=notification_to_info(notification))


@router.post("/mark-read", response_model=MarkReadResponse)
async def mark_read(
    request: MarkReadRequest,
    user: GitHubUser = Depends(require_current_user),
    notification_repo: NotificationRepository | None = Depends(get_notification_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Mark specific notifications as read."""
    if not notification_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    notification_uuids = []
    for nid in request.notification_ids:
        with contextlib.suppress(ValueError):
            notification_uuids.append(UUID(nid))

    marked = await notification_repo.mark_multiple_read(user_id, notification_uuids)

    return MarkReadResponse(
        success=True,
        marked_count=marked,
    )


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_read(
    user: GitHubUser = Depends(require_current_user),
    notification_repo: NotificationRepository | None = Depends(get_notification_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Mark all notifications as read."""
    if not notification_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)
    marked = await notification_repo.mark_all_read(user_id)

    return MarkAllReadResponse(
        success=True,
        marked_count=marked,
    )


@router.delete("/{notification_id}", response_model=DeleteNotificationResponse)
async def delete_notification(
    notification_id: str,
    user: GitHubUser = Depends(require_current_user),
    notification_repo: NotificationRepository | None = Depends(get_notification_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Delete a notification."""
    if not notification_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        notification_uuid = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID")

    user_id = await get_db_user_id(user, user_repo)

    deleted = await notification_repo.delete_by_user(user_id, notification_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")

    return DeleteNotificationResponse(success=True)
