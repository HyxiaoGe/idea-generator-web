"""
Image generation-related Pydantic schemas.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class AspectRatio(StrEnum):
    """Supported aspect ratios."""

    SQUARE = "1:1"
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    LANDSCAPE_43 = "4:3"
    PORTRAIT_34 = "3:4"


class Resolution(StrEnum):
    """Supported resolutions."""

    LOW = "1K"
    MEDIUM = "2K"
    HIGH = "4K"


class SafetyLevel(StrEnum):
    """Content safety filter levels."""

    STRICT = "strict"
    MODERATE = "moderate"
    RELAXED = "relaxed"
    NONE = "none"


class GenerationMode(StrEnum):
    """Image generation modes."""

    BASIC = "basic"
    CHAT = "chat"
    BATCH = "batch"
    BLEND = "blend"
    STYLE = "style"
    SEARCH = "search"
    INPAINT = "inpaint"
    OUTPAINT = "outpaint"
    DESCRIBE = "describe"


class MaskMode(StrEnum):
    """Mask modes for inpainting."""

    USER_PROVIDED = "user_provided"
    FOREGROUND = "foreground"
    BACKGROUND = "background"
    SEMANTIC = "semantic"


class DescribeMode(StrEnum):
    """Mode for image description endpoint."""

    DESCRIBE = "describe"
    REVERSE_PROMPT = "reverse_prompt"


class DetailLevel(StrEnum):
    """Detail level for image description."""

    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


class GenerationSettings(BaseModel):
    """Common settings for image generation."""

    aspect_ratio: AspectRatio = Field(
        default=AspectRatio.LANDSCAPE, description="Image aspect ratio"
    )
    resolution: Resolution = Field(default=Resolution.LOW, description="Image resolution")
    safety_level: SafetyLevel = Field(
        default=SafetyLevel.MODERATE, description="Content safety filter level"
    )


class GenerateImageRequest(BaseModel):
    """Request for basic image generation."""

    prompt: str = Field(..., min_length=1, max_length=2000, description="Image generation prompt")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )
    include_thinking: bool = Field(default=False, description="Include model's thinking process")
    enhance_prompt: bool | None = Field(
        None, description="AI-enhance the prompt for better results"
    )
    generate_negative: bool | None = Field(None, description="Auto-generate negative prompt")
    template_id: str | None = Field(None, description="Local template ID to apply")
    quality_preset: str | None = Field(
        None,
        description="Quality preset: 'premium', 'balanced', 'fast'. Ignored if X-Model header is set.",
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        """Validate and clean prompt."""
        return v.strip()


class GeneratedImage(BaseModel):
    """Generated image information."""

    key: str = Field(..., description="Storage key/path of the image")
    filename: str = Field(..., description="Image filename")
    url: str | None = Field(None, description="Public URL if available")
    width: int | None = Field(None, description="Image width in pixels")
    height: int | None = Field(None, description="Image height in pixels")


class GenerateImageResponse(BaseModel):
    """Response for image generation."""

    image: GeneratedImage = Field(..., description="Generated image info")
    prompt: str = Field(..., description="Original prompt")
    thinking: str | None = Field(None, description="Model's thinking process")
    text_response: str | None = Field(None, description="Text response from model")
    duration: float = Field(..., description="Generation time in seconds")
    mode: GenerationMode = Field(default=GenerationMode.BASIC)
    settings: GenerationSettings = Field(..., description="Settings used")
    created_at: datetime = Field(default_factory=datetime.now)
    # Multi-provider support
    provider: str | None = Field(None, description="Provider used (google, openai, bfl, etc)")
    model: str | None = Field(None, description="Model ID used")
    model_display_name: str | None = Field(None, description="Human-readable model name")
    quality_preset: str | None = Field(
        None, description="Quality preset used, or 'manual' if model was specified"
    )
    search_sources: str | None = Field(None, description="Search sources for grounded generation")
    # Prompt pipeline
    processed_prompt: str | None = Field(
        None, description="Final processed prompt (if pipeline ran)"
    )
    negative_prompt: str | None = Field(None, description="Generated negative prompt")
    template_used: bool = Field(False, description="Whether a template was applied")
    was_translated: bool = Field(False, description="Whether prompt was auto-translated")
    was_enhanced: bool = Field(False, description="Whether prompt was AI-enhanced")
    template_name: str | None = Field(None, description="Template name if used")


class AsyncGenerateResponse(BaseModel):
    """Response returned by POST /api/generate in async mode."""

    task_id: str = Field(..., description="Task ID for tracking progress")
    status: str = Field(default="queued", description="Current task status")
    message: str = Field(default="Generation task queued", description="Status message")


class GenerateTaskProgress(BaseModel):
    """Unified progress response for any generation task (single or batch)."""

    task_id: str = Field(..., description="Task ID")
    task_type: str = Field(..., description="Task type: 'single' or 'batch'")
    status: str = Field(..., description="Task status")
    progress: float = Field(
        default=0.0, description="Progress (0.0-1.0 for single, count/total for batch)"
    )
    # Single-image fields
    stage: str | None = Field(
        None, description="Current stage (generating, switching_provider, etc)"
    )
    provider: str | None = Field(None, description="Current/final provider name")
    result: GenerateImageResponse | None = Field(
        None, description="Final result (single-image only)"
    )
    # Batch fields
    total: int | None = Field(None, description="Total count (batch only)")
    current_prompt: str | None = Field(None, description="Currently processing prompt (batch only)")
    results: list[GeneratedImage] | None = Field(None, description="Completed results (batch only)")
    errors: list[str] | None = Field(None, description="Error list (batch only)")
    # Common
    error: str | None = Field(None, description="Error message if failed")
    error_code: str | None = Field(None, description="Error code if failed")
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BatchGenerateRequest(BaseModel):
    """Request for batch image generation."""

    prompts: list[str] = Field(..., min_length=1, max_length=10, description="List of prompts")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )


class BatchGenerateResponse(BaseModel):
    """Response for batch generation task."""

    task_id: str = Field(..., description="Task ID for tracking progress")
    total: int = Field(..., description="Total number of images to generate")
    status: str = Field(default="queued", description="Current task status")


class TaskProgress(BaseModel):
    """Progress update for a generation task."""

    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status")
    progress: int = Field(..., description="Completed count")
    total: int = Field(..., description="Total count")
    current_prompt: str | None = Field(None, description="Currently processing prompt")
    results: list[GeneratedImage] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BlendImagesRequest(BaseModel):
    """Request for image blending."""

    image_keys: list[str] = Field(
        ..., min_length=2, max_length=4, description="List of image keys to blend"
    )
    blend_prompt: str | None = Field(None, description="Additional prompt for blending")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )


class StyleTransferRequest(BaseModel):
    """Request for style transfer."""

    content_image_key: str = Field(..., description="Key of content image")
    style_prompt: str = Field(..., description="Style description")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )


class InpaintRequest(BaseModel):
    """Request for image inpainting."""

    image_key: str = Field(..., description="Storage key of the source image")
    prompt: str = Field(
        ..., min_length=1, max_length=2000, description="What to paint in the masked area"
    )
    mask_key: str | None = Field(
        None, description="Storage key of the mask image (required for user_provided mode)"
    )
    mask_mode: MaskMode = Field(default=MaskMode.USER_PROVIDED, description="Mask mode")
    mask_dilation: float = Field(default=0.03, ge=0.0, le=1.0, description="Mask dilation factor")
    remove_mode: bool = Field(
        default=False, description="If true, remove content in masked area instead of inserting"
    )
    negative_prompt: str | None = Field(None, description="Negative prompt")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )


class OutpaintRequest(BaseModel):
    """Request for image outpainting (extending beyond borders)."""

    image_key: str = Field(..., description="Storage key of the source image")
    mask_key: str = Field(..., description="Storage key of the mask image (defines outpaint area)")
    prompt: str = Field(
        default="Extend this image naturally",
        min_length=1,
        max_length=2000,
        description="Prompt for the extended area",
    )
    negative_prompt: str | None = Field(None, description="Negative prompt")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )


class DescribeImageRequest(BaseModel):
    """Request for image description/analysis."""

    image_key: str = Field(..., description="Storage key of the image to describe")
    mode: DescribeMode = Field(
        default=DescribeMode.DESCRIBE,
        description="Mode: 'describe' for natural language description, 'reverse_prompt' for generation prompt",
    )
    detail_level: DetailLevel = Field(
        default=DetailLevel.STANDARD, description="Description detail level"
    )
    include_tags: bool = Field(default=True, description="Include keyword tags in response")
    language: str = Field(
        default="en", pattern="^(en|zh)$", description="Response language (en or zh)"
    )


class DescribeImageResponse(BaseModel):
    """Response for image description."""

    description: str = Field(..., description="Image description text")
    prompt: str | None = Field(None, description="Generated prompt (reverse_prompt mode only)")
    tags: list[str] = Field(default_factory=list, description="Keyword tags extracted from image")
    duration: float = Field(..., description="Analysis time in seconds")
    provider: str | None = Field(None, description="Provider used")
    model: str | None = Field(None, description="Model used")


class SearchGenerateRequest(BaseModel):
    """Request for search-grounded generation."""

    prompt: str = Field(..., min_length=1, max_length=2000, description="Generation prompt")
    search_context: str | None = Field(None, description="Additional search context")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings, description="Generation settings"
    )
    enhance_prompt: bool | None = Field(
        None, description="AI-enhance the prompt for better results"
    )
    generate_negative: bool | None = Field(None, description="Auto-generate negative prompt")
    template_id: str | None = Field(None, description="Local template ID to apply")
    quality_preset: str | None = Field(
        None,
        description="Quality preset: 'premium', 'balanced', 'fast'. Ignored if X-Model header is set.",
    )


class CostEstimate(BaseModel):
    """Cost estimate for generation."""

    mode: GenerationMode
    resolution: Resolution
    count: int = Field(default=1)
    estimated_cost_usd: float
    estimated_tokens: int
