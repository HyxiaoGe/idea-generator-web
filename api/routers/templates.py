"""
Templates router for the prompt template library.

15 endpoints covering listing, CRUD, social engagement, recommendations,
and AI generation/enhancement.

Fixed-path endpoints are placed before parameterized endpoints to avoid
route conflicts.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import (
    ensure_db_user,
    ensure_db_user_optional,
    get_template_repository,
)
from api.schemas.templates import (
    BatchGenerateRequest,
    CategoryItem,
    EnhanceResponse,
    GenerateRequest,
    GenerateResponse,
    TemplateCreateRequest,
    TemplateDetailResponse,
    TemplateListItem,
    TemplateListResponse,
    TemplateUpdateRequest,
    ToggleResponse,
    VariantRequest,
    VariantResponse,
)
from core.auth import AppUser, require_admin
from database.repositories import TemplateRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


# ============ Helpers ============


def template_to_list_item(t) -> TemplateListItem:
    """Convert a PromptTemplate model to a TemplateListItem schema."""
    return TemplateListItem(
        id=str(t.id),
        display_name_en=t.display_name_en,
        display_name_zh=t.display_name_zh,
        description_en=t.description_en,
        description_zh=t.description_zh,
        preview_image_url=t.preview_image_url,
        preview_4k_url=t.preview_4k_url,
        preview_storage_key=t.preview_storage_key,
        category=t.category,
        tags=t.tags or [],
        difficulty=t.difficulty,
        media_type=t.media_type,
        use_count=t.use_count,
        like_count=t.like_count,
        favorite_count=t.favorite_count,
        source=t.source,
        trending_score=t.trending_score,
        created_at=t.created_at,
    )


def template_to_detail(
    t, *, is_liked: bool = False, is_favorited: bool = False
) -> TemplateDetailResponse:
    """Convert a PromptTemplate model to a TemplateDetailResponse schema."""
    return TemplateDetailResponse(
        id=str(t.id),
        prompt_text=t.prompt_text,
        display_name_en=t.display_name_en,
        display_name_zh=t.display_name_zh,
        description_en=t.description_en,
        description_zh=t.description_zh,
        preview_image_url=t.preview_image_url,
        preview_4k_url=t.preview_4k_url,
        preview_storage_key=t.preview_storage_key,
        category=t.category,
        tags=t.tags or [],
        style_keywords=t.style_keywords or [],
        parameters=t.parameters or {},
        difficulty=t.difficulty,
        media_type=t.media_type,
        language=t.language,
        source=t.source,
        use_count=t.use_count,
        like_count=t.like_count,
        favorite_count=t.favorite_count,
        trending_score=t.trending_score,
        is_active=t.is_active,
        created_by=str(t.created_by) if t.created_by else None,
        created_at=t.created_at,
        updated_at=t.updated_at,
        is_liked=is_liked,
        is_favorited=is_favorited,
    )


# ============================================================================
# Fixed-path endpoints (must come before parameterized)
# ============================================================================


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None),
    tags: str | None = Query(default=None, description="Comma-separated tags"),
    difficulty: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="trending"),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """List templates with filtering, searching, and sorting."""
    if not template_repo:
        return TemplateListResponse(items=[], total=0, page=page, page_size=page_size)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    templates, total = await template_repo.list_templates(
        category=category,
        tags=tag_list,
        difficulty=difficulty,
        media_type=media_type,
        search=search,
        sort_by=sort_by,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return TemplateListResponse(
        items=[template_to_list_item(t) for t in templates],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/categories", response_model=list[CategoryItem])
async def get_categories(
    media_type: str | None = Query(default=None),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Get all categories with template counts."""
    if not template_repo:
        return []

    rows = await template_repo.get_categories_with_count(media_type=media_type)
    return [CategoryItem(category=cat, count=cnt) for cat, cnt in rows]


@router.get("/favorites", response_model=TemplateListResponse)
async def get_user_favorites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    media_type: str | None = Query(default=None),
    user_id: UUID | None = Depends(ensure_db_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Get current user's favorited templates."""
    if not template_repo or not user_id:
        raise HTTPException(status_code=503, detail="Database not configured")

    templates, total = await template_repo.get_user_favorites(
        user_id=user_id,
        media_type=media_type,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return TemplateListResponse(
        items=[template_to_list_item(t) for t in templates],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/recommended", response_model=list[TemplateListItem])
async def get_recommendations(
    based_on: str | None = Query(default=None, description="Template ID to base on"),
    tags: str | None = Query(default=None, description="Comma-separated tags"),
    media_type: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Get recommended templates based on tags or a source template."""
    if not template_repo:
        return []

    based_on_uuid = None
    if based_on:
        try:
            based_on_uuid = UUID(based_on)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid template ID")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    templates = await template_repo.get_recommendations(
        based_on=based_on_uuid,
        tags=tag_list,
        media_type=media_type,
        limit=limit,
    )
    return [template_to_list_item(t) for t in templates]


@router.post("/generate", response_model=GenerateResponse)
async def generate_templates(
    data: GenerateRequest,
    admin: AppUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Generate AI templates for a single category (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    from services.template_generator import TemplateGenerator

    generator = TemplateGenerator(template_repo)
    try:
        stats = await generator.generate_templates_for_category(
            category=data.category,
            count=data.count,
            styles=data.styles,
        )
        return GenerateResponse(
            stats=[stats],
            total_generated=stats.generated,
            total_saved=stats.saved,
        )
    finally:
        await generator.close()


@router.post("/batch-generate", response_model=GenerateResponse)
async def batch_generate(
    data: BatchGenerateRequest,
    admin: AppUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Batch-generate AI templates across categories (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    from services.template_generator import TemplateGenerator

    generator = TemplateGenerator(template_repo)
    try:
        result = await generator.batch_generate(
            categories=data.categories,
            count_per_category=data.count_per_category,
        )
        return result
    finally:
        await generator.close()


@router.post("", response_model=TemplateDetailResponse)
async def create_template(
    data: TemplateCreateRequest,
    admin: AppUser = Depends(require_admin),
    user_id: UUID | None = Depends(ensure_db_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Create a new template (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    template = await template_repo.create(
        **data.model_dump(),
        created_by=user_id,
    )
    return template_to_detail(template)


# ============================================================================
# Parameterized endpoints
# ============================================================================


@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template_detail(
    template_id: str,
    user_id: UUID | None = Depends(ensure_db_user_optional),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Get full template detail."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    template = await template_repo.get_by_id(tid)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    is_liked = False
    is_favorited = False
    if user_id:
        is_liked = await template_repo.is_liked(tid, user_id)
        is_favorited = await template_repo.is_favorited(tid, user_id)

    return template_to_detail(template, is_liked=is_liked, is_favorited=is_favorited)


@router.post("/{template_id}/use", response_model=TemplateDetailResponse)
async def record_usage(
    template_id: str,
    user_id: UUID | None = Depends(ensure_db_user_optional),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Record that a template was used."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    template = await template_repo.record_usage(tid, user_id=user_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template_to_detail(template)


@router.post("/{template_id}/like", response_model=ToggleResponse)
async def toggle_like(
    template_id: str,
    user_id: UUID | None = Depends(ensure_db_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Toggle like on a template."""
    if not template_repo or not user_id:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    try:
        action, count = await template_repo.toggle_like(tid, user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found")

    return ToggleResponse(action=action, count=count)


@router.post("/{template_id}/favorite", response_model=ToggleResponse)
async def toggle_favorite(
    template_id: str,
    user_id: UUID | None = Depends(ensure_db_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Toggle favorite on a template."""
    if not template_repo or not user_id:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    try:
        action, count = await template_repo.toggle_favorite(tid, user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found")

    return ToggleResponse(action=action, count=count)


@router.post("/{template_id}/enhance", response_model=EnhanceResponse)
async def enhance_template(
    template_id: str,
    admin: AppUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Enhance a template's prompt using AI (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    from services.template_generator import TemplateGenerator

    generator = TemplateGenerator(template_repo)
    try:
        result = await generator.enhance_template(str(tid))
        return result
    finally:
        await generator.close()


@router.post("/{template_id}/variants", response_model=VariantResponse)
async def generate_variants(
    template_id: str,
    data: VariantRequest,
    admin: AppUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Generate style variants of a template (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    from services.template_generator import TemplateGenerator

    generator = TemplateGenerator(template_repo)
    try:
        result = await generator.generate_style_variants(str(tid), data.target_styles)
        return result
    finally:
        await generator.close()


@router.put("/{template_id}", response_model=TemplateDetailResponse)
async def update_template(
    template_id: str,
    data: TemplateUpdateRequest,
    admin: AppUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Update a template (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    update_data = data.model_dump(exclude_unset=True)
    template = await template_repo.update(tid, **update_data)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template_to_detail(template)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    admin: AppUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Soft-delete a template (admin only)."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    deleted = await template_repo.soft_delete(tid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")

    return {"message": "Template deleted"}
