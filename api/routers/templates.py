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

from api.dependencies import get_template_repository, get_user_repository
from api.routers.auth import get_current_user, require_current_user
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
from database.repositories import TemplateRepository, UserRepository
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


# ============ Helpers ============


async def require_admin(user: GitHubUser = Depends(require_current_user)) -> GitHubUser:
    """Require admin privileges (currently passes through authenticated user)."""
    return user


async def get_db_user_id(
    user: GitHubUser | None,
    user_repo: UserRepository | None,
) -> UUID | None:
    """Resolve GitHub user to database user ID."""
    if not user or not user_repo:
        return None
    db_user = await user_repo.get_by_github_id(int(user.id))
    return db_user.id if db_user else None


def template_to_list_item(t) -> TemplateListItem:
    """Convert a PromptTemplate model to a TemplateListItem schema."""
    return TemplateListItem(
        id=str(t.id),
        display_name_en=t.display_name_en,
        display_name_zh=t.display_name_zh,
        description_en=t.description_en,
        description_zh=t.description_zh,
        preview_image_url=t.preview_image_url,
        category=t.category,
        tags=t.tags or [],
        difficulty=t.difficulty,
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
        category=t.category,
        tags=t.tags or [],
        style_keywords=t.style_keywords or [],
        parameters=t.parameters or {},
        difficulty=t.difficulty,
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
    template_repo: TemplateRepository | None = Depends(get_template_repository),
):
    """Get all categories with template counts."""
    if not template_repo:
        return []

    rows = await template_repo.get_categories_with_count()
    return [CategoryItem(category=cat, count=cnt) for cat, cnt in rows]


@router.get("/favorites", response_model=TemplateListResponse)
async def get_user_favorites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: GitHubUser = Depends(require_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get current user's favorited templates."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=500, detail="User record not synced. Please re-login.")

    templates, total = await template_repo.get_user_favorites(
        user_id=user_id,
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
        limit=limit,
    )
    return [template_to_list_item(t) for t in templates]


@router.post("/generate", response_model=GenerateResponse)
async def generate_templates(
    data: GenerateRequest,
    admin: GitHubUser = Depends(require_admin),
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
    admin: GitHubUser = Depends(require_admin),
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
    admin: GitHubUser = Depends(require_admin),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Create a new template (admin only)."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    user_id = await get_db_user_id(admin, user_repo)

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
    user: GitHubUser | None = Depends(get_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
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

    user_id = await get_db_user_id(user, user_repo)

    is_liked = False
    is_favorited = False
    if user_id:
        is_liked = await template_repo.is_liked(tid, user_id)
        is_favorited = await template_repo.is_favorited(tid, user_id)

    return template_to_detail(template, is_liked=is_liked, is_favorited=is_favorited)


@router.post("/{template_id}/use", response_model=TemplateDetailResponse)
async def record_usage(
    template_id: str,
    user: GitHubUser | None = Depends(get_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Record that a template was used."""
    if not template_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    user_id = await get_db_user_id(user, user_repo)
    template = await template_repo.record_usage(tid, user_id=user_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template_to_detail(template)


@router.post("/{template_id}/like", response_model=ToggleResponse)
async def toggle_like(
    template_id: str,
    user: GitHubUser = Depends(require_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Toggle like on a template."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=500, detail="User record not synced. Please re-login.")

    try:
        action, count = await template_repo.toggle_like(tid, user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found")

    return ToggleResponse(action=action, count=count)


@router.post("/{template_id}/favorite", response_model=ToggleResponse)
async def toggle_favorite(
    template_id: str,
    user: GitHubUser = Depends(require_current_user),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Toggle favorite on a template."""
    if not template_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        tid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=500, detail="User record not synced. Please re-login.")

    try:
        action, count = await template_repo.toggle_favorite(tid, user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found")

    return ToggleResponse(action=action, count=count)


@router.post("/{template_id}/enhance", response_model=EnhanceResponse)
async def enhance_template(
    template_id: str,
    admin: GitHubUser = Depends(require_admin),
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
    admin: GitHubUser = Depends(require_admin),
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
    admin: GitHubUser = Depends(require_admin),
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
    admin: GitHubUser = Depends(require_admin),
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
