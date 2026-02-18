"""
Admin announcements router.

Endpoints:
- GET /api/admin/announcements - List announcements
- POST /api/admin/announcements - Create announcement
- PUT /api/admin/announcements/{id} - Update announcement
- POST /api/admin/notifications/broadcast - Broadcast notification
"""

import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from api.schemas.admin import (
    AnnouncementInfo,
    AnnouncementResponse,
    BroadcastNotificationRequest,
    BroadcastNotificationResponse,
    CreateAnnouncementRequest,
    ListAnnouncementsResponse,
)
from core.auth import AppUser, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-announcements"])


# ============ In-memory storage (temporary) ============

_announcements: dict[str, AnnouncementInfo] = {}


# ============ Endpoints ============


@router.get("/announcements", response_model=ListAnnouncementsResponse)
async def list_announcements(
    admin: AppUser = Depends(require_admin),
):
    """List all announcements."""
    return ListAnnouncementsResponse(
        announcements=list(_announcements.values()),
        total=len(_announcements),
    )


@router.post("/announcements", response_model=AnnouncementResponse)
async def create_announcement(
    request: CreateAnnouncementRequest,
    admin: AppUser = Depends(require_admin),
):
    """Create a new announcement."""
    announcement_id = str(uuid4())

    announcement = AnnouncementInfo(
        id=announcement_id,
        title=request.title,
        content=request.content,
        type=request.type,
        is_active=True,
        starts_at=request.starts_at,
        ends_at=request.ends_at,
        target_tiers=request.target_tiers,
        created_at=datetime.now(),
    )

    _announcements[announcement_id] = announcement

    logger.info(f"Admin {admin.login} created announcement: {request.title}")

    return AnnouncementResponse(
        success=True,
        announcement=announcement,
    )


@router.put("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: str,
    request: CreateAnnouncementRequest,
    admin: AppUser = Depends(require_admin),
):
    """Update an announcement."""
    if announcement_id not in _announcements:
        raise HTTPException(status_code=404, detail="Announcement not found")

    existing = _announcements[announcement_id]

    announcement = AnnouncementInfo(
        id=announcement_id,
        title=request.title,
        content=request.content,
        type=request.type,
        is_active=existing.is_active,
        starts_at=request.starts_at,
        ends_at=request.ends_at,
        target_tiers=request.target_tiers,
        created_at=existing.created_at,
    )

    _announcements[announcement_id] = announcement

    return AnnouncementResponse(
        success=True,
        announcement=announcement,
    )


@router.post("/notifications/broadcast", response_model=BroadcastNotificationResponse)
async def broadcast_notification(
    request: BroadcastNotificationRequest,
    admin: AppUser = Depends(require_admin),
):
    """Broadcast a notification to multiple users."""
    # TODO: Implement actual notification broadcasting
    # This would:
    # 1. Create notification records in the database
    # 2. Send via WebSocket to connected users
    # 3. Queue for email delivery if configured

    logger.info(f"Admin {admin.login} broadcast notification: {request.title}")

    return BroadcastNotificationResponse(
        success=True,
        recipients=0,  # TODO: return actual count
        message="Notification broadcast queued",
    )
