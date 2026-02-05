"""
Templates router for managing prompt templates.

Endpoints:
- GET /api/templates - List templates
- POST /api/templates - Create template
- GET /api/templates/{id} - Get template
- PUT /api/templates/{id} - Update template
- DELETE /api/templates/{id} - Delete template
- POST /api/templates/{id}/use - Use template
- GET /api/templates/public - List public templates
"""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_template_repository, get_user_repository
from api.routers.auth import get_current_user, require_current_user
from api.schemas.templates import (
    CreateTemplateRequest,
    CreateTemplateResponse,
    DeleteTemplateResponse,
    GetTemplateResponse,
    ListTemplatesResponse,
    TemplateInfo,
    TemplateListItem,
    TemplateSettings,
    TemplateVariable,
    UpdateTemplateRequest,
    UpdateTemplateResponse,
    UseTemplateRequest,
    UseTemplateResponse,
)
from database.models import Template
from database.repositories import TemplateRepository, UserRepository
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


# ============ Helpers ============


def template_to_info(template: Template, user_id: UUID | None = None) -> TemplateInfo:
    """Convert database template to response model."""
    variables = [TemplateVariable(**v) for v in template.variables]
    settings = (
        TemplateSettings(**template.default_settings)
        if template.default_settings
        else TemplateSettings()
    )

    return TemplateInfo(
        id=str(template.id),
        name=template.name,
        description=template.description,
        prompt_template=template.prompt_template,
        variables=variables,
        default_settings=settings,
        category=template.category,
        tags=template.tags,
        is_public=template.is_public,
        is_owner=template.user_id == user_id if user_id else False,
        use_count=template.use_count,
        preview_url=template.preview_url,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def template_to_list_item(template: Template, user_id: UUID | None = None) -> TemplateListItem:
    """Convert database template to list item."""
    return TemplateListItem(
        id=str(template.id),
        name=template.name,
        description=template.description,
        category=template.category,
        tags=template.tags,
        is_public=template.is_public,
        is_owner=template.user_id == user_id if user_id else False,
        use_count=template.use_count,
        preview_url=template.preview_url,
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


def fill_template(prompt_template: str, variables: dict) -> str:
    """Fill template variables with provided values."""
    result = prompt_template
    for name, value in variables.items():
        pattern = r"\{\{\s*" + re.escape(name) + r"\s*\}\}"
        result = re.sub(pattern, str(value), result)
    return result


# ============ Endpoints ============


@router.get("", response_model=ListTemplatesResponse)
async def list_templates(
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List templates accessible to the current user."""
    if not template_repo:
        return ListTemplatesResponse(
            templates=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
            categories=[],
        )

    user_id = await get_db_user_id(user, user_repo)

    templates = await template_repo.list_accessible(
        user_id=user_id,
        category=category,
        search=search,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(templates) > limit
    templates = templates[:limit]

    # Get categories
    categories = await template_repo.get_categories(user_id)

    return ListTemplatesResponse(
        templates=[template_to_list_item(t, user_id) for t in templates],
        total=len(templates),  # Approximate
        limit=limit,
        offset=offset,
        has_more=has_more,
        categories=categories,
    )


@router.get("/public", response_model=ListTemplatesResponse)
async def list_public_templates(
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """List public templates."""
    if not template_repo:
        return ListTemplatesResponse(
            templates=[],
            total=0,
            limit=limit,
            offset=offset,
            has_more=False,
            categories=[],
        )

    templates = await template_repo.list_public(
        category=category,
        search=search,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(templates) > limit
    templates = templates[:limit]

    categories = await template_repo.get_categories()

    return ListTemplatesResponse(
        templates=[template_to_list_item(t) for t in templates],
        total=await template_repo.count_public(),
        limit=limit,
        offset=offset,
        has_more=has_more,
        categories=categories,
    )


@router.post("", response_model=CreateTemplateResponse)
async def create_template(
    request: CreateTemplateRequest,
    user: GitHubUser = Depends(require_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Create a new template."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    template = await template_repo.create(
        user_id=user_id,
        name=request.name,
        description=request.description,
        prompt_template=request.prompt_template,
        variables=[v.model_dump() for v in request.variables],
        default_settings=request.default_settings.model_dump() if request.default_settings else {},
        category=request.category,
        tags=request.tags,
        is_public=request.is_public,
    )

    return CreateTemplateResponse(
        success=True,
        template=template_to_info(template, user_id),
    )


@router.get("/{template_id}", response_model=GetTemplateResponse)
async def get_template(
    template_id: str,
    user: GitHubUser | None = Depends(get_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get a specific template."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        template_uuid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    template = await template_repo.get_by_id(template_uuid)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    user_id = await get_db_user_id(user, user_repo)

    # Check access
    if not template.is_public and template.user_id != user_id:
        raise HTTPException(status_code=404, detail="Template not found")

    return GetTemplateResponse(template=template_to_info(template, user_id))


@router.put("/{template_id}", response_model=UpdateTemplateResponse)
async def update_template(
    template_id: str,
    request: UpdateTemplateRequest,
    user: GitHubUser = Depends(require_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Update a template."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        template_uuid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify ownership
    template = await template_repo.get_by_id(template_uuid)
    if not template or template.user_id != user_id:
        raise HTTPException(status_code=404, detail="Template not found")

    updated = await template_repo.update(
        template_id=template_uuid,
        name=request.name,
        description=request.description,
        prompt_template=request.prompt_template,
        variables=[v.model_dump() for v in request.variables] if request.variables else None,
        default_settings=request.default_settings.model_dump()
        if request.default_settings
        else None,
        category=request.category,
        tags=request.tags,
        is_public=request.is_public,
    )

    return UpdateTemplateResponse(
        success=True,
        template=template_to_info(updated, user_id),
    )


@router.delete("/{template_id}", response_model=DeleteTemplateResponse)
async def delete_template(
    template_id: str,
    user: GitHubUser = Depends(require_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Delete a template."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        template_uuid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    deleted = await template_repo.delete_by_user(user_id, template_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")

    return DeleteTemplateResponse(success=True)


@router.post("/{template_id}/use", response_model=UseTemplateResponse)
async def use_template(
    template_id: str,
    request: UseTemplateRequest,
    user: GitHubUser | None = Depends(get_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Use a template to generate a prompt.

    Fills in the template variables and returns the final prompt with settings.
    Does not actually generate an image - use /api/generate for that.
    """
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        template_uuid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    template = await template_repo.get_by_id(template_uuid)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    user_id = await get_db_user_id(user, user_repo)

    # Check access
    if not template.is_public and template.user_id != user_id:
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate required variables
    for var in template.variables:
        if var.get("required", True) and var["name"] not in request.variables:
            if not var.get("default"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required variable: {var['name']}",
                )

    # Fill in defaults
    variables = {}
    for var in template.variables:
        name = var["name"]
        if name in request.variables:
            variables[name] = request.variables[name]
        elif var.get("default"):
            variables[name] = var["default"]

    # Fill template
    prompt = fill_template(template.prompt_template, variables)

    # Merge settings
    settings = (
        TemplateSettings(**template.default_settings)
        if template.default_settings
        else TemplateSettings()
    )
    if request.settings_override:
        if request.settings_override.aspect_ratio:
            settings.aspect_ratio = request.settings_override.aspect_ratio
        if request.settings_override.resolution:
            settings.resolution = request.settings_override.resolution
        if request.settings_override.provider:
            settings.provider = request.settings_override.provider

    # Increment use count
    await template_repo.increment_use_count(template_uuid)

    return UseTemplateResponse(
        prompt=prompt,
        settings=settings,
    )
