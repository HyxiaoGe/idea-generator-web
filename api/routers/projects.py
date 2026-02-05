"""
Projects router for managing image workspaces.

Endpoints:
- GET /api/projects - List projects
- POST /api/projects - Create project
- GET /api/projects/{id} - Get project
- PUT /api/projects/{id} - Update project
- DELETE /api/projects/{id} - Delete project
- GET /api/projects/{id}/images - List images in project
- POST /api/projects/{id}/images - Add image to project
- DELETE /api/projects/{id}/images/{image_id} - Remove image from project
- GET /api/projects/{id}/export - Export project
"""

import contextlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_project_repository, get_user_repository
from api.routers.auth import get_current_user, require_current_user
from api.schemas.projects import (
    AddProjectImageRequest,
    AddProjectImageResponse,
    BulkAddProjectImagesRequest,
    BulkAddProjectImagesResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    DeleteProjectResponse,
    ExportProjectResponse,
    GetProjectResponse,
    ListProjectImagesResponse,
    ListProjectsResponse,
    ProjectImageInfo,
    ProjectInfo,
    ProjectListItem,
    ProjectSettings,
    RemoveProjectImageResponse,
    UpdateProjectRequest,
    UpdateProjectResponse,
)
from database.models import Project, ProjectImage
from database.repositories import ProjectRepository, UserRepository
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ============ Helpers ============


def project_to_info(project: Project, image_count: int = 0) -> ProjectInfo:
    """Convert database project to response model."""
    settings = ProjectSettings(**project.settings) if project.settings else ProjectSettings()

    return ProjectInfo(
        id=str(project.id),
        name=project.name,
        description=project.description,
        settings=settings,
        is_public=project.is_public,
        cover_url=project.cover_url,
        image_count=image_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def project_to_list_item(project: Project, image_count: int = 0) -> ProjectListItem:
    """Convert database project to list item."""
    return ProjectListItem(
        id=str(project.id),
        name=project.name,
        description=project.description,
        is_public=project.is_public,
        cover_url=project.cover_url,
        image_count=image_count,
        updated_at=project.updated_at,
    )


def project_image_to_info(project_image: ProjectImage) -> ProjectImageInfo:
    """Convert database project image to response model."""
    image = project_image.image
    return ProjectImageInfo(
        id=str(image.id),
        filename=image.filename,
        prompt=image.prompt,
        url=image.public_url,
        thumbnail_url=None,
        note=project_image.note,
        sort_order=project_image.sort_order,
        added_at=project_image.added_at,
        created_at=image.created_at,
    )


async def get_db_user_id(
    user: GitHubUser | None,
    user_repo: UserRepository | None,
) -> UUID | None:
    """Get database user ID from GitHub user."""
    if not user or not user_repo:
        return None

    db_user = await user_repo.get_by_github_id(int(user.id))
    return db_user.id if db_user else None


# ============ Endpoints ============


@router.get("", response_model=ListProjectsResponse)
async def list_projects(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List projects for the current user."""
    if not project_repo or not user_repo:
        return ListProjectsResponse(
            projects=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
        )

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    projects = await project_repo.list_by_user(user_id, limit=limit + 1, offset=offset)

    has_more = len(projects) > limit
    projects = projects[:limit]

    total = await project_repo.count_by_user(user_id)

    # Get image counts
    project_items = []
    for project in projects:
        count = await project_repo.count_images(project.id)
        project_items.append(project_to_list_item(project, count))

    return ListProjectsResponse(
        projects=project_items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post("", response_model=CreateProjectResponse)
async def create_project(
    request: CreateProjectRequest,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Create a new project."""
    if not project_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    project = await project_repo.create(
        user_id=user_id,
        name=request.name,
        description=request.description,
        settings=request.settings.model_dump() if request.settings else {},
        is_public=request.is_public,
    )

    return CreateProjectResponse(
        success=True,
        project=project_to_info(project, 0),
    )


@router.get("/{project_id}", response_model=GetProjectResponse)
async def get_project(
    project_id: str,
    user: GitHubUser | None = Depends(get_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get a specific project."""
    if not project_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    project = await project_repo.get_by_id(project_uuid)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user_id = await get_db_user_id(user, user_repo)

    # Check access
    if not project.is_public and project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    image_count = await project_repo.count_images(project.id)

    return GetProjectResponse(project=project_to_info(project, image_count))


@router.put("/{project_id}", response_model=UpdateProjectResponse)
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Update a project."""
    if not project_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify ownership
    project = await project_repo.get_by_id(project_uuid)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    updated = await project_repo.update(
        project_id=project_uuid,
        name=request.name,
        description=request.description,
        settings=request.settings.model_dump() if request.settings else None,
        is_public=request.is_public,
        cover_url=request.cover_url,
    )

    image_count = await project_repo.count_images(project_uuid)

    return UpdateProjectResponse(
        success=True,
        project=project_to_info(updated, image_count),
    )


@router.delete("/{project_id}", response_model=DeleteProjectResponse)
async def delete_project(
    project_id: str,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Delete a project."""
    if not project_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    deleted = await project_repo.delete_by_user(user_id, project_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    return DeleteProjectResponse(success=True)


# ============ Project Images ============


@router.get("/{project_id}/images", response_model=ListProjectImagesResponse)
async def list_project_images(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List images in a project."""
    if not project_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    project = await project_repo.get_by_id(project_uuid)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user_id = await get_db_user_id(user, user_repo)

    # Check access
    if not project.is_public and project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    project_images = await project_repo.list_images(project_uuid, limit=limit + 1, offset=offset)

    has_more = len(project_images) > limit
    project_images = project_images[:limit]

    total = await project_repo.count_images(project_uuid)

    return ListProjectImagesResponse(
        images=[project_image_to_info(pi) for pi in project_images],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post("/{project_id}/images", response_model=AddProjectImageResponse)
async def add_project_image(
    project_id: str,
    request: AddProjectImageRequest,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Add an image to a project."""
    if not project_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
        image_uuid = UUID(request.image_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify ownership
    project = await project_repo.get_by_id(project_uuid)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if already in project
    existing = await project_repo.get_project_image(project_uuid, image_uuid)
    if existing:
        raise HTTPException(status_code=409, detail="Image already in project")

    await project_repo.add_image(
        project_id=project_uuid,
        image_id=image_uuid,
        note=request.note,
        sort_order=request.sort_order or 0,
    )

    # Re-fetch to get image relationship
    project_images = await project_repo.list_images(project_uuid, limit=1, offset=0)
    if project_images:
        return AddProjectImageResponse(
            success=True,
            image=project_image_to_info(project_images[0]),
        )

    raise HTTPException(status_code=500, detail="Failed to add image")


@router.delete("/{project_id}/images/{image_id}", response_model=RemoveProjectImageResponse)
async def remove_project_image(
    project_id: str,
    image_id: str,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Remove an image from a project."""
    if not project_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
        image_uuid = UUID(image_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify ownership
    project = await project_repo.get_by_id(project_uuid)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    removed = await project_repo.remove_image(project_uuid, image_uuid)
    if not removed:
        raise HTTPException(status_code=404, detail="Image not in project")

    return RemoveProjectImageResponse(success=True)


@router.post("/{project_id}/images/bulk", response_model=BulkAddProjectImagesResponse)
async def bulk_add_project_images(
    project_id: str,
    request: BulkAddProjectImagesRequest,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Add multiple images to a project."""
    if not project_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        project_uuid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify ownership
    project = await project_repo.get_by_id(project_uuid)
    if not project or project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    image_uuids = []
    for image_id in request.image_ids:
        with contextlib.suppress(ValueError):
            image_uuids.append(UUID(image_id))

    added = await project_repo.bulk_add_images(project_uuid, image_uuids)

    return BulkAddProjectImagesResponse(
        success=True,
        added=len(added),
        skipped=len(request.image_ids) - len(added),
    )


@router.get("/{project_id}/export", response_model=ExportProjectResponse)
async def export_project(
    project_id: str,
    user: GitHubUser = Depends(require_current_user),
    project_repo: ProjectRepository | None = Depends(get_project_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Export a project as a ZIP file."""
    # TODO: Implement actual export
    raise HTTPException(
        status_code=501,
        detail="Project export not yet implemented",
    )
