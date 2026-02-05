"""
Pydantic schemas for favorites API.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# ============ Folder Schemas ============


class FolderInfo(BaseModel):
    """Favorite folder information."""

    id: str = Field(..., description="Folder ID")
    name: str = Field(..., description="Folder name")
    description: str | None = Field(None, description="Folder description")
    favorite_count: int = Field(default=0, description="Number of favorites in folder")
    created_at: datetime = Field(..., description="Creation timestamp")


class CreateFolderRequest(BaseModel):
    """Request for creating a folder."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Folder name",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Folder description",
    )


class CreateFolderResponse(BaseModel):
    """Response for creating a folder."""

    success: bool = True
    folder: FolderInfo


class ListFoldersResponse(BaseModel):
    """Response for listing folders."""

    folders: list[FolderInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of folders")


class UpdateFolderRequest(BaseModel):
    """Request for updating a folder."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New folder name",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="New folder description",
    )


class UpdateFolderResponse(BaseModel):
    """Response for updating a folder."""

    success: bool = True
    folder: FolderInfo


class DeleteFolderResponse(BaseModel):
    """Response for deleting a folder."""

    success: bool = True
    message: str = Field(default="Folder deleted successfully")


# ============ Favorite Schemas ============


class ImageInfo(BaseModel):
    """Basic image information for favorites."""

    id: str = Field(..., description="Image ID")
    filename: str = Field(..., description="Filename")
    prompt: str = Field(..., description="Generation prompt")
    url: str | None = Field(None, description="Image URL")
    thumbnail_url: str | None = Field(None, description="Thumbnail URL")
    created_at: datetime = Field(..., description="Image creation timestamp")


class FavoriteInfo(BaseModel):
    """Favorite information."""

    id: str = Field(..., description="Favorite ID")
    image: ImageInfo = Field(..., description="Image information")
    folder_id: str | None = Field(None, description="Folder ID if in a folder")
    folder_name: str | None = Field(None, description="Folder name if in a folder")
    note: str | None = Field(None, description="User note")
    created_at: datetime = Field(..., description="When the image was favorited")


class AddFavoriteRequest(BaseModel):
    """Request for adding a favorite."""

    image_id: str = Field(..., description="Image ID to favorite")
    folder_id: str | None = Field(
        default=None,
        description="Folder to add the favorite to",
    )
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional note",
    )


class AddFavoriteResponse(BaseModel):
    """Response for adding a favorite."""

    success: bool = True
    favorite: FavoriteInfo


class ListFavoritesResponse(BaseModel):
    """Response for listing favorites."""

    favorites: list[FavoriteInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of favorites")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more items exist")


class UpdateFavoriteRequest(BaseModel):
    """Request for updating a favorite."""

    folder_id: str | None = Field(
        default=None,
        description="Move to a different folder",
    )
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Update the note",
    )


class UpdateFavoriteResponse(BaseModel):
    """Response for updating a favorite."""

    success: bool = True
    favorite: FavoriteInfo


class DeleteFavoriteResponse(BaseModel):
    """Response for deleting a favorite."""

    success: bool = True
    message: str = Field(default="Favorite removed successfully")


# ============ Bulk Operations ============


class BulkFavoriteRequest(BaseModel):
    """Request for bulk favorite operations."""

    action: str = Field(
        ...,
        description="Action to perform: 'add', 'remove', 'move'",
    )
    image_ids: list[str] = Field(
        default_factory=list,
        description="Image IDs for add action",
    )
    favorite_ids: list[str] = Field(
        default_factory=list,
        description="Favorite IDs for remove/move actions",
    )
    folder_id: str | None = Field(
        default=None,
        description="Target folder for add/move actions",
    )


class BulkFavoriteResponse(BaseModel):
    """Response for bulk favorite operations."""

    success: bool = True
    processed: int = Field(..., description="Number of items processed")
    failed: int = Field(default=0, description="Number of items that failed")
    message: str = Field(..., description="Result message")
