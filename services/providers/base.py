"""
Base protocols and data classes for AI providers.

This module defines the core abstractions that all providers must implement,
ensuring a consistent interface across different AI vendors.
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


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


# ============ Error Types (for i18n mapping) ============

ERROR_TYPE_OVERLOADED = "overloaded"
ERROR_TYPE_UNAVAILABLE = "unavailable"
ERROR_TYPE_TIMEOUT = "timeout"
ERROR_TYPE_RATE_LIMITED = "rate_limited"
ERROR_TYPE_INVALID_KEY = "invalid_key"
ERROR_TYPE_SAFETY_BLOCKED = "safety_blocked"
ERROR_TYPE_CONNECTION = "connection"
ERROR_TYPE_UNKNOWN = "unknown"

# Network-related error keywords that should trigger retry
RETRYABLE_ERRORS = [
    "server disconnected",
    "connection reset",
    "connection refused",
    "timeout",
    "network",
    "unavailable",
    "overloaded",
    "503",
    "502",
    "504",
]


# ============ Utility Functions ============


def is_retryable_error(error_msg: str) -> bool:
    """Check if an error is retryable based on error message."""
    error_lower = error_msg.lower()
    return any(keyword in error_lower for keyword in RETRYABLE_ERRORS)


def classify_error(error_msg: str) -> str:
    """
    Classify error message into error type for i18n lookup.

    Returns:
        Error type constant string for i18n key mapping
    """
    error_lower = error_msg.lower()

    if "overloaded" in error_lower or ("503" in error_lower and "unavailable" in error_lower):
        return ERROR_TYPE_OVERLOADED
    elif "503" in error_lower or "unavailable" in error_lower:
        return ERROR_TYPE_UNAVAILABLE
    elif "timeout" in error_lower:
        return ERROR_TYPE_TIMEOUT
    elif "quota" in error_lower or "rate" in error_lower:
        return ERROR_TYPE_RATE_LIMITED
    elif "api_key" in error_lower or "invalid" in error_lower:
        return ERROR_TYPE_INVALID_KEY
    elif "safety" in error_lower or "blocked" in error_lower:
        return ERROR_TYPE_SAFETY_BLOCKED
    elif "server disconnected" in error_lower or "connection" in error_lower:
        return ERROR_TYPE_CONNECTION
    else:
        return ERROR_TYPE_UNKNOWN


def get_friendly_error_message(error_msg: str, translator=None) -> str:
    """
    Convert technical error messages to user-friendly messages.

    Args:
        error_msg: The technical error message
        translator: Optional Translator instance for i18n support

    Returns:
        User-friendly error message
    """
    error_type = classify_error(error_msg)

    # If translator is provided, use i18n
    if translator:
        i18n_key = f"errors.api.{error_type}"
        translated = translator.get(i18n_key)
        if translated != i18n_key:
            return translated

    # Fallback to hardcoded bilingual messages
    fallback_messages = {
        ERROR_TYPE_OVERLOADED: "模型繁忙，请稍后重试 (Model overloaded)",
        ERROR_TYPE_UNAVAILABLE: "服务暂时不可用，请稍后重试 (Service unavailable)",
        ERROR_TYPE_TIMEOUT: "请求超时，请重试 (Request timeout)",
        ERROR_TYPE_RATE_LIMITED: "API 配额已用尽或请求过快 (Rate limited)",
        ERROR_TYPE_INVALID_KEY: "API Key 无效，请检查配置 (Invalid API key)",
        ERROR_TYPE_SAFETY_BLOCKED: "内容被安全过滤器拦截 (Blocked by safety filter)",
        ERROR_TYPE_CONNECTION: "网络连接异常，请重试 (Connection error)",
    }

    if error_type in fallback_messages:
        return fallback_messages[error_type]

    # Return original message if no match, but truncate if too long
    return error_msg[:200] if len(error_msg) > 200 else error_msg


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
    # Video-specific
    duration: int | None = None  # seconds
    fps: int | None = None
    # Provider hints
    preferred_provider: str | None = None
    preferred_model: str | None = None
    preferred_region: ProviderRegion | None = None  # Region preference for routing
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


# ============ Authentication Strategies ============


class AuthStrategy(ABC):
    """Base class for authentication strategies."""

    @abstractmethod
    def apply(self, headers: dict, **kwargs) -> dict:
        """Apply authentication to request headers."""
        pass


class BearerTokenAuth(AuthStrategy):
    """Bearer token authentication (Authorization: Bearer xxx)."""

    def __init__(self, token: str):
        self.token = token

    def apply(self, headers: dict, **kwargs) -> dict:
        headers["Authorization"] = f"Bearer {self.token}"
        return headers


class ApiKeyHeaderAuth(AuthStrategy):
    """API key header authentication (X-API-Key: xxx or custom header)."""

    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self.api_key = api_key
        self.header_name = header_name

    def apply(self, headers: dict, **kwargs) -> dict:
        headers[self.header_name] = self.api_key
        return headers


class HmacSignatureAuth(AuthStrategy):
    """HMAC-based authentication (Kling, some Chinese providers)."""

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key

    def apply(
        self,
        headers: dict,
        method: str = "POST",
        path: str = "/",
        body: str = "",
        **kwargs,
    ) -> dict:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(8)

        sign_str = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}"
        signature = hmac.new(
            self.secret_key.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()

        headers["X-Access-Key"] = self.access_key
        headers["X-Timestamp"] = timestamp
        headers["X-Nonce"] = nonce
        headers["X-Signature"] = signature
        return headers


class VolcanoEngineAuth(AuthStrategy):
    """ByteDance Volcano Engine authentication (AWS Signature V4 style)."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str = "cn-north-1",
        service: str = "cv",
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.service = service

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(self, date_stamp: str) -> bytes:
        k_date = self._sign(self.secret_key.encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, "request")
        return k_signing

    def apply(
        self,
        headers: dict,
        method: str = "POST",
        path: str = "/",
        query: str = "",
        body: str = "",
        host: str = "",
        **kwargs,
    ) -> dict:
        t = datetime.now(UTC)
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = t.strftime("%Y%m%d")

        # Add required headers
        headers["X-Date"] = amz_date
        if host:
            headers["Host"] = host

        # Create canonical request
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        headers["X-Content-Sha256"] = payload_hash

        signed_headers = "host;x-content-sha256;x-date"
        canonical_headers = f"host:{host}\nx-content-sha256:{payload_hash}\nx-date:{amz_date}\n"

        canonical_request = (
            f"{method}\n{path}\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        # Create string to sign
        algorithm = "HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/request"
        string_to_sign = (
            f"{algorithm}\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        # Calculate signature
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Add authorization header
        authorization = (
            f"{algorithm} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        headers["Authorization"] = authorization

        return headers


# ============ Circuit Breaker ============


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: float = 60.0  # Seconds before trying half-open
    half_open_max_calls: int = 1  # Max concurrent calls in half-open state


class CircuitBreaker:
    """Circuit breaker for provider fault tolerance."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = "closed"  # closed, open, half-open
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0
        self._half_open_calls = 0

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time > self.config.timeout:
                self.state = "half-open"
                self._half_open_calls = 0
                logger.info(f"[CircuitBreaker:{self.name}] Transitioning to half-open")
                return True
            return False

        # Half-open state - allow limited calls
        if self._half_open_calls < self.config.half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == "half-open":
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = "closed"
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"[CircuitBreaker:{self.name}] Circuit closed")
        else:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "half-open":
            self.state = "open"
            self.success_count = 0
            logger.warning(f"[CircuitBreaker:{self.name}] Circuit reopened after half-open failure")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = "open"
            self.success_count = 0
            logger.warning(
                f"[CircuitBreaker:{self.name}] Circuit opened after {self.failure_count} failures"
            )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self.state = "closed"
        self.failure_count = 0
        self.success_count = 0
        self._half_open_calls = 0

    def get_status(self) -> dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
        }


class CircuitBreakerManager:
    """Manages circuit breakers for all providers."""

    _breakers: dict[str, CircuitBreaker] = {}

    @classmethod
    def get(cls, provider_name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        """Get or create a circuit breaker for a provider."""
        if provider_name not in cls._breakers:
            cls._breakers[provider_name] = CircuitBreaker(provider_name, config)
        return cls._breakers[provider_name]

    @classmethod
    def reset(cls, provider_name: str) -> bool:
        """Reset a specific circuit breaker."""
        if provider_name in cls._breakers:
            cls._breakers[provider_name].reset()
            return True
        return False

    @classmethod
    def reset_all(cls) -> None:
        """Reset all circuit breakers."""
        for breaker in cls._breakers.values():
            breaker.reset()

    @classmethod
    def get_all_status(cls) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in cls._breakers.items()}


# ============ Cost Tracking ============


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


class CostTracker:
    """Track generation costs across providers."""

    def __init__(self, budget_limit: float | None = None):
        self.budget_limit = budget_limit
        self.records: list[CostRecord] = []
        self._lock = asyncio.Lock()

    async def record(
        self,
        provider: str,
        model: str,
        cost: float,
        media_type: MediaType,
        resolution: str | None = None,
        duration: int | None = None,
    ) -> None:
        """Record a generation cost."""
        async with self._lock:
            self.records.append(
                CostRecord(
                    provider=provider,
                    model=model,
                    cost=cost,
                    timestamp=time.time(),
                    media_type=media_type,
                    resolution=resolution,
                    duration=duration,
                )
            )
            # Keep only last 10000 records
            if len(self.records) > 10000:
                self.records = self.records[-10000:]

    def get_total_cost(self, since: float = 0) -> float:
        """Get total cost since a timestamp."""
        return sum(r.cost for r in self.records if r.timestamp >= since)

    def get_cost_by_provider(self, since: float = 0) -> dict[str, float]:
        """Get costs grouped by provider."""
        costs: dict[str, float] = {}
        for r in self.records:
            if r.timestamp >= since:
                costs[r.provider] = costs.get(r.provider, 0) + r.cost
        return costs

    def get_cost_by_media_type(self, since: float = 0) -> dict[str, float]:
        """Get costs grouped by media type."""
        costs: dict[str, float] = {}
        for r in self.records:
            if r.timestamp >= since:
                key = r.media_type.value
                costs[key] = costs.get(key, 0) + r.cost
        return costs

    def is_within_budget(self, additional_cost: float = 0) -> bool:
        """Check if within budget limit."""
        if self.budget_limit is None:
            return True
        return self.get_total_cost() + additional_cost <= self.budget_limit

    def get_summary(self, since: float = 0) -> dict[str, Any]:
        """Get a summary of costs."""
        return {
            "total_cost": self.get_total_cost(since),
            "by_provider": self.get_cost_by_provider(since),
            "by_media_type": self.get_cost_by_media_type(since),
            "budget_limit": self.budget_limit,
            "within_budget": self.is_within_budget(),
            "record_count": len([r for r in self.records if r.timestamp >= since]),
        }


# ============ Provider Protocols ============


@runtime_checkable
class ImageProvider(Protocol):
    """Protocol that all image generation providers must implement."""

    @property
    def name(self) -> str:
        """Unique identifier for this provider (e.g., 'google', 'openai')."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for this provider."""
        ...

    @property
    def models(self) -> list[ProviderModel]:
        """List of models available from this provider."""
        ...

    @property
    def is_available(self) -> bool:
        """Check if the provider is currently available (has valid credentials)."""
        ...

    def get_default_model(self) -> ProviderModel | None:
        """Get the default model for this provider."""
        ...

    def validate_api_key(self) -> tuple[bool, str]:
        """
        Validate the configured API key.

        Returns:
            Tuple of (is_valid, message)
        """
        ...

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """
        Generate an image based on the request.

        Args:
            request: The generation request
            model_id: Optional specific model to use

        Returns:
            GenerationResult with the generated image or error
        """
        ...

    async def health_check(self) -> dict:
        """
        Perform a health check on this provider.

        Returns:
            Dict with 'status' ('healthy', 'degraded', 'unhealthy') and optional 'message'
        """
        ...


@runtime_checkable
class VideoProvider(Protocol):
    """Protocol that all video generation providers must implement."""

    @property
    def name(self) -> str:
        """Unique identifier for this provider."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for this provider."""
        ...

    @property
    def models(self) -> list[ProviderModel]:
        """List of models available from this provider."""
        ...

    @property
    def is_available(self) -> bool:
        """Check if the provider is currently available."""
        ...

    def get_default_model(self) -> ProviderModel | None:
        """Get the default model for this provider."""
        ...

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API key."""
        ...

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """
        Start video generation (usually async).

        Returns:
            GenerationResult with video_task_id for polling, or video_url if sync
        """
        ...

    async def get_task_status(self, task_id: str) -> dict:
        """
        Get the status of an async video generation task.

        Returns:
            Dict with 'status' ('queued', 'processing', 'completed', 'failed'),
            'progress' (0-100), and optionally 'video_url' or 'error'
        """
        ...

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        ...


# ============ Base Classes (Shared Implementations) ============


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    retry_delays: list[int] = field(default_factory=lambda: [2, 4, 8])
    retryable_status_codes: list[int] = field(default_factory=lambda: [502, 503, 504])


class TaskPollingMixin:
    """
    Mixin for providers that use async task polling pattern.

    Provides standardized task polling with exponential backoff for
    providers that return task_id instead of immediate results.
    """

    # Override these in subclasses as needed
    DEFAULT_POLL_INTERVAL: float = 2.0
    DEFAULT_TIMEOUT: float = 300.0
    MAX_POLL_INTERVAL: float = 10.0

    async def submit_task(
        self,
        request: "GenerationRequest",
        model: "ProviderModel",
    ) -> str:
        """
        Submit generation task, return task_id.

        Override in subclass to implement provider-specific task submission.

        Args:
            request: The generation request
            model: The model to use

        Returns:
            Task ID string
        """
        raise NotImplementedError("Subclass must implement submit_task")

    async def poll_task_status(self, task_id: str) -> TaskInfo:
        """
        Check task status.

        Override in subclass to implement provider-specific status polling.

        Args:
            task_id: The task ID to check

        Returns:
            TaskInfo with current status
        """
        raise NotImplementedError("Subclass must implement poll_task_status")

    async def download_result(self, result_url: str) -> bytes:
        """
        Download generated content from URL.

        Args:
            result_url: URL to download from (can be http/https URL or data: URL)

        Returns:
            Downloaded bytes
        """
        # Handle data URLs (base64 encoded content)
        if result_url.startswith("data:"):
            import base64

            # Format: data:[<mediatype>][;base64],<data>
            # Example: data:image/jpeg;base64,/9j/4AAQSkZJRg...
            try:
                header, data = result_url.split(",", 1)
                return base64.b64decode(data)
            except (ValueError, Exception) as e:
                raise ValueError(f"Invalid data URL format: {e}")

        # Always use a fresh client for downloading external URLs
        # Don't use the API client as it may have base_url and auth headers
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(result_url)
            response.raise_for_status()
            return response.content

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: float | None = None,
        poll_interval: float | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TaskInfo:
        """
        Poll until task completes with exponential backoff.

        Args:
            task_id: The task ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Initial polling interval
            on_progress: Optional callback for progress updates

        Returns:
            Final TaskInfo with status and result
        """
        timeout = timeout or self.DEFAULT_TIMEOUT
        interval = poll_interval or self.DEFAULT_POLL_INTERVAL
        start = time.time()

        while time.time() - start < timeout:
            try:
                info = await self.poll_task_status(task_id)

                if on_progress and info.progress is not None:
                    on_progress(info.progress)

                if info.status in ("completed", "failed", "cancelled"):
                    return info

                await asyncio.sleep(interval)
                # Exponential backoff with cap
                interval = min(interval * 1.5, self.MAX_POLL_INTERVAL)

            except Exception as e:
                logger.warning(f"Error polling task {task_id}: {e}")
                await asyncio.sleep(interval)

        return TaskInfo(
            task_id=task_id,
            status="timeout",
            error=f"Polling timed out after {timeout}s",
        )


class BaseProvider(ABC):
    """
    Abstract base class with shared logic for all providers.

    Provides common implementations for:
    - Model lookup (get_default_model, get_model_by_id)
    - Statistics recording
    - Result creation helpers
    """

    RETRY_CONFIG = RetryConfig()

    # Subclasses must set these
    _models: list[ProviderModel]
    _stats: list[dict]

    def get_default_model(self) -> ProviderModel | None:
        """Get the default model for this provider."""
        for model in self._models:
            if model.is_default:
                return model
        return self._models[0] if self._models else None

    def get_model_by_id(self, model_id: str) -> ProviderModel | None:
        """Get a specific model by ID."""
        for model in self._models:
            if model.id == model_id:
                return model
        return None

    def _record_stats(self, duration: float) -> None:
        """Record generation statistics."""
        self._stats.append({"duration": duration, "timestamp": time.time()})
        # Keep only last 100 stats
        if len(self._stats) > 100:
            self._stats = self._stats[-100:]

    def _create_result(self, media_type: MediaType) -> GenerationResult:
        """Create a new GenerationResult with provider info."""
        return GenerationResult(
            media_type=media_type,
            provider=self.name,
        )

    def _set_error(
        self,
        result: GenerationResult,
        error_msg: str,
        start_time: float,
        safety_blocked: bool = False,
    ) -> GenerationResult:
        """Set error information on a result."""
        result.error = error_msg
        result.error_type = "safety_blocked" if safety_blocked else classify_error(error_msg)
        result.safety_blocked = safety_blocked
        result.retryable = is_retryable_error(error_msg) if not safety_blocked else False
        result.duration = time.time() - start_time
        return result

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for this provider."""
        ...

    @property
    @abstractmethod
    def models(self) -> list[ProviderModel]:
        """List of models available from this provider."""
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is currently available."""
        ...

    @abstractmethod
    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API key."""
        ...


class HTTPProviderMixin:
    """
    Mixin for providers that use httpx for HTTP requests.

    Provides common implementations for:
    - HTTP client management
    - Async retry logic with exponential backoff
    - Error extraction from responses
    - Safety error detection
    """

    _client: httpx.AsyncClient | None = None
    _base_url: str
    _api_key: str
    RETRY_CONFIG: RetryConfig = RetryConfig()

    def _get_default_headers(self) -> dict:
        """
        Get default headers for requests. Override in subclasses for custom auth.

        Default implementation uses Bearer token authentication.
        """
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _get_client_timeout(self) -> float:
        """Get timeout for HTTP client. Override for longer timeouts."""
        return 120.0

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._get_default_headers(),
                timeout=self._get_client_timeout(),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _extract_error_from_response(self, response: httpx.Response) -> str:
        """
        Extract error message from response. Override for provider-specific formats.

        Default implementation looks for {"error": {"message": "..."}} format.
        """
        try:
            data = response.json()
            if isinstance(data.get("error"), dict):
                return data["error"].get("message", f"HTTP {response.status_code}")
            elif isinstance(data.get("error"), str):
                return data["error"]
            elif "message" in data:
                return data["message"]
            return f"HTTP {response.status_code}"
        except Exception:
            return f"HTTP {response.status_code}"

    def _is_safety_error(self, error_msg: str) -> bool:
        """Check if an error is a safety/content policy error."""
        error_lower = error_msg.lower()
        return any(
            keyword in error_lower
            for keyword in [
                "safety",
                "blocked",
                "content_policy",
                "content policy",
                "sensitive",
                "moderation",
                "violation",
            ]
        )

    async def _execute_with_retry(
        self,
        request_func: Callable[[], Any],
        result: GenerationResult,
        start_time: float,
        provider_name: str = "Provider",
    ) -> tuple[httpx.Response | None, str | None]:
        """
        Execute an async request function with retry logic.

        Args:
            request_func: Async function that makes the HTTP request
            result: GenerationResult to update on safety errors
            start_time: Start time for duration calculation
            provider_name: Provider name for logging

        Returns:
            Tuple of (response, last_error). Response is None if all retries failed.
        """
        last_error = None
        config = self.RETRY_CONFIG

        for attempt in range(config.max_retries + 1):
            try:
                response = await request_func()

                # Check for successful response
                if response.status_code in [200, 201]:
                    return response, None

                # Extract error message
                error_msg = self._extract_error_from_response(response)
                last_error = error_msg

                # Check for safety error (no retry)
                if self._is_safety_error(error_msg):
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return None, error_msg

                # Check if retryable
                if (
                    response.status_code in config.retryable_status_codes
                    or is_retryable_error(error_msg)
                ) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[{provider_name}] Retryable error on attempt {attempt + 1}: {error_msg}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error
                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[{provider_name}] Exception on attempt {attempt + 1}: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        return None, last_error


class BaseImageProvider(BaseProvider, ABC):
    """
    Abstract base class for image generation providers.

    Extends BaseProvider with image-specific functionality.
    """

    def _estimate_cost(self, model: ProviderModel, resolution: str) -> float:
        """
        Estimate cost for image generation. Override for provider-specific pricing.

        Default implementation uses resolution multipliers.
        """
        base_cost = model.pricing_per_unit
        resolution_multipliers = {"1K": 1.0, "2K": 1.5, "4K": 2.0}
        return base_cost * resolution_multipliers.get(resolution, 1.0)

    @abstractmethod
    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """Generate an image based on the request."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        ...


class BaseVideoProvider(BaseProvider, ABC):
    """
    Abstract base class for video generation providers.

    Extends BaseProvider with video-specific functionality including
    async task polling.
    """

    def _estimate_cost(self, model: ProviderModel, duration: int) -> float:
        """Estimate cost for video generation (price per second)."""
        return model.pricing_per_unit * duration

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: float = 5.0,
    ) -> dict:
        """
        Wait for a video generation task to complete.

        Args:
            task_id: The task ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks

        Returns:
            Final task status dict
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = await self.get_task_status(task_id)

            if status["status"] in ["completed", "failed", "cancelled"]:
                return status

            await asyncio.sleep(poll_interval)

        return {
            "status": "failed",
            "error": "Timeout waiting for video generation",
        }

    @abstractmethod
    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """Start video generation (usually async)."""
        ...

    @abstractmethod
    async def get_task_status(self, task_id: str) -> dict:
        """Get the status of an async video generation task."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        ...
