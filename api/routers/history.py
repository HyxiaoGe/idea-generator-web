"""
History router for image history management.

Endpoints:
- GET /api/history - List history items
- GET /api/history/{item_id} - Get history item details
- DELETE /api/history/{item_id} - Delete history item
- GET /api/history/stats - Get history statistics
"""

import base64
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response

from services import ImageStorage, get_storage, get_r2_storage
from api.schemas.history import (
    HistoryItem,
    HistorySettings,
    HistoryListResponse,
    HistoryDetailResponse,
    HistoryDeleteResponse,
    HistoryStatsResponse,
)
from api.routers.auth import get_current_user
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])


# ============ Helpers ============

def get_user_id_from_user(user: Optional[GitHubUser]) -> Optional[str]:
    """Get user ID for storage access."""
    if user:
        return user.user_folder_id
    return None


def get_user_storage(user: Optional[GitHubUser]) -> ImageStorage:
    """Get storage instance for user."""
    user_id = get_user_id_from_user(user)
    return get_storage(user_id=user_id)


def record_to_history_item(record: dict, user_id: Optional[str] = None) -> HistoryItem:
    """Convert storage record to HistoryItem."""
    # Get URL from record or generate one
    url = record.get("r2_url") or record.get("url")
    if not url and record.get("r2_key"):
        r2 = get_r2_storage(user_id=user_id)
        url = r2.get_public_url(record["r2_key"])

    # Parse created_at
    created_at = record.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.now()
    elif not created_at:
        created_at = datetime.now()

    # Parse settings
    settings_data = record.get("settings", {})
    settings = HistorySettings(
        aspect_ratio=settings_data.get("aspect_ratio"),
        resolution=settings_data.get("resolution"),
    )

    return HistoryItem(
        id=record.get("key") or record.get("filename", ""),
        filename=record.get("filename", ""),
        prompt=record.get("prompt", ""),
        mode=record.get("mode", "basic"),
        settings=settings,
        duration=record.get("duration"),
        created_at=created_at,
        url=url,
        r2_key=record.get("r2_key") or record.get("key"),
        text_response=record.get("text_response"),
        thinking=record.get("thinking"),
        session_id=record.get("session_id"),
    )


# ============ Endpoints ============

@router.get("", response_model=HistoryListResponse)
async def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    mode: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    sort: str = Query(default="newest"),
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    List image generation history.

    Supports filtering by mode and search in prompts.
    """
    user_id = get_user_id_from_user(user)
    storage = get_user_storage(user)

    # Get history from storage
    # Request more items to handle offset/pagination
    all_items = storage.get_history(
        limit=offset + limit + 1,  # Get one extra to check has_more
        mode=mode,
        search=search,
    )

    # Apply offset
    items_slice = all_items[offset:offset + limit + 1]
    has_more = len(items_slice) > limit
    items_slice = items_slice[:limit]

    # Convert to response format
    items = [record_to_history_item(r, user_id) for r in items_slice]

    # Apply sort
    if sort == "oldest":
        items.sort(key=lambda x: x.created_at)
    else:  # newest (default)
        items.sort(key=lambda x: x.created_at, reverse=True)

    return HistoryListResponse(
        items=items,
        total=len(all_items),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/stats", response_model=HistoryStatsResponse)
async def get_history_stats(
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Get statistics about user's generation history.
    """
    user_id = get_user_id_from_user(user)
    storage = get_user_storage(user)

    # Get all history
    all_items = storage.get_history(limit=1000)

    if not all_items:
        return HistoryStatsResponse()

    # Calculate statistics
    total_images = len(all_items)
    total_duration = 0.0
    images_by_mode = {}
    dates = []

    for record in all_items:
        # Count by mode
        mode = record.get("mode", "basic")
        images_by_mode[mode] = images_by_mode.get(mode, 0) + 1

        # Sum duration
        duration = record.get("duration")
        if duration:
            total_duration += duration

        # Track dates
        created_at = record.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    dates.append(created_at)
                except ValueError:
                    pass
            elif isinstance(created_at, datetime):
                dates.append(created_at)

    average_duration = total_duration / total_images if total_images > 0 else 0.0

    return HistoryStatsResponse(
        total_images=total_images,
        images_by_mode=images_by_mode,
        total_duration=total_duration,
        average_duration=average_duration,
        earliest_date=min(dates) if dates else None,
        latest_date=max(dates) if dates else None,
    )


@router.get("/{item_id}", response_model=HistoryDetailResponse)
async def get_history_item(
    item_id: str,
    include_image: bool = Query(default=False, description="Include base64 image data"),
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Get detailed information about a history item.

    Optionally includes base64 encoded image data.
    """
    user_id = get_user_id_from_user(user)
    storage = get_user_storage(user)

    # Find the item
    record = storage.get_history_item(item_id)

    if not record:
        raise HTTPException(status_code=404, detail="History item not found")

    item = record_to_history_item(record, user_id)

    # Get image URL
    image_url = item.url
    if not image_url and item.r2_key:
        r2 = get_r2_storage(user_id=user_id)
        image_url = r2.get_public_url(item.r2_key)

    # Get base64 image data if requested
    image_base64 = None
    if include_image:
        image_bytes = storage.load_image_bytes(item_id)
        if image_bytes:
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    return HistoryDetailResponse(
        item=item,
        image_url=image_url,
        image_base64=image_base64,
    )


@router.get("/{item_id}/image")
async def get_history_image(
    item_id: str,
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Get the actual image file for a history item.

    Returns the image as a PNG file.
    """
    storage = get_user_storage(user)

    # Load image bytes
    image_bytes = storage.load_image_bytes(item_id)

    if not image_bytes:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{item_id}"'
        }
    )


@router.delete("/{item_id}", response_model=HistoryDeleteResponse)
async def delete_history_item(
    item_id: str,
    user: Optional[GitHubUser] = Depends(get_current_user),
):
    """
    Delete a history item.
    """
    user_id = get_user_id_from_user(user)
    storage = get_user_storage(user)

    # Check if item exists
    record = storage.get_history_item(item_id)
    if not record:
        raise HTTPException(status_code=404, detail="History item not found")

    # Delete from storage
    deleted = storage.delete_image(item_id)

    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete item")

    return HistoryDeleteResponse(
        success=True,
        deleted_count=1,
        message="Item deleted successfully",
    )
