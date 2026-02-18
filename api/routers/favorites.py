"""
Favorites router for bookmarking generated images.

Endpoints:
- GET /api/favorites - List favorites
- POST /api/favorites - Add favorite
- DELETE /api/favorites/{id} - Remove favorite
- POST /api/favorites/bulk - Bulk operations
- GET /api/favorites/folders - List folders
- POST /api/favorites/folders - Create folder
- PUT /api/favorites/folders/{id} - Update folder
- DELETE /api/favorites/folders/{id} - Delete folder
"""

import contextlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_favorite_repository, get_user_repository
from api.schemas.favorites import (
    AddFavoriteRequest,
    AddFavoriteResponse,
    BulkFavoriteRequest,
    BulkFavoriteResponse,
    CreateFolderRequest,
    CreateFolderResponse,
    DeleteFavoriteResponse,
    DeleteFolderResponse,
    FavoriteInfo,
    FolderInfo,
    ImageInfo,
    ListFavoritesResponse,
    ListFoldersResponse,
    UpdateFolderRequest,
    UpdateFolderResponse,
)
from core.auth import AppUser, require_current_user
from database.models import Favorite, FavoriteFolder
from database.repositories import FavoriteRepository, UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/favorites", tags=["favorites"])


# ============ Helpers ============


def folder_to_info(folder: FavoriteFolder, favorite_count: int = 0) -> FolderInfo:
    """Convert database folder to response model."""
    return FolderInfo(
        id=str(folder.id),
        name=folder.name,
        description=folder.description,
        favorite_count=favorite_count,
        created_at=folder.created_at,
    )


def favorite_to_info(favorite: Favorite) -> FavoriteInfo:
    """Convert database favorite to response model."""
    image = favorite.image
    image_info = ImageInfo(
        id=str(image.id),
        filename=image.filename,
        prompt=image.prompt,
        url=image.public_url,
        thumbnail_url=None,  # TODO: implement thumbnails
        created_at=image.created_at,
    )

    folder_name = None
    if favorite.folder:
        folder_name = favorite.folder.name

    return FavoriteInfo(
        id=str(favorite.id),
        image=image_info,
        folder_id=str(favorite.folder_id) if favorite.folder_id else None,
        folder_name=folder_name,
        note=favorite.note,
        created_at=favorite.created_at,
    )


async def get_db_user_id(
    user: AppUser,
    user_repo: UserRepository | None,
) -> UUID:
    """Get database user ID from GitHub user."""
    if not user_repo:
        raise HTTPException(
            status_code=503,
            detail="Database not configured",
        )

    db_user = await user_repo.get_by_auth_id(user.id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return db_user.id


# ============ Folder Endpoints ============


@router.get("/folders", response_model=ListFoldersResponse)
async def list_folders(
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List all favorite folders for the current user."""
    if not favorite_repo:
        return ListFoldersResponse(folders=[], total=0)

    user_id = await get_db_user_id(user, user_repo)
    folders = await favorite_repo.list_folders_by_user(user_id)

    # Get counts for each folder
    folder_infos = []
    for folder in folders:
        count = await favorite_repo.count_by_user(user_id, folder_id=folder.id)
        folder_infos.append(folder_to_info(folder, count))

    return ListFoldersResponse(
        folders=folder_infos,
        total=len(folder_infos),
    )


@router.post("/folders", response_model=CreateFolderResponse)
async def create_folder(
    request: CreateFolderRequest,
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Create a new favorite folder."""
    if not favorite_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    folder = await favorite_repo.create_folder(
        user_id=user_id,
        name=request.name,
        description=request.description,
    )

    return CreateFolderResponse(
        success=True,
        folder=folder_to_info(folder, 0),
    )


@router.put("/folders/{folder_id}", response_model=UpdateFolderResponse)
async def update_folder(
    folder_id: str,
    request: UpdateFolderRequest,
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Update a favorite folder."""
    if not favorite_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    try:
        folder_uuid = UUID(folder_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid folder ID")

    # Verify ownership
    folder = await favorite_repo.get_folder_by_id(folder_uuid)
    if not folder or folder.user_id != user_id:
        raise HTTPException(status_code=404, detail="Folder not found")

    updated = await favorite_repo.update_folder(
        folder_id=folder_uuid,
        name=request.name,
        description=request.description,
    )

    count = await favorite_repo.count_by_user(user_id, folder_id=folder_uuid)

    return UpdateFolderResponse(
        success=True,
        folder=folder_to_info(updated, count),
    )


@router.delete("/folders/{folder_id}", response_model=DeleteFolderResponse)
async def delete_folder(
    folder_id: str,
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Delete a favorite folder."""
    if not favorite_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    try:
        folder_uuid = UUID(folder_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid folder ID")

    # Verify ownership
    folder = await favorite_repo.get_folder_by_id(folder_uuid)
    if not folder or folder.user_id != user_id:
        raise HTTPException(status_code=404, detail="Folder not found")

    await favorite_repo.delete_folder(folder_uuid)

    return DeleteFolderResponse(success=True)


# ============ Favorite Endpoints ============


@router.get("", response_model=ListFavoritesResponse)
async def list_favorites(
    folder_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List favorites for the current user."""
    if not favorite_repo:
        return ListFavoritesResponse(
            favorites=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
        )

    user_id = await get_db_user_id(user, user_repo)

    folder_uuid = None
    if folder_id:
        try:
            folder_uuid = UUID(folder_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid folder ID")

    favorites = await favorite_repo.list_by_user(
        user_id=user_id,
        folder_id=folder_uuid,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(favorites) > limit
    favorites = favorites[:limit]

    total = await favorite_repo.count_by_user(user_id, folder_id=folder_uuid)

    return ListFavoritesResponse(
        favorites=[favorite_to_info(f) for f in favorites],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post("", response_model=AddFavoriteResponse)
async def add_favorite(
    request: AddFavoriteRequest,
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Add an image to favorites."""
    if not favorite_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    try:
        image_uuid = UUID(request.image_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid image ID")

    folder_uuid = None
    if request.folder_id:
        try:
            folder_uuid = UUID(request.folder_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid folder ID")

    # Check if already favorited
    existing = await favorite_repo.get_by_user_and_image(user_id, image_uuid)
    if existing:
        raise HTTPException(status_code=409, detail="Image already favorited")

    favorite = await favorite_repo.create(
        user_id=user_id,
        image_id=image_uuid,
        folder_id=folder_uuid,
        note=request.note,
    )

    # Re-fetch to get image relationship
    favorite = await favorite_repo.get_by_id(favorite.id)

    return AddFavoriteResponse(
        success=True,
        favorite=favorite_to_info(favorite),
    )


@router.delete("/{favorite_id}", response_model=DeleteFavoriteResponse)
async def delete_favorite(
    favorite_id: str,
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Remove a favorite."""
    if not favorite_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    try:
        favorite_uuid = UUID(favorite_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid favorite ID")

    # Verify ownership
    favorite = await favorite_repo.get_by_id(favorite_uuid)
    if not favorite or favorite.user_id != user_id:
        raise HTTPException(status_code=404, detail="Favorite not found")

    await favorite_repo.delete(favorite_uuid)

    return DeleteFavoriteResponse(success=True)


@router.post("/bulk", response_model=BulkFavoriteResponse)
async def bulk_favorite_operation(
    request: BulkFavoriteRequest,
    user: AppUser = Depends(require_current_user),
    favorite_repo: FavoriteRepository | None = Depends(get_favorite_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Perform bulk operations on favorites."""
    if not favorite_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)

    folder_uuid = None
    if request.folder_id:
        try:
            folder_uuid = UUID(request.folder_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid folder ID")

    if request.action == "add":
        # Bulk add favorites
        image_uuids = []
        for image_id in request.image_ids:
            with contextlib.suppress(ValueError):
                image_uuids.append(UUID(image_id))

        created = await favorite_repo.bulk_create(
            user_id=user_id,
            image_ids=image_uuids,
            folder_id=folder_uuid,
        )

        return BulkFavoriteResponse(
            success=True,
            processed=len(created),
            failed=len(request.image_ids) - len(created),
            message=f"Added {len(created)} favorites",
        )

    elif request.action == "remove":
        # Bulk remove favorites
        favorite_uuids = []
        for fav_id in request.favorite_ids:
            with contextlib.suppress(ValueError):
                favorite_uuids.append(UUID(fav_id))

        deleted = await favorite_repo.bulk_delete(user_id, favorite_uuids)

        return BulkFavoriteResponse(
            success=True,
            processed=deleted,
            failed=len(request.favorite_ids) - deleted,
            message=f"Removed {deleted} favorites",
        )

    elif request.action == "move":
        # Move favorites to folder
        moved = 0
        for fav_id in request.favorite_ids:
            try:
                fav_uuid = UUID(fav_id)
                favorite = await favorite_repo.get_by_id(fav_uuid)
                if favorite and favorite.user_id == user_id:
                    await favorite_repo.update(fav_uuid, folder_id=folder_uuid)
                    moved += 1
            except ValueError:
                pass

        return BulkFavoriteResponse(
            success=True,
            processed=moved,
            failed=len(request.favorite_ids) - moved,
            message=f"Moved {moved} favorites",
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid action")
