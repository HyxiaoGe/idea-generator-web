"""
Pydantic schemas for the prompt template library API.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# ============================================================================
# Response Schemas
# ============================================================================


class TemplateListItem(BaseModel):
    """Compact template for list views."""

    id: str
    display_name_en: str
    display_name_zh: str
    description_en: str | None = None
    description_zh: str | None = None
    preview_image_url: str | None = None
    preview_4k_url: str | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
    difficulty: str
    media_type: str = "image"
    use_count: int
    like_count: int
    favorite_count: int
    source: str
    trending_score: float
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateDetailResponse(BaseModel):
    """Full template detail."""

    id: str
    prompt_text: str
    display_name_en: str
    display_name_zh: str
    description_en: str | None = None
    description_zh: str | None = None
    preview_image_url: str | None = None
    preview_4k_url: str | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
    style_keywords: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    difficulty: str
    media_type: str = "image"
    language: str
    source: str
    use_count: int
    like_count: int
    favorite_count: int
    trending_score: float
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime

    # Computed at runtime per user
    is_liked: bool = False
    is_favorited: bool = False

    model_config = {"from_attributes": True}


# ============================================================================
# Request Schemas
# ============================================================================


class TemplateCreateRequest(BaseModel):
    """Request to create a template."""

    prompt_text: str
    display_name_en: str
    display_name_zh: str
    description_en: str | None = None
    description_zh: str | None = None
    preview_image_url: str | None = None
    preview_4k_url: str | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
    style_keywords: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    difficulty: str = "beginner"
    media_type: str = "image"
    language: str = "bilingual"
    source: str = "curated"


class TemplateUpdateRequest(BaseModel):
    """Request to update a template (all fields optional)."""

    prompt_text: str | None = None
    display_name_en: str | None = None
    display_name_zh: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    preview_image_url: str | None = None
    preview_4k_url: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    style_keywords: list[str] | None = None
    parameters: dict | None = None
    difficulty: str | None = None
    media_type: str | None = None
    language: str | None = None
    source: str | None = None
    is_active: bool | None = None


# ============================================================================
# Utility Schemas
# ============================================================================


class CategoryItem(BaseModel):
    """Category with template count."""

    category: str
    count: int


class ToggleResponse(BaseModel):
    """Response for like/favorite toggle."""

    action: str  # "added" or "removed"
    count: int


# ============================================================================
# Paginated Response
# ============================================================================


class TemplateListResponse(BaseModel):
    """Paginated list of templates."""

    items: list[TemplateListItem]
    total: int
    page: int
    page_size: int


# ============================================================================
# AI Generation Schemas
# ============================================================================


class GenerateRequest(BaseModel):
    """Request to generate templates for a single category."""

    category: str
    count: int = Field(default=10, ge=1, le=50)
    styles: list[str] | None = None


class BatchGenerateRequest(BaseModel):
    """Request to batch-generate templates across categories."""

    categories: list[str] | None = None  # None = all categories
    count_per_category: int = Field(default=10, ge=1, le=50)


class VariantRequest(BaseModel):
    """Request to generate style variants of a template."""

    target_styles: list[str]


class GenerateStats(BaseModel):
    """Stats for a single category generation run."""

    category: str
    generated: int
    passed_quality: int
    saved: int


class GenerateResponse(BaseModel):
    """Response for template generation (single or batch)."""

    stats: list[GenerateStats]
    total_generated: int
    total_saved: int


class EnhanceResponse(BaseModel):
    """Response for template enhancement."""

    template_id: str
    original_prompt: str
    enhanced_prompt: str
    improvements: list[str]


class VariantResponse(BaseModel):
    """Response for style variant generation."""

    source_template_id: str
    variants_created: list[TemplateDetailResponse]
