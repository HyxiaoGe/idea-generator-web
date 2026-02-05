"""
Runway Video Provider implementation.

This provider integrates with Runway's Gen-4/4.5 API for video generation,
offering high-quality AI video generation with professional-grade output.
"""

import asyncio
import base64
import contextlib
import logging
import os
import time
from io import BytesIO

import httpx

from .base import (
    BaseVideoProvider,
    GenerationRequest,
    GenerationResult,
    HTTPProviderMixin,
    MediaType,
    ProviderCapability,
    ProviderConfig,
    ProviderModel,
    RetryConfig,
    classify_error,
    is_retryable_error,
)

logger = logging.getLogger(__name__)


# ============ Model Definitions ============

RUNWAY_MODELS = [
    ProviderModel(
        id="gen-4",
        name="Gen-4",
        provider="runway",
        media_type=MediaType.VIDEO,
        capabilities=[
            ProviderCapability.TEXT_TO_VIDEO,
            ProviderCapability.IMAGE_TO_VIDEO,
        ],
        max_resolution="1080p",
        max_video_duration=40,  # seconds
        supports_aspect_ratios=["16:9", "9:16", "1:1"],
        pricing_per_unit=0.05,  # Per second of video
        quality_score=0.95,
        latency_estimate=60.0,  # Average generation time
        is_default=True,
    ),
    ProviderModel(
        id="gen-4-turbo",
        name="Gen-4 Turbo",
        provider="runway",
        media_type=MediaType.VIDEO,
        capabilities=[
            ProviderCapability.TEXT_TO_VIDEO,
            ProviderCapability.IMAGE_TO_VIDEO,
        ],
        max_resolution="1080p",
        max_video_duration=10,  # Shorter for faster generation
        supports_aspect_ratios=["16:9", "9:16", "1:1"],
        pricing_per_unit=0.03,  # Lower cost, faster
        quality_score=0.88,
        latency_estimate=30.0,
        is_default=False,
    ),
    ProviderModel(
        id="gen-3a",
        name="Gen-3 Alpha",
        provider="runway",
        media_type=MediaType.VIDEO,
        capabilities=[
            ProviderCapability.TEXT_TO_VIDEO,
            ProviderCapability.IMAGE_TO_VIDEO,
        ],
        max_resolution="1080p",
        max_video_duration=10,
        supports_aspect_ratios=["16:9", "9:16", "1:1"],
        pricing_per_unit=0.05,
        quality_score=0.90,
        latency_estimate=45.0,
        is_default=False,
    ),
]

# Aspect ratio mapping for Runway API
ASPECT_RATIO_MAP = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "16:9",  # Fallback
    "3:4": "9:16",  # Fallback
    "21:9": "16:9",  # Fallback
}


class RunwayProvider(HTTPProviderMixin, BaseVideoProvider):
    """
    Runway video generation provider.

    Supports:
    - Text-to-video generation with Gen-4/4.5
    - Image-to-video animation
    - Multiple aspect ratios
    - Professional-grade video output
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the Runway provider.

        Args:
            config: Optional provider configuration with API key
        """
        self._config = config or ProviderConfig()
        self._api_key = self._config.api_key or os.getenv("RUNWAY_API_KEY")
        self._base_url = self._config.api_base_url or "https://api.dev.runwayml.com/v1"
        self._models = RUNWAY_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "runway"

    @property
    def display_name(self) -> str:
        return "Runway"

    @property
    def models(self) -> list[ProviderModel]:
        return self._models

    @property
    def is_available(self) -> bool:
        return self._api_key is not None

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API key."""
        if not self._api_key or len(self._api_key) < 10:
            return False, "API key is too short"
        return True, "API key format is valid"

    def _get_default_headers(self) -> dict:
        """Get headers with Bearer auth and Runway version."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        }

    def _get_client_timeout(self) -> float:
        """Video generation needs longer timeout."""
        return 180.0

    def _get_api_model_name(self, model_id: str) -> str:
        """Convert internal model ID to API model name."""
        model_map = {
            "gen-4": "gen4_turbo",  # Use gen4_turbo as the actual API name
            "gen-4-turbo": "gen4_turbo",
            "gen-3a": "gen3a_turbo",
        }
        return model_map.get(model_id, "gen4_turbo")

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """
        Start video generation (async).

        Args:
            request: The generation request
            model_id: Optional specific model to use

        Returns:
            GenerationResult with video_task_id for polling
        """
        start_time = time.time()
        result = GenerationResult(
            media_type=MediaType.VIDEO,
            provider=self.name,
        )

        if not self._api_key:
            result.error = "Runway API key not configured"
            result.error_type = "invalid_key"
            return result

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}"
            return result

        result.model = model.id

        # Validate duration
        duration = request.duration or 5
        if duration > model.max_video_duration:
            duration = model.max_video_duration

        # Get client
        client = await self._get_client()

        # Build request payload
        self._get_api_model_name(model.id)
        aspect_ratio = ASPECT_RATIO_MAP.get(request.aspect_ratio, "16:9")

        # Check if this is image-to-video or text-to-video
        if request.reference_images and len(request.reference_images) > 0:
            return await self._generate_image_to_video(
                request, model, client, result, start_time, aspect_ratio, duration
            )
        else:
            return await self._generate_text_to_video(
                request, model, client, result, start_time, aspect_ratio, duration
            )

    async def _generate_text_to_video(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        client: httpx.AsyncClient,
        result: GenerationResult,
        start_time: float,
        aspect_ratio: str,
        duration: int,
    ) -> GenerationResult:
        """Generate video from text prompt."""
        api_model = self._get_api_model_name(model.id)

        payload = {
            "model": api_model,
            "promptText": request.prompt,
            "ratio": aspect_ratio,
            "duration": duration,
        }

        # Add seed if specified
        if request.seed is not None:
            payload["seed"] = request.seed

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await client.post("/tasks", json=payload)

                if response.status_code in [200, 201]:
                    data = response.json()
                    task_id = data.get("id")

                    if task_id:
                        result.video_task_id = task_id
                        result.success = True
                        result.duration = time.time() - start_time
                        result.cost = self._estimate_cost(model, duration)
                        return result
                    else:
                        last_error = "No task ID returned"
                        break

                # Handle errors
                error_data = {}
                with contextlib.suppress(Exception):
                    error_data = response.json()
                error_msg = error_data.get("error", f"HTTP {response.status_code}")
                last_error = error_msg

                # Check for content policy
                if self._is_safety_error(error_msg):
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return result

                if is_retryable_error(error_msg) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[Runway] Retryable error: {error_msg}. Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(f"[Runway] Exception: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                break

        result.error = last_error
        result.error_type = classify_error(last_error) if last_error else "unknown"
        result.retryable = is_retryable_error(last_error) if last_error else False
        result.duration = time.time() - start_time
        return result

    async def _generate_image_to_video(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        client: httpx.AsyncClient,
        result: GenerationResult,
        start_time: float,
        aspect_ratio: str,
        duration: int,
    ) -> GenerationResult:
        """Generate video from image (animate image)."""
        api_model = self._get_api_model_name(model.id)

        # Convert first reference image to base64
        ref_image = request.reference_images[0]
        img_buffer = BytesIO()
        ref_image.save(img_buffer, format="PNG")
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")

        payload = {
            "model": api_model,
            "promptImage": f"data:image/png;base64,{img_base64}",
            "ratio": aspect_ratio,
            "duration": duration,
        }

        # Add text prompt if provided
        if request.prompt:
            payload["promptText"] = request.prompt

        # Add seed if specified
        if request.seed is not None:
            payload["seed"] = request.seed

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await client.post("/tasks", json=payload)

                if response.status_code in [200, 201]:
                    data = response.json()
                    task_id = data.get("id")

                    if task_id:
                        result.video_task_id = task_id
                        result.success = True
                        result.duration = time.time() - start_time
                        result.cost = self._estimate_cost(model, duration)
                        return result
                    else:
                        last_error = "No task ID returned"
                        break

                # Handle errors
                error_data = {}
                with contextlib.suppress(Exception):
                    error_data = response.json()
                error_msg = error_data.get("error", f"HTTP {response.status_code}")
                last_error = error_msg

                # Check for content policy
                if self._is_safety_error(error_msg):
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return result

                if is_retryable_error(error_msg) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[Runway] Retryable error: {error_msg}. Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(f"[Runway] Exception: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                break

        result.error = last_error
        result.error_type = classify_error(last_error) if last_error else "unknown"
        result.retryable = is_retryable_error(last_error) if last_error else False
        result.duration = time.time() - start_time
        return result

    async def get_task_status(self, task_id: str) -> dict:
        """
        Get the status of an async video generation task.

        Args:
            task_id: The task ID to check

        Returns:
            Dict with status, progress, and optionally video_url or error
        """
        if not self._api_key:
            return {
                "status": "failed",
                "error": "API key not configured",
            }

        client = await self._get_client()

        try:
            response = await client.get(f"/tasks/{task_id}")

            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")

                # Map Runway status to our standard status
                status_map = {
                    "PENDING": "queued",
                    "RUNNING": "processing",
                    "SUCCEEDED": "completed",
                    "FAILED": "failed",
                    "CANCELLED": "cancelled",
                }
                mapped_status = status_map.get(status, status.lower())

                result = {
                    "status": mapped_status,
                    "progress": data.get("progress", 0),
                }

                # Add video URL if completed
                if mapped_status == "completed":
                    output = data.get("output", [])
                    if output and len(output) > 0:
                        result["video_url"] = output[0]

                # Add error if failed
                if mapped_status == "failed":
                    result["error"] = data.get("failure", "Unknown error")
                    failure_code = data.get("failureCode")
                    if failure_code:
                        result["error_code"] = failure_code

                return result

            else:
                return {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self._api_key:
            return {
                "status": "unhealthy",
                "message": "API key not configured",
            }

        try:
            client = await self._get_client()
            start = time.time()

            # Check API connectivity by listing recent tasks (limited)
            response = await client.get("/tasks?limit=1")
            latency = time.time() - start

            if response.status_code in [200, 401]:
                # 401 means API is reachable but key might be invalid
                # 200 means everything works
                status = "healthy" if response.status_code == 200 else "degraded"
                return {
                    "status": status,
                    "latency_ms": int(latency * 1000),
                    "models_available": len(self._models),
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"API returned {response.status_code}",
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": str(e)[:100],
            }
