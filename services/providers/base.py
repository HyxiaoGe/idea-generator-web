"""
Base protocols and data classes for AI providers.

This module defines the core abstractions that all providers must implement,
ensuring a consistent interface across different AI vendors.

Submodules split out for focused responsibility:
- types.py: Enums, dataclasses
- auth.py: Authentication strategies
- circuit_breaker.py: Circuit breaker pattern
- cost.py: Cost tracking

Everything is re-exported here for backward compatibility.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

# Re-export from shared errors module
from services.errors import (  # noqa: F401
    ERROR_TYPE_CONNECTION,
    ERROR_TYPE_INVALID_KEY,
    ERROR_TYPE_OVERLOADED,
    ERROR_TYPE_RATE_LIMITED,
    ERROR_TYPE_SAFETY_BLOCKED,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_UNAVAILABLE,
    ERROR_TYPE_UNKNOWN,
    RETRYABLE_ERRORS,
    classify_error,
    get_friendly_error_message,
    is_retryable_error,
)

# Re-export from submodules
from .auth import (  # noqa: F401
    ApiKeyHeaderAuth,
    AuthStrategy,
    BearerTokenAuth,
    HmacSignatureAuth,
    VolcanoEngineAuth,
)
from .circuit_breaker import (  # noqa: F401
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
)
from .cost import CostTracker  # noqa: F401
from .types import (  # noqa: F401
    AuthType,
    CostRecord,
    ExecutionMode,
    GenerationRequest,
    GenerationResult,
    MediaType,
    ProviderCapability,
    ProviderConfig,
    ProviderModel,
    ProviderRegion,
    TaskInfo,
)

logger = logging.getLogger(__name__)


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
        """Get a specific model by ID or alias."""
        for model in self._models:
            if model.id == model_id:
                return model
        # Fallback: check aliases
        for model in self._models:
            if model_id in model.aliases:
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

    # Polling configuration (override in subclasses as needed)
    DEFAULT_POLL_INTERVAL: float = 5.0
    DEFAULT_TIMEOUT: float = 300.0
    MAX_POLL_INTERVAL: float = 30.0

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: float = 300,
        poll_interval: float = 5.0,
        on_progress: Callable[[float], None] | None = None,
    ) -> dict:
        """
        Wait for a video generation task to complete.

        Uses exponential backoff (capped at MAX_POLL_INTERVAL) and supports
        an optional progress callback.

        Args:
            task_id: The task ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Initial time between status checks
            on_progress: Optional callback invoked with progress (0.0-1.0)

        Returns:
            Final task status dict
        """
        start_time = time.time()
        interval = poll_interval

        while time.time() - start_time < timeout:
            try:
                status = await self.get_task_status(task_id)

                if on_progress and "progress" in status:
                    on_progress(status["progress"])

                if status["status"] in ["completed", "failed", "cancelled"]:
                    return status

                await asyncio.sleep(interval)
                # Exponential backoff with cap
                interval = min(interval * 1.5, self.MAX_POLL_INTERVAL)

            except Exception as e:
                logger.warning(f"Error polling video task {task_id}: {e}")
                await asyncio.sleep(interval)

        return {
            "status": "failed",
            "error": f"Timeout waiting for video generation after {timeout}s",
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
