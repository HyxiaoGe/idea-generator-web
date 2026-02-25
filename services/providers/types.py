"""
Enums and data classes for the provider abstraction layer.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from PIL import Image

# ============ Enums ============


class MediaType(StrEnum):
    """Type of media that can be generated."""

    IMAGE = "image"
    VIDEO = "video"


class ProviderCapability(StrEnum):
    """Capabilities that a provider may support."""

    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_BLEND = "image_blend"
    STYLE_TRANSFER = "style_transfer"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    VIDEO_EXTEND = "video_extend"
    SEARCH_GROUNDED = "search_grounded"
    MULTI_TURN_CHAT = "multi_turn_chat"
    INPAINTING = "inpainting"
    OUTPAINTING = "outpainting"
    UPSCALING = "upscaling"


class ProviderRegion(StrEnum):
    """Provider region for routing optimization."""

    GLOBAL = "global"  # Google, OpenAI, FLUX, Runway
    CHINA = "china"  # Alibaba, ByteDance, Zhipu, MiniMax
    BOTH = "both"  # Providers with global endpoints


class ExecutionMode(StrEnum):
    """How the provider executes generation."""

    SYNC = "sync"  # Returns result immediately
    ASYNC_TASK = "async"  # Returns task_id, requires polling


class AuthType(StrEnum):
    """Authentication strategy."""

    BEARER_TOKEN = "bearer"  # Authorization: Bearer xxx
    API_KEY_HEADER = "api_key"  # X-API-Key: xxx or custom header
    HMAC_SIGNATURE = "hmac"  # HMAC-based signing (Kling, ByteDance)
    VOLCANO_ENGINE = "volcano"  # ByteDance Volcano Engine auth


# ============ Data Classes ============


@dataclass
class ProviderModel:
    """Metadata for a model offered by a provider."""

    id: str
    name: str
    provider: str
    media_type: MediaType
    capabilities: list[ProviderCapability]
    max_resolution: str = "1K"
    max_video_duration: int | None = None  # seconds, for video models
    supports_aspect_ratios: list[str] = field(default_factory=lambda: ["1:1", "16:9", "9:16"])
    pricing_per_unit: float = 0.0  # USD per image or per second of video
    quality_score: float = 0.8  # 0.0-1.0, for routing decisions
    latency_estimate: float = 10.0  # seconds, average generation time
    is_default: bool = False  # Whether this is the default model for the provider
    # New fields for extensibility
    region: ProviderRegion = ProviderRegion.GLOBAL
    execution_mode: ExecutionMode = ExecutionMode.SYNC
    auth_type: AuthType = AuthType.BEARER_TOKEN
    rate_limit_rpm: int | None = None  # Requests per minute
    rate_limit_daily: int | None = None  # Daily quota
    supports_batch: bool = False  # Batch generation support
    min_resolution: str | None = None  # Minimum resolution
    supported_styles: list[str] = field(default_factory=list)  # Style presets
    # Model registry & quality preset fields
    tier: str = "balanced"  # "premium" | "balanced" | "fast"
    arena_rank: int | None = None  # LM Arena ranking (lower = better)
    arena_score: int | None = None  # LM Arena ELO score
    aliases: list[str] = field(default_factory=list)  # Old model IDs that map to this model
    strengths: list[str] = field(default_factory=list)  # e.g. ["photorealism", "speed"]
    hidden: bool = False  # Hidden from user-facing lists

    def supports_capability(self, capability: ProviderCapability) -> bool:
        """Check if this model supports a specific capability."""
        return capability in self.capabilities

    def supports_resolution(self, resolution: str) -> bool:
        """Check if this model supports a specific resolution."""
        resolution_order = ["1K", "2K", "4K"]
        try:
            max_idx = resolution_order.index(self.max_resolution)
            req_idx = resolution_order.index(resolution)
            return req_idx <= max_idx
        except ValueError:
            return False


@dataclass
class TaskInfo:
    """Standard task status response for async providers."""

    task_id: str
    status: str  # queued, processing, completed, failed, cancelled, timeout
    progress: float | None = None  # 0.0 to 1.0
    result_url: str | None = None
    result_urls: list[str] | None = None  # For batch results
    error: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ProviderConfig:
    """Configuration for a single provider."""

    enabled: bool = True
    api_key: str | None = None
    api_base_url: str | None = None
    priority: int = 100  # Lower = higher priority
    max_concurrent: int = 5
    timeout: int = 120  # seconds
    extra: dict = field(default_factory=dict)  # Provider-specific config


@dataclass
class GenerationRequest:
    """Unified generation request that works across all providers."""

    prompt: str
    negative_prompt: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "1K"
    safety_level: str = "moderate"
    seed: int | None = None
    # Media type (for routing)
    media_type: MediaType | None = None
    # Image-specific
    reference_images: list[Image.Image] | None = None
    style_image: Image.Image | None = None
    mask_image: Image.Image | None = None
    edit_mode: str | None = None  # "inpaint_insert", "inpaint_remove", "outpaint", "describe"
    mask_mode: str | None = None  # "user_provided", "foreground", "background", "semantic"
    mask_dilation: float = 0.03
    # Video-specific
    duration: int | None = None  # seconds
    fps: int | None = None
    # Provider hints
    preferred_provider: str | None = None
    preferred_model: str | None = None
    preferred_region: ProviderRegion | None = None  # Region preference for routing
    required_capability: ProviderCapability | None = None  # Filter providers by capability
    # Features
    enable_thinking: bool = False
    enable_search: bool = False
    # Metadata
    user_id: str | None = None
    request_id: str | None = None


@dataclass
class GenerationResult:
    """Unified generation result from any provider."""

    success: bool = False
    media_type: MediaType = MediaType.IMAGE
    # Image result
    image: Image.Image | None = None
    # Video result
    video_url: str | None = None
    video_data: bytes | None = None
    video_task_id: str | None = None  # For async video generation
    # Metadata
    provider: str = ""
    model: str = ""
    text_response: str | None = None
    thinking: str | None = None
    search_sources: str | None = None
    safety_ratings: list[dict] | None = None
    # Timing & Cost
    duration: float = 0.0  # Generation time in seconds
    cost: float = 0.0  # Estimated cost in USD
    # Error handling
    error: str | None = None
    error_type: str | None = None
    safety_blocked: bool = False
    retryable: bool = False


@dataclass
class CostRecord:
    """Record of a generation cost."""

    provider: str
    model: str
    cost: float
    timestamp: float
    media_type: MediaType
    resolution: str | None = None
    duration: int | None = None  # For video
