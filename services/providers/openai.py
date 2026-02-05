"""
OpenAI GPT-Image/DALL-E Provider implementation.

This provider integrates with OpenAI's image generation APIs,
including GPT-Image-1 and DALL-E 3 models.
"""

import asyncio
import base64
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

OPENAI_MODELS = [
    ProviderModel(
        id="gpt-image-1",
        name="GPT Image 1",
        provider="openai",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
            ProviderCapability.IMAGE_TO_IMAGE,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.04,  # Medium quality
        quality_score=0.92,
        latency_estimate=10.0,
        is_default=True,
    ),
    ProviderModel(
        id="gpt-image-1-hd",
        name="GPT Image 1 HD",
        provider="openai",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.08,  # High quality
        quality_score=0.95,
        latency_estimate=15.0,
        is_default=False,
    ),
    ProviderModel(
        id="dall-e-3",
        name="DALL-E 3",
        provider="openai",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.04,  # Standard
        quality_score=0.88,
        latency_estimate=12.0,
        is_default=False,
    ),
    ProviderModel(
        id="dall-e-3-hd",
        name="DALL-E 3 HD",
        provider="openai",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16"],
        pricing_per_unit=0.08,  # HD
        quality_score=0.90,
        latency_estimate=15.0,
        is_default=False,
    ),
]

# Resolution mapping
RESOLUTION_MAP = {
    "1K": "1024x1024",
    "2K": "1792x1024",  # Landscape
    "4K": "1792x1024",  # Max for DALL-E
}

ASPECT_RATIO_SIZES = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:3": "1024x1024",  # Fallback
    "3:4": "1024x1024",  # Fallback
}


class OpenAIProvider(HTTPProviderMixin, BaseImageProvider):
    """
    OpenAI GPT-Image/DALL-E image generation provider.

    Supports:
    - Text-to-image generation with GPT-Image-1 and DALL-E 3
    - Multiple quality tiers (standard, HD)
    - Various aspect ratios
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the OpenAI provider.

        Args:
            config: Optional provider configuration with API key.
                    Supports third-party proxies like OpenRouter by setting api_base_url.
        """
        self._config = config or ProviderConfig()
        self._api_key = (
            self._config.api_key
            or os.getenv("PROVIDER_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self._base_url = (
            self._config.api_base_url
            or os.getenv("PROVIDER_OPENAI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self._models = OPENAI_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []
        # Extra headers for third-party proxies (e.g., OpenRouter)
        self._extra_headers = self._config.extra.get("headers", {}) if self._config.extra else {}

    @property
    def name(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI"

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

        # Skip format check for third-party proxies (they may use different key formats)
        if self._base_url != "https://api.openai.com/v1":
            return True, "API key format is valid (third-party proxy)"

        # Official OpenAI key format check
        if not self._api_key.startswith("sk-"):
            return False, "Invalid API key format"

        return True, "API key format is valid"

    def _get_default_headers(self) -> dict:
        """Get default headers with extra headers for third-party proxies."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self._extra_headers)
        return headers

    def _get_size_for_request(self, aspect_ratio: str, resolution: str) -> str:
        """Get the appropriate size string for the API request."""
        # Use aspect ratio if available
        if aspect_ratio in ASPECT_RATIO_SIZES:
            return ASPECT_RATIO_SIZES[aspect_ratio]
        return RESOLUTION_MAP.get(resolution, "1024x1024")

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
            result.error = "OpenAI API key not configured"
            result.error_type = "invalid_key"
            return result

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}"
            return result

        result.model = model.id

        # Determine API endpoint and parameters based on model
        if model.id.startswith("gpt-image"):
            return await self._generate_gpt_image(request, model, result, start_time)
        else:
            return await self._generate_dalle(request, model, result, start_time)

    async def _generate_gpt_image(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Generate using GPT-Image API."""
        client = await self._get_client()

        # Determine quality
        quality = "hd" if "hd" in model.id else "medium"

        # Build request payload
        payload = {
            "model": "gpt-image-1",
            "prompt": request.prompt,
            "n": 1,
            "size": self._get_size_for_request(request.aspect_ratio, request.resolution),
            "quality": quality,
            "response_format": "b64_json",
        }

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await client.post("/images/generations", json=payload)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("data") and len(data["data"]) > 0:
                        image_b64 = data["data"][0].get("b64_json")
                        if image_b64:
                            image_data = base64.b64decode(image_b64)
                            result.image = Image.open(BytesIO(image_data))
                            result.success = True
                            result.duration = time.time() - start_time
                            result.cost = self._estimate_cost(model, request.resolution)
                            self._record_stats(result.duration)
                            return result

                        # Check for URL response
                        image_url = data["data"][0].get("url")
                        if image_url:
                            # Download image from URL
                            img_response = await client.get(image_url)
                            if img_response.status_code == 200:
                                result.image = Image.open(BytesIO(img_response.content))
                                result.success = True
                                result.duration = time.time() - start_time
                                result.cost = self._estimate_cost(model, request.resolution)
                                self._record_stats(result.duration)
                                return result

                # Handle errors
                error_data = response.json() if response.status_code != 200 else {}
                error_msg = error_data.get("error", {}).get(
                    "message", f"HTTP {response.status_code}"
                )
                last_error = error_msg

                # Check for safety filter
                if self._is_safety_error(error_msg):
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return result

                # Check if retryable
                if is_retryable_error(error_msg) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[OpenAI] Retryable error on attempt {attempt + 1}: {error_msg}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue

                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(f"[OpenAI] Exception on attempt {attempt + 1}: {e}. Retrying...")
                    await asyncio.sleep(delay)
                    continue
                break

        result.error = last_error
        result.error_type = classify_error(last_error) if last_error else "unknown"
        result.retryable = is_retryable_error(last_error) if last_error else False
        result.duration = time.time() - start_time
        return result

    async def _generate_dalle(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Generate using DALL-E API."""
        client = await self._get_client()

        # Determine quality
        quality = "hd" if "hd" in model.id else "standard"

        # Build request payload
        payload = {
            "model": "dall-e-3",
            "prompt": request.prompt,
            "n": 1,
            "size": self._get_size_for_request(request.aspect_ratio, request.resolution),
            "quality": quality,
            "response_format": "b64_json",
        }

        # Execute with retry
        config = self.RETRY_CONFIG
        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                response = await client.post("/images/generations", json=payload)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("data") and len(data["data"]) > 0:
                        image_b64 = data["data"][0].get("b64_json")
                        if image_b64:
                            image_data = base64.b64decode(image_b64)
                            result.image = Image.open(BytesIO(image_data))
                            result.success = True

                            # DALL-E 3 may revise the prompt
                            revised_prompt = data["data"][0].get("revised_prompt")
                            if revised_prompt:
                                result.text_response = f"Revised prompt: {revised_prompt}"

                            result.duration = time.time() - start_time
                            result.cost = self._estimate_cost(model, request.resolution)
                            self._record_stats(result.duration)
                            return result

                # Handle errors
                error_data = response.json() if response.status_code != 200 else {}
                error_msg = error_data.get("error", {}).get(
                    "message", f"HTTP {response.status_code}"
                )
                last_error = error_msg

                # Check for safety filter
                if self._is_safety_error(error_msg):
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return result

                # Check if retryable
                if is_retryable_error(error_msg) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[OpenAI/DALL-E] Retryable error on attempt {attempt + 1}: {error_msg}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue

                break

            except Exception as e:
                last_error = str(e)
                if is_retryable_error(last_error) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[OpenAI/DALL-E] Exception on attempt {attempt + 1}: {e}. Retrying..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        result.error = last_error
        result.error_type = classify_error(last_error) if last_error else "unknown"
        result.retryable = is_retryable_error(last_error) if last_error else False
        result.duration = time.time() - start_time
        return result

    def _estimate_cost(self, model: ProviderModel, resolution: str) -> float:
        """Estimate cost for a generation. OpenAI charges same for all sizes."""
        return model.pricing_per_unit

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

            # Simple models list request to verify API key
            response = await client.get("/models")
            latency = time.time() - start

            if response.status_code == 200:
                return {
                    "status": "healthy",
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
