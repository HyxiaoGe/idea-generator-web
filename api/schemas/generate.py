"""
Image generation-related Pydantic schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, field_validator


class AspectRatio(str, Enum):
    """Supported aspect ratios."""

    SQUARE = "1:1"
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    LANDSCAPE_43 = "4:3"
    PORTRAIT_34 = "3:4"


class Resolution(str, Enum):
    """Supported resolutions."""

    LOW = "1K"
    MEDIUM = "2K"
    HIGH = "4K"


class SafetyLevel(str, Enum):
    """Content safety filter levels."""

    STRICT = "strict"
    MODERATE = "moderate"
    RELAXED = "relaxed"
    NONE = "none"


class GenerationMode(str, Enum):
    """Image generation modes."""

    BASIC = "basic"
    CHAT = "chat"
    BATCH = "batch"
    BLEND = "blend"
    STYLE = "style"
    SEARCH = "search"


class GenerationSettings(BaseModel):
    """Common settings for image generation."""

    aspect_ratio: AspectRatio = Field(
        default=AspectRatio.LANDSCAPE,
        description="Image aspect ratio"
    )
    resolution: Resolution = Field(
        default=Resolution.LOW,
        description="Image resolution"
    )
    safety_level: SafetyLevel = Field(
        default=SafetyLevel.MODERATE,
        description="Content safety filter level"
    )


class GenerateImageRequest(BaseModel):
    """Request for basic image generation."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Image generation prompt"
    )
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings,
        description="Generation settings"
    )
    include_thinking: bool = Field(
        default=False,
        description="Include model's thinking process"
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
    url: Optional[str] = Field(None, description="Public URL if available")
    width: Optional[int] = Field(None, description="Image width in pixels")
    height: Optional[int] = Field(None, description="Image height in pixels")


class GenerateImageResponse(BaseModel):
    """Response for image generation."""

    image: GeneratedImage = Field(..., description="Generated image info")
    prompt: str = Field(..., description="Original prompt")
    thinking: Optional[str] = Field(None, description="Model's thinking process")
    text_response: Optional[str] = Field(None, description="Text response from model")
    duration: float = Field(..., description="Generation time in seconds")
    mode: GenerationMode = Field(default=GenerationMode.BASIC)
    settings: GenerationSettings = Field(..., description="Settings used")
    created_at: datetime = Field(default_factory=datetime.now)


class BatchGenerateRequest(BaseModel):
    """Request for batch image generation."""

    prompts: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of prompts"
    )
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings,
        description="Generation settings"
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
    current_prompt: Optional[str] = Field(None, description="Currently processing prompt")
    results: List[GeneratedImage] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BlendImagesRequest(BaseModel):
    """Request for image blending."""

    image_keys: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="List of image keys to blend"
    )
    blend_prompt: Optional[str] = Field(
        None,
        description="Additional prompt for blending"
    )
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings,
        description="Generation settings"
    )


class StyleTransferRequest(BaseModel):
    """Request for style transfer."""

    content_image_key: str = Field(..., description="Key of content image")
    style_prompt: str = Field(..., description="Style description")
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings,
        description="Generation settings"
    )


class SearchGenerateRequest(BaseModel):
    """Request for search-grounded generation."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Generation prompt"
    )
    search_context: Optional[str] = Field(
        None,
        description="Additional search context"
    )
    settings: GenerationSettings = Field(
        default_factory=GenerationSettings,
        description="Generation settings"
    )


class CostEstimate(BaseModel):
    """Cost estimate for generation."""

    mode: GenerationMode
    resolution: Resolution
    count: int = Field(default=1)
    estimated_cost_usd: float
    estimated_tokens: int
