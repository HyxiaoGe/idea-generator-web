"""
Image serving router.

Provides an endpoint to serve images when the storage backend
doesn't have a public URL (e.g., local file system).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from api.routers.auth import get_current_user
from services.auth_service import GitHubUser
from services.storage import get_storage_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


def get_user_id_from_user(user: GitHubUser | None) -> str | None:
    """Get user ID from authenticated user."""
    if user:
        return user.user_folder_id
    return None


@router.get("/{path:path}")
async def serve_image(
    path: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """
    Serve an image from storage.

    This endpoint acts as a proxy when the storage backend doesn't have
    a public URL configured (e.g., local file system storage).

    The path format is typically:
    - users/{user_id}/YYYY/MM/DD/mode_HHMMSS_slug.png
    - YYYY/MM/DD/mode_HHMMSS_slug.png (for anonymous users)

    Args:
        path: The storage key/path of the image

    Returns:
        Image file response
    """
    # Extract user_id from path if present
    user_id = get_user_id_from_user(user)

    # If path starts with "users/", extract user_id from path for storage access
    # This allows serving images for the correct user context
    path_user_id = None
    if path.startswith("users/"):
        parts = path.split("/", 2)
        if len(parts) >= 2:
            path_user_id = parts[1]

    # Use path_user_id if available, otherwise use authenticated user
    storage_user_id = path_user_id or user_id

    storage = get_storage_manager(user_id=storage_user_id)

    # Load image bytes
    data = await storage.load_image_bytes(path)

    if not data:
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine content type from file extension
    content_type = "image/png"
    path_lower = path.lower()
    if path_lower.endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif path_lower.endswith(".webp"):
        content_type = "image/webp"
    elif path_lower.endswith(".gif"):
        content_type = "image/gif"

    # Get filename for Content-Disposition
    filename = path.split("/")[-1]

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",  # 1 day cache
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
