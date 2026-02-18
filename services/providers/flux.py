"""
FLUX Provider implementation (Black Forest Labs).

This provider integrates with Black Forest Labs' FLUX API for image generation,
offering high-quality images at competitive pricing.
"""

import asyncio
import logging
import os
import time
from io import BytesIO

import httpx
from PIL import Image

from .base import (
    BaseImageProvider,
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

FLUX_MODELS = [
    ProviderModel(
        id="flux-2-pro",
        name="FLUX 2 Pro",
        provider="bfl",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21"],
        pricing_per_unit=0.05,
        quality_score=0.93,
        latency_estimate=8.0,
        is_default=True,
        tier="premium",
        arena_rank=2,
        arena_score=1220,
        strengths=["photorealism", "prompt-adherence", "detail"],
    ),
    ProviderModel(
        id="flux-1.1-pro",
        name="FLUX 1.1 Pro",
        provider="bfl",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.04,
        quality_score=0.90,
        latency_estimate=6.0,
        is_default=False,
        tier="balanced",
        strengths=["speed", "quality-balance"],
    ),
    ProviderModel(
        id="flux-dev",
        name="FLUX Dev",
        provider="bfl",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.025,
        quality_score=0.85,
        latency_estimate=5.0,
        is_default=False,
        tier="fast",
        strengths=["speed", "cost-effective"],
    ),
    ProviderModel(
        id="flux-schnell",
        name="FLUX Schnell",
        provider="bfl",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="1K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.014,
        quality_score=0.80,
        latency_estimate=2.0,
        is_default=False,
        tier="fast",
        strengths=["speed", "cheapest"],
    ),
]

# Aspect ratio to width/height mapping
ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
    "21:9": (1536, 640),
    "9:21": (640, 1536),
}

# Resolution multipliers
RESOLUTION_MULTIPLIERS = {
    "1K": 1.0,
    "2K": 1.5,
    "4K": 2.0,
}


class FluxProvider(HTTPProviderMixin, BaseImageProvider):
    """
    FLUX image generation provider (Black Forest Labs).

    Supports:
    - Text-to-image generation with FLUX 2 Pro, 1.1 Pro, Dev, and Schnell
    - Multiple aspect ratios
    - High quality at competitive pricing
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the FLUX provider.

        Args:
            config: Optional provider configuration with API key
        """
        self._config = config or ProviderConfig()
        self._api_key = self._config.api_key or os.getenv("BFL_API_KEY")
        self._base_url = self._config.api_base_url or "https://api.bfl.ml/v1"
        self._models = FLUX_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "bfl"

    @property
    def display_name(self) -> str:
        return "FLUX (Black Forest Labs)"

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
        """Get headers with X-Key authentication for FLUX."""
        return {
            "X-Key": self._api_key,
            "Content-Type": "application/json",
        }

    def _get_dimensions(self, aspect_ratio: str, resolution: str) -> tuple[int, int]:
        """Get width and height for the request."""
        base_w, base_h = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))
        multiplier = RESOLUTION_MULTIPLIERS.get(resolution, 1.0)

        # Apply multiplier and round to nearest 64 (FLUX requirement)
        width = int(base_w * multiplier)
        height = int(base_h * multiplier)

        # Round to nearest 64
        width = ((width + 32) // 64) * 64
        height = ((height + 32) // 64) * 64

        # Cap at max dimensions
        width = min(width, 2048)
        height = min(height, 2048)

        return width, height

    def _get_api_model_name(self, model_id: str) -> str:
        """Convert internal model ID to API model name."""
        model_map = {
            "flux-2-pro": "flux-pro-1.1",  # Latest pro model
            "flux-1.1-pro": "flux-pro-1.1",
            "flux-dev": "flux-dev",
            "flux-schnell": "flux-schnell",
        }
        return model_map.get(model_id, "flux-pro-1.1")

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        """Generate an image based on the request."""
        start_time = time.time()
        result = GenerationResult(
            media_type=MediaType.IMAGE,
            provider=self.name,
        )

        if not self._api_key:
            result.error = "FLUX API key not configured"
            result.error_type = "invalid_key"
            return result

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}"
            return result

        result.model = model.id

        # Get dimensions
        width, height = self._get_dimensions(request.aspect_ratio, request.resolution)

        # Get client
        client = await self._get_client()

        # Build request payload
        api_model = self._get_api_model_name(model.id)
        payload = {
            "prompt": request.prompt,
            "width": width,
            "height": height,
        }

        # Add seed if specified
        if request.seed is not None:
            payload["seed"] = request.seed

        # Add negative prompt if specified
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                # Step 1: Submit generation request
                response = await client.post(f"/{api_model}", json=payload)

                if response.status_code != 200:
                    error_data = (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    error_msg = error_data.get("error", {}).get(
                        "message", f"HTTP {response.status_code}"
                    )
                    last_error = error_msg

                    if is_retryable_error(error_msg) and attempt < config.max_retries:
                        delay = config.retry_delays[attempt]
                        logger.warning(
                            f"[FLUX] Retryable error: {error_msg}. Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    break

                data = response.json()
                task_id = data.get("id")

                if not task_id:
                    last_error = "No task ID returned"
                    break

                # Step 2: Poll for result
                poll_url = f"/get_result?id={task_id}"
                max_polls = 60  # Max 2 minutes of polling
                poll_interval = 2.0

                for _poll in range(max_polls):
                    await asyncio.sleep(poll_interval)

                    poll_response = await client.get(poll_url)

                    if poll_response.status_code != 200:
                        continue

                    poll_data = poll_response.json()
                    status = poll_data.get("status")

                    if status == "Ready":
                        # Get image URL and download
                        image_url = poll_data.get("result", {}).get("sample")

                        if image_url:
                            img_response = await client.get(image_url)
                            if img_response.status_code == 200:
                                result.image = Image.open(BytesIO(img_response.content))
                                result.success = True
                                result.duration = time.time() - start_time
                                result.cost = self._estimate_cost(model, request.resolution)
                                self._record_stats(result.duration)
                                return result

                        last_error = "Failed to download generated image"
                        break

                    elif status == "Failed" or status == "Error":
                        last_error = poll_data.get("error", "Generation failed")

                        # Check for content policy
                        if self._is_safety_error(last_error):
                            result.safety_blocked = True
                            result.error = "Content blocked by safety filter"
                            result.error_type = "safety_blocked"
                            result.duration = time.time() - start_time
                            return result

                        break

                    elif status == "Pending" or status == "Processing":
                        continue

                    else:
                        # Unknown status
                        continue

                # Polling timeout
                if not last_error:
                    last_error = "Generation timed out"

                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(f"[FLUX] Exception: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                break

        result.error = last_error
        result.error_type = classify_error(last_error) if last_error else "unknown"
        result.retryable = is_retryable_error(last_error) if last_error else False
        result.duration = time.time() - start_time
        return result

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

            # Simple request to verify API connectivity
            # BFL doesn't have a dedicated health endpoint, so we'll check if we can reach the API
            await client.get("/")
            latency = time.time() - start

            # Any response indicates the API is reachable
            return {
                "status": "healthy",
                "latency_ms": int(latency * 1000),
                "models_available": len(self._models),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": str(e)[:100],
            }
