"""
Pydantic schemas for projects API.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectSettings(BaseModel):
    """Project-level settings."""

    default_aspect_ratio: str | None = Field(
        default=None,
        description="Default aspect ratio for this project",
    )
    default_resolution: str | None = Field(
        default=None,
        description="Default resolution for this project",
    )
    default_provider: str | None = Field(
        default=None,
        description="Default provider for this project",
    )


class ProjectImageInfo(BaseModel):
    """Image information within a project."""

    id: str = Field(..., description="Image ID")
    filename: str = Field(..., description="Filename")
    prompt: str = Field(..., description="Generation prompt")
    url: str | None = Field(None, description="Image URL")
    thumbnail_url: str | None = Field(None, description="Thumbnail URL")
    note: str | None = Field(None, description="Note about this image in the project")
    sort_order: int = Field(default=0, description="Sort order within project")
    added_at: datetime = Field(..., description="When added to project")
    created_at: datetime = Field(..., description="Image creation timestamp")


class ProjectInfo(BaseModel):
    """Project information."""

    id: str = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    description: str | None = Field(None, description="Project description")
    settings: ProjectSettings = Field(
        default_factory=ProjectSettings,
        description="Project settings",
    )
    is_public: bool = Field(default=False, description="Whether project is public")
    cover_url: str | None = Field(None, description="Cover image URL")
    image_count: int = Field(default=0, description="Number of images in project")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class ProjectListItem(BaseModel):
    """Abbreviated project info for list views."""

    id: str = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    description: str | None = Field(None, description="Project description")
    is_public: bool = Field(default=False, description="Whether project is public")
    cover_url: str | None = Field(None, description="Cover image URL")
    image_count: int = Field(default=0, description="Number of images in project")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ============ Request/Response Schemas ============


class CreateProjectRequest(BaseModel):
    """Request for creating a project."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Project name",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Project description",
    )
    settings: ProjectSettings | None = Field(
        default=None,
        description="Project settings",
    )
    is_public: bool = Field(
        default=False,
        description="Make project publicly visible",
    )


class CreateProjectResponse(BaseModel):
    """Response for creating a project."""

    success: bool = True
    project: ProjectInfo


class ListProjectsResponse(BaseModel):
    """Response for listing projects."""

    projects: list[ProjectListItem] = Field(default_factory=list)
    total: int = Field(..., description="Total number of projects")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more items exist")


class GetProjectResponse(BaseModel):
    """Response for getting a project."""

    project: ProjectInfo


class UpdateProjectRequest(BaseModel):
    """Request for updating a project."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Project name",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Project description",
    )
    settings: ProjectSettings | None = Field(
        default=None,
        description="Project settings",
    )
    is_public: bool | None = Field(
        default=None,
        description="Make project publicly visible",
    )
    cover_url: str | None = Field(
        default=None,
        description="Cover image URL",
    )


class UpdateProjectResponse(BaseModel):
    """Response for updating a project."""

    success: bool = True
    project: ProjectInfo


class DeleteProjectResponse(BaseModel):
    """Response for deleting a project."""

    success: bool = True
    message: str = Field(default="Project deleted successfully")


# ============ Project Images ============


class ListProjectImagesResponse(BaseModel):
    """Response for listing images in a project."""

    images: list[ProjectImageInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of images")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more items exist")


class AddProjectImageRequest(BaseModel):
    """Request for adding an image to a project."""

    image_id: str = Field(..., description="Image ID to add")
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Note about this image",
    )
    sort_order: int | None = Field(
        default=None,
        description="Sort order within project",
    )


class AddProjectImageResponse(BaseModel):
    """Response for adding an image to a project."""

    success: bool = True
    image: ProjectImageInfo


class UpdateProjectImageRequest(BaseModel):
    """Request for updating a project image."""

    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Note about this image",
    )
    sort_order: int | None = Field(
        default=None,
        description="Sort order within project",
    )


class UpdateProjectImageResponse(BaseModel):
    """Response for updating a project image."""

    success: bool = True
    image: ProjectImageInfo


class RemoveProjectImageResponse(BaseModel):
    """Response for removing an image from a project."""

    success: bool = True
    message: str = Field(default="Image removed from project")


class BulkAddProjectImagesRequest(BaseModel):
    """Request for adding multiple images to a project."""

    image_ids: list[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="Image IDs to add",
    )


class BulkAddProjectImagesResponse(BaseModel):
    """Response for adding multiple images."""

    success: bool = True
    added: int = Field(..., description="Number of images added")
    skipped: int = Field(default=0, description="Number of images skipped (already in project)")


# ============ Export ============


class ExportProjectRequest(BaseModel):
    """Request for exporting a project."""

    format: str = Field(
        default="zip",
        description="Export format (zip)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include metadata JSON file",
    )


class ExportProjectResponse(BaseModel):
    """Response for exporting a project."""

    success: bool = True
    download_url: str = Field(..., description="URL to download the export")
    expires_at: datetime = Field(..., description="When the download URL expires")
    file_size: int | None = Field(None, description="Export file size in bytes")
