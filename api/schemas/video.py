"""
Video generation-related Pydantic schemas.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class VideoResolution(StrEnum):
    """Supported video resolutions."""

    SD = "480p"
    HD = "720p"
    FULL_HD = "1080p"
    UHD_4K = "4K"


class VideoAspectRatio(StrEnum):
    """Supported video aspect ratios."""

    SQUARE = "1:1"
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    CINEMATIC = "21:9"
    VERTICAL = "4:5"


class VideoGenerationMode(StrEnum):
    """Video generation modes."""

    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    VIDEO_EXTEND = "video_extend"


class VideoTaskStatus(StrEnum):
    """Status of a video generation task."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoGenerationSettings(BaseModel):
    """Common settings for video generation."""

    resolution: VideoResolution = Field(default=VideoResolution.HD, description="Video resolution")
    aspect_ratio: VideoAspectRatio = Field(
        default=VideoAspectRatio.LANDSCAPE, description="Video aspect ratio"
    )
    fps: int = Field(default=24, ge=15, le=60, description="Frames per second")
    duration: int = Field(default=5, ge=1, le=60, description="Video duration in seconds")


class GenerateVideoRequest(BaseModel):
    """Request for text-to-video generation."""

    prompt: str = Field(..., min_length=1, max_length=2000, description="Video generation prompt")
    negative_prompt: str | None = Field(
        None, max_length=1000, description="What to avoid in the video"
    )
    settings: VideoGenerationSettings = Field(
        default_factory=VideoGenerationSettings, description="Generation settings"
    )
    seed: int | None = Field(None, description="Random seed for reproducibility")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        """Validate and clean prompt."""
        return v.strip()


class ImageToVideoRequest(BaseModel):
    """Request for image-to-video generation."""

    image_key: str = Field(..., description="Key of the source image")
    prompt: str | None = Field(None, max_length=2000, description="Motion/animation prompt")
    settings: VideoGenerationSettings = Field(
        default_factory=VideoGenerationSettings, description="Generation settings"
    )


class VideoExtendRequest(BaseModel):
    """Request for extending an existing video."""

    video_task_id: str = Field(..., description="Task ID of the video to extend")
    extend_duration: int = Field(default=5, ge=1, le=30, description="Additional seconds to add")
    prompt: str | None = Field(None, description="Prompt for the extension")


class GeneratedVideo(BaseModel):
    """Generated video information."""

    task_id: str = Field(..., description="Unique task identifier")
    url: str | None = Field(None, description="Video URL when ready")
    thumbnail_url: str | None = Field(None, description="Thumbnail image URL")
    duration: float | None = Field(None, description="Video duration in seconds")
    width: int | None = Field(None, description="Video width in pixels")
    height: int | None = Field(None, description="Video height in pixels")
    file_size: int | None = Field(None, description="File size in bytes")


class GenerateVideoResponse(BaseModel):
    """Response for video generation (async)."""

    task_id: str = Field(..., description="Task ID for tracking progress")
    status: VideoTaskStatus = Field(default=VideoTaskStatus.QUEUED)
    message: str = Field(default="Video generation started")
    estimated_duration: int | None = Field(
        None, description="Estimated time to complete in seconds"
    )
    # Provider info
    provider: str | None = Field(None, description="Provider used")
    model: str | None = Field(None, description="Model ID used")


class VideoTaskProgress(BaseModel):
    """Progress update for a video generation task."""

    task_id: str = Field(..., description="Task ID")
    status: VideoTaskStatus = Field(..., description="Current status")
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    video: GeneratedVideo | None = Field(None, description="Video info when completed")
    error: str | None = Field(None, description="Error message if failed")
    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)
    # Provider info
    provider: str | None = Field(None, description="Provider used")
    model: str | None = Field(None, description="Model ID used")
    # Cost
    estimated_cost: float | None = Field(None, description="Estimated cost in USD")


class ListVideoTasksResponse(BaseModel):
    """Response for listing video tasks."""

    tasks: list[VideoTaskProgress] = Field(default_factory=list)
    total: int = Field(default=0)


class VideoProviderInfo(BaseModel):
    """Information about a video provider."""

    name: str = Field(..., description="Provider identifier")
    display_name: str = Field(..., description="Human-readable name")
    models: list[dict] = Field(default_factory=list)
    max_duration: int = Field(..., description="Maximum video duration in seconds")
    supported_resolutions: list[str] = Field(default_factory=list)
    pricing_per_second: float = Field(..., description="USD per second of video")


class ListVideoProvidersResponse(BaseModel):
    """Response for listing video providers."""

    providers: list[VideoProviderInfo] = Field(default_factory=list)
    default_provider: str = Field(...)
    routing_strategy: str = Field(...)
