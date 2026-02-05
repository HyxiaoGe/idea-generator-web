"""
Kling Video Provider implementation (Kuaishou).

This provider integrates with Kling's AI video generation API,
offering high-quality video generation with excellent price-performance ratio
and support for up to 3-minute videos.
"""

import asyncio
import base64
import contextlib
import logging
import os
import time
from io import BytesIO

import httpx
import jwt

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

KLING_MODELS = [
    ProviderModel(
        id="kling-2.0-pro",
        name="Kling 2.0 Pro",
        provider="kling",
        media_type=MediaType.VIDEO,
        capabilities=[
            ProviderCapability.TEXT_TO_VIDEO,
            ProviderCapability.IMAGE_TO_VIDEO,
        ],
        max_resolution="1080p",
        max_video_duration=180,  # Up to 3 minutes!
        supports_aspect_ratios=["16:9", "9:16", "1:1", "4:3", "3:4"],
        pricing_per_unit=0.02,  # Per second - very competitive
        quality_score=0.92,
        latency_estimate=90.0,
        is_default=True,
    ),
    ProviderModel(
        id="kling-2.0-standard",
        name="Kling 2.0 Standard",
        provider="kling",
        media_type=MediaType.VIDEO,
        capabilities=[
            ProviderCapability.TEXT_TO_VIDEO,
            ProviderCapability.IMAGE_TO_VIDEO,
        ],
        max_resolution="720p",
        max_video_duration=60,
        supports_aspect_ratios=["16:9", "9:16", "1:1"],
        pricing_per_unit=0.01,  # Budget option
        quality_score=0.85,
        latency_estimate=60.0,
        is_default=False,
    ),
    ProviderModel(
        id="kling-1.6",
        name="Kling 1.6",
        provider="kling",
        media_type=MediaType.VIDEO,
        capabilities=[
            ProviderCapability.TEXT_TO_VIDEO,
            ProviderCapability.IMAGE_TO_VIDEO,
        ],
        max_resolution="1080p",
        max_video_duration=30,
        supports_aspect_ratios=["16:9", "9:16", "1:1"],
        pricing_per_unit=0.015,
        quality_score=0.88,
        latency_estimate=45.0,
        is_default=False,
    ),
]

# Aspect ratio mapping for Kling API
ASPECT_RATIO_MAP = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
    "3:4": "3:4",
    "21:9": "16:9",  # Fallback
}


class KlingProvider(HTTPProviderMixin, BaseVideoProvider):
    """
    Kling video generation provider (Kuaishou).

    Supports:
    - Text-to-video generation with Kling 2.0
    - Image-to-video animation
    - Up to 3 minutes of video (industry-leading)
    - Excellent price-performance ratio
    - Audio-visual synchronization
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the Kling provider.

        Args:
            config: Optional provider configuration with API key
        """
        self._config = config or ProviderConfig()
        self._access_key = (
            self._config.api_key
            or os.getenv("PROVIDER_KLING_API_KEY")
            or os.getenv("KLING_ACCESS_KEY")
        )
        self._secret_key = (
            (self._config.extra.get("secret_key") if self._config.extra else None)
            or os.getenv("PROVIDER_KLING_SECRET_KEY")
            or os.getenv("KLING_SECRET_KEY")
        )
        self._base_url = self._config.api_base_url or "https://api.klingai.com/v1"
        self._api_key = self._access_key  # For HTTPProviderMixin compatibility
        self._models = KLING_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "kling"

    @property
    def display_name(self) -> str:
        return "Kling (Kuaishou)"

    @property
    def models(self) -> list[ProviderModel]:
        return self._models

    @property
    def is_available(self) -> bool:
        return self._access_key is not None and self._secret_key is not None

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API key."""
        if not self._access_key or len(self._access_key) < 10:
            return False, "Access key is too short"
        if not self._secret_key or len(self._secret_key) < 10:
            return False, "Secret key is too short"
        return True, "API keys format is valid"

    def _generate_auth_token(self) -> str:
        """
        Generate JWT authentication token for Kling API.

        Kling uses JWT (HS256) for authentication with:
        - iss: Access Key
        - exp: Expiration time (30 minutes from now)
        - nbf: Not valid before (5 seconds ago for clock skew)
        """
        headers = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "iss": self._access_key,
            "exp": int(time.time()) + 1800,  # Token expires in 30 minutes
            "nbf": int(time.time()) - 5,  # Token valid from 5 seconds ago
        }
        return jwt.encode(payload, self._secret_key, algorithm="HS256", headers=headers)

    def _get_default_headers(self) -> dict:
        """Get default headers (without auth, auth added per-request)."""
        return {
            "Content-Type": "application/json",
        }

    def _get_client_timeout(self) -> float:
        """Video generation needs longer timeout."""
        return 180.0

    def _get_auth_headers(self) -> dict:
        """Get authentication headers for the request."""
        return {
            "Authorization": f"Bearer {self._generate_auth_token()}",
        }

    def _get_api_model_name(self, model_id: str) -> str:
        """Convert internal model ID to API model name."""
        model_map = {
            "kling-2.0-pro": "kling-v2-pro",
            "kling-2.0-standard": "kling-v2-standard",
            "kling-1.6": "kling-v1.6",
        }
        return model_map.get(model_id, "kling-v2-pro")

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

        if not self._access_key or not self._secret_key:
            result.error = "Kling API keys not configured"
            result.error_type = "invalid_key"
            return result

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}"
            return result

        result.model = model.id

        # Validate and cap duration
        duration = request.duration or 5
        if duration > model.max_video_duration:
            duration = model.max_video_duration

        # Get client
        client = await self._get_client()

        # Check if this is image-to-video or text-to-video
        if request.reference_images and len(request.reference_images) > 0:
            return await self._generate_image_to_video(
                request, model, client, result, start_time, duration
            )
        else:
            return await self._generate_text_to_video(
                request, model, client, result, start_time, duration
            )

    async def _generate_text_to_video(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        client: httpx.AsyncClient,
        result: GenerationResult,
        start_time: float,
        duration: int,
    ) -> GenerationResult:
        """Generate video from text prompt."""
        api_model = self._get_api_model_name(model.id)
        aspect_ratio = ASPECT_RATIO_MAP.get(request.aspect_ratio, "16:9")

        payload = {
            "model": api_model,
            "prompt": request.prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "mode": "standard",  # or "professional"
        }

        # Add negative prompt if provided
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        # Add seed if specified
        if request.seed is not None:
            payload["seed"] = request.seed

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await client.post(
                    "/videos/text2video",
                    json=payload,
                    headers=self._get_auth_headers(),
                )

                if response.status_code in [200, 201]:
                    data = response.json()

                    # Kling returns task_id in the response
                    task_id = data.get("data", {}).get("task_id") or data.get("task_id")

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

                error_msg = (
                    error_data.get("message")
                    or error_data.get("error")
                    or f"HTTP {response.status_code}"
                )
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
                    logger.warning(f"[Kling] Retryable error: {error_msg}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(f"[Kling] Exception: {e}. Retrying in {delay}s...")
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
        duration: int,
    ) -> GenerationResult:
        """Generate video from image (animate image)."""
        api_model = self._get_api_model_name(model.id)
        aspect_ratio = ASPECT_RATIO_MAP.get(request.aspect_ratio, "16:9")

        # Convert first reference image to base64
        ref_image = request.reference_images[0]
        img_buffer = BytesIO()
        ref_image.save(img_buffer, format="PNG")
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")

        payload = {
            "model": api_model,
            "image": f"data:image/png;base64,{img_base64}",
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "mode": "standard",
        }

        # Add motion prompt if provided
        if request.prompt:
            payload["prompt"] = request.prompt

        # Add negative prompt if provided
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        # Add seed if specified
        if request.seed is not None:
            payload["seed"] = request.seed

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await client.post(
                    "/videos/image2video",
                    json=payload,
                    headers=self._get_auth_headers(),
                )

                if response.status_code in [200, 201]:
                    data = response.json()
                    task_id = data.get("data", {}).get("task_id") or data.get("task_id")

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

                error_msg = (
                    error_data.get("message")
                    or error_data.get("error")
                    or f"HTTP {response.status_code}"
                )
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
                    logger.warning(f"[Kling] Retryable error: {error_msg}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(f"[Kling] Exception: {e}. Retrying in {delay}s...")
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
        if not self._access_key or not self._secret_key:
            return {
                "status": "failed",
                "error": "API keys not configured",
            }

        client = await self._get_client()

        try:
            response = await client.get(
                f"/videos/tasks/{task_id}",
                headers=self._get_auth_headers(),
            )

            if response.status_code == 200:
                data = response.json()
                task_data = data.get("data", data)
                status = task_data.get("status", "unknown")

                # Map Kling status to our standard status
                status_map = {
                    "pending": "queued",
                    "processing": "processing",
                    "running": "processing",
                    "completed": "completed",
                    "success": "completed",
                    "failed": "failed",
                    "error": "failed",
                    "cancelled": "cancelled",
                }
                mapped_status = status_map.get(status.lower(), status.lower())

                result = {
                    "status": mapped_status,
                    "progress": task_data.get("progress", 0),
                }

                # Add video URL if completed
                if mapped_status == "completed":
                    video_url = task_data.get("video_url") or task_data.get("output", {}).get(
                        "video_url"
                    )
                    if video_url:
                        result["video_url"] = video_url

                    # Also check for thumbnail
                    thumbnail_url = task_data.get("thumbnail_url") or task_data.get(
                        "output", {}
                    ).get("thumbnail_url")
                    if thumbnail_url:
                        result["thumbnail_url"] = thumbnail_url

                # Add error if failed
                if mapped_status == "failed":
                    result["error"] = (
                        task_data.get("error_message")
                        or task_data.get("message")
                        or "Unknown error"
                    )

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

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 600,  # Kling can generate up to 3 minutes, so longer timeout
        poll_interval: float = 10.0,
    ) -> dict:
        """Wait for completion with Kling-specific longer timeout."""
        return await super().wait_for_completion(task_id, timeout, poll_interval)

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self._access_key or not self._secret_key:
            return {
                "status": "unhealthy",
                "message": "API keys not configured",
            }

        try:
            client = await self._get_client()
            start = time.time()

            # Check API connectivity by making a simple request
            response = await client.get(
                "/account/quota",  # Or another lightweight endpoint
                headers=self._get_auth_headers(),
            )
            latency = time.time() - start

            if response.status_code in [200, 401, 403]:
                # 401/403 means API is reachable but auth might have issues
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
