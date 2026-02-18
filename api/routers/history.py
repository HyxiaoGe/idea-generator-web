"""
History router for image history management.

Endpoints:
- GET /api/history - List history items
- GET /api/history/{item_id} - Get history item details
- DELETE /api/history/{item_id} - Delete history item
- GET /api/history/stats - Get history statistics

Supports dual storage:
- PostgreSQL (if configured) for fast queries
- File storage (JSON) as fallback
"""

import base64
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.dependencies import get_image_repository
from api.schemas.history import (
    HistoryDeleteResponse,
    HistoryDetailResponse,
    HistoryItem,
    HistoryListResponse,
    HistorySettings,
    HistoryStatsResponse,
)
from core.auth import AppUser, get_current_user
from database.models import GeneratedImage
from database.repositories import ImageRepository
from services.storage import StorageManager, get_storage_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])


# ============ Helpers ============


def get_user_id_from_user(user: AppUser | None) -> str | None:
    """Get user ID for storage access."""
    if user:
        return user.user_folder_id
    return None


def get_user_storage(user: AppUser | None) -> StorageManager:
    """Get storage manager instance for user."""
    user_id = get_user_id_from_user(user)
    return get_storage_manager(user_id=user_id)


def record_to_history_item(record: dict, user_id: str | None = None) -> HistoryItem:
    """Convert storage record to HistoryItem."""
    # Get URL from record or generate one
    url = record.get("url") or record.get("r2_url")
    if not url and record.get("key"):
        storage = get_storage_manager(user_id=user_id)
        url = storage.get_public_url(record["key"])

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
        r2_key=record.get("key") or record.get("r2_key"),
        text_response=record.get("text_response"),
        thinking=record.get("thinking"),
        session_id=record.get("session_id"),
        provider=record.get("provider") or settings_data.get("provider"),
        model=record.get("model") or settings_data.get("model"),
    )


def db_image_to_history_item(image: GeneratedImage) -> HistoryItem:
    """Convert database GeneratedImage to HistoryItem."""
    settings = HistorySettings(
        aspect_ratio=image.aspect_ratio,
        resolution=image.resolution,
    )

    return HistoryItem(
        id=image.storage_key,
        filename=image.filename,
        prompt=image.prompt,
        mode=image.mode,
        settings=settings,
        duration=image.duration,
        created_at=image.created_at,
        url=image.public_url,
        r2_key=image.storage_key,
        text_response=image.text_response,
        thinking=image.thinking,
        session_id=str(image.chat_session_id) if image.chat_session_id else None,
        provider=image.provider,
        model=image.model,
    )


# ============ Endpoints ============


@router.get("", response_model=HistoryListResponse)
async def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    mode: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: str = Query(default="newest"),
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
):
    """
    List image generation history.

    Supports filtering by mode and search in prompts.
    Uses PostgreSQL if available, falls back to file storage.
    """
    user_id = get_user_id_from_user(user)

    # Try PostgreSQL first
    if image_repo:
        try:
            # Get from database (database user_id is UUID, not folder string)
            # For now, use None for anonymous users - proper mapping will need user sync
            db_user_id = None  # TODO: Map folder_id to UUID

            images = await image_repo.list_by_user(
                user_id=db_user_id,
                limit=limit + 1,  # +1 to check has_more
                offset=offset,
                mode=mode,
                search=search,
            )

            has_more = len(images) > limit
            images = images[:limit]

            # Get total count
            total = await image_repo.count_by_user(
                user_id=db_user_id,
                mode=mode,
                search=search,
            )

            # Convert to response format
            items = [db_image_to_history_item(img) for img in images]

            # Apply sort (database already sorts by newest)
            if sort == "oldest":
                items.reverse()

            return HistoryListResponse(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
                has_more=has_more,
            )
        except Exception as e:
            logger.warning(f"Database query failed, falling back to file storage: {e}")

    # Fallback to file storage
    storage = get_user_storage(user)

    # Get history from storage
    all_items = await storage.get_history(limit=offset + limit + 1)

    # Apply filters
    if mode:
        all_items = [r for r in all_items if r.get("mode") == mode]
    if search:
        search_lower = search.lower()
        all_items = [r for r in all_items if search_lower in r.get("prompt", "").lower()]

    # Apply offset
    items_slice = all_items[offset : offset + limit + 1]
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
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
):
    """
    Get statistics about user's generation history.
    """
    # Try PostgreSQL first
    if image_repo:
        try:
            db_user_id = None  # TODO: Map folder_id to UUID
            stats = await image_repo.get_stats_by_user(db_user_id)

            return HistoryStatsResponse(
                total_images=stats["total_images"],
                images_by_mode=stats["images_by_mode"],
                total_duration=stats["total_duration"],
                average_duration=stats["average_duration"],
                earliest_date=stats["earliest_date"],
                latest_date=stats["latest_date"],
            )
        except Exception as e:
            logger.warning(f"Database stats query failed, falling back to file storage: {e}")

    # Fallback to file storage
    storage = get_user_storage(user)

    # Get all history
    all_items = await storage.get_history(limit=1000)

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
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
):
    """
    Get detailed information about a history item.

    Optionally includes base64 encoded image data.
    """
    user_id = get_user_id_from_user(user)
    storage = get_user_storage(user)

    # Try PostgreSQL first (using storage_key)
    if image_repo:
        try:
            image = await image_repo.get_by_storage_key(item_id)
            if image:
                item = db_image_to_history_item(image)

                # Get image URL
                image_url = item.url
                if not image_url and item.r2_key:
                    image_url = storage.get_public_url(item.r2_key)

                # Get base64 image data if requested
                image_base64 = None
                if include_image:
                    image_bytes = await storage.load_image_bytes(item_id)
                    if image_bytes:
                        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                return HistoryDetailResponse(
                    item=item,
                    image_url=image_url,
                    image_base64=image_base64,
                )
        except Exception as e:
            logger.warning(f"Database lookup failed, falling back to file storage: {e}")

    # Fallback to file storage
    record = await storage.get_history_item(item_id)

    if not record:
        raise HTTPException(status_code=404, detail="History item not found")

    item = record_to_history_item(record, user_id)

    # Get image URL
    image_url = item.url
    if not image_url and item.r2_key:
        image_url = storage.get_public_url(item.r2_key)

    # Get base64 image data if requested
    image_base64 = None
    if include_image:
        image_bytes = await storage.load_image_bytes(item_id)
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
    user: AppUser | None = Depends(get_current_user),
):
    """
    Get the actual image file for a history item.

    Returns the image as a PNG file.
    """
    storage = get_user_storage(user)

    # Load image bytes
    image_bytes = await storage.load_image_bytes(item_id)

    if not image_bytes:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{item_id}"'},
    )


@router.delete("/{item_id}", response_model=HistoryDeleteResponse)
async def delete_history_item(
    item_id: str,
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
):
    """
    Delete a history item.
    """
    storage = get_user_storage(user)

    # Check if item exists (in file storage)
    record = await storage.get_history_item(item_id)
    if not record:
        raise HTTPException(status_code=404, detail="History item not found")

    # Delete from file storage
    deleted = await storage.delete_image(item_id)

    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete item")

    # Also delete from database if available
    if image_repo:
        try:
            await image_repo.delete_by_storage_key(item_id)
        except Exception as e:
            logger.warning(f"Failed to delete from database: {e}")
            # Don't fail - file deletion succeeded

    return HistoryDeleteResponse(
        success=True,
        deleted_count=1,
        message="Item deleted successfully",
    )
