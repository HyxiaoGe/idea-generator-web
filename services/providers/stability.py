"""
Stability AI Provider implementation.

This provider integrates with Stability AI's REST API for image generation
and editing, including Stable Diffusion 3.5, inpainting, outpainting, and upscaling.

API Documentation:
https://platform.stability.ai/docs/api-reference
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

STABILITY_MODELS = [
    ProviderModel(
        id="sd3.5-large",
        name="Stable Diffusion 3.5 Large",
        provider="stability",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.065,
        quality_score=0.88,
        latency_estimate=8.0,
        is_default=True,
        tier="balanced",
        strengths=["photorealism", "artistic-styles"],
    ),
    ProviderModel(
        id="stability-inpaint",
        name="Stability Inpaint",
        provider="stability",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.INPAINTING,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.03,
        quality_score=0.87,
        latency_estimate=6.0,
        is_default=False,
        tier="balanced",
        strengths=["inpainting", "editing"],
    ),
    ProviderModel(
        id="stability-outpaint",
        name="Stability Outpaint",
        provider="stability",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.OUTPAINTING,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.04,
        quality_score=0.86,
        latency_estimate=8.0,
        is_default=False,
        tier="balanced",
        strengths=["outpainting", "extension"],
    ),
    ProviderModel(
        id="stability-upscale",
        name="Stability Upscale",
        provider="stability",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.UPSCALING,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.025,
        quality_score=0.90,
        latency_estimate=5.0,
        is_default=False,
        tier="balanced",
        strengths=["upscaling", "enhancement"],
    ),
]

# Aspect ratio to width/height mapping
ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
}


class StabilityProvider(HTTPProviderMixin, BaseImageProvider):
    """
    Stability AI image generation and editing provider.

    Supports:
    - Text-to-image with Stable Diffusion 3.5
    - Inpainting (edit masked regions)
    - Outpainting (extend image borders)
    - Upscaling (enhance resolution)

    All endpoints use multipart/form-data requests.
    """

    RETRY_CONFIG = RetryConfig()

    def __init__(self, config: ProviderConfig | None = None):
        self._config = config or ProviderConfig()
        self._api_key = (
            self._config.api_key
            or os.getenv("PROVIDER_STABILITY_API_KEY")
            or os.getenv("STABILITY_API_KEY")
        )
        self._base_url = self._config.api_base_url or "https://api.stability.ai/v2beta/stable-image"
        self._models = STABILITY_MODELS.copy()
        self._client: httpx.AsyncClient | None = None
        self._stats: list[dict] = []

    @property
    def name(self) -> str:
        return "stability"

    @property
    def display_name(self) -> str:
        return "Stability AI"

    @property
    def models(self) -> list[ProviderModel]:
        return self._models

    @property
    def is_available(self) -> bool:
        return self._api_key is not None

    def validate_api_key(self) -> tuple[bool, str]:
        if not self._api_key or len(self._api_key) < 10:
            return False, "API key is too short"
        if not self._api_key.startswith("sk-"):
            return False, "Invalid API key format"
        return True, "API key format is valid"

    def _get_default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    @staticmethod
    def _image_to_bytes(img: Image.Image) -> bytes:
        """Convert PIL Image to PNG bytes."""
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()

    async def generate(
        self,
        request: GenerationRequest,
        model_id: str | None = None,
    ) -> GenerationResult:
        start_time = time.time()
        result = GenerationResult(
            media_type=MediaType.IMAGE,
            provider=self.name,
        )

        if not self._api_key:
            result.error = "Stability API key not configured"
            result.error_type = "invalid_key"
            return result

        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}"
            return result

        result.model = model.id

        # Route to the correct endpoint based on model capabilities
        if model.id == "stability-inpaint":
            return await self._inpaint(request, model, result, start_time)
        elif model.id == "stability-outpaint":
            return await self._outpaint(request, model, result, start_time)
        elif model.id == "stability-upscale":
            return await self._upscale(request, model, result, start_time)
        else:
            return await self._text_to_image(request, model, result, start_time)

    async def _text_to_image(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Generate image from text using SD3.5."""
        client = await self._get_client()

        width, height = ASPECT_RATIO_DIMENSIONS.get(request.aspect_ratio, (1024, 1024))

        data = {
            "prompt": request.prompt,
            "output_format": "png",
            "aspect_ratio": request.aspect_ratio.replace(":", ":"),
        }
        if request.negative_prompt:
            data["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            data["seed"] = str(request.seed)

        return await self._execute_request(
            client=client,
            endpoint="/generate/sd3",
            data=data,
            model=model,
            result=result,
            start_time=start_time,
        )

    async def _inpaint(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Inpaint masked regions of an image."""
        client = await self._get_client()

        if not request.reference_images:
            result.error = "Inpainting requires a reference image"
            result.error_type = "validation"
            return result

        source_bytes = self._image_to_bytes(request.reference_images[0])

        files = {
            "image": ("image.png", source_bytes, "image/png"),
        }

        if request.mask_image:
            mask_bytes = self._image_to_bytes(request.mask_image)
            files["mask"] = ("mask.png", mask_bytes, "image/png")

        data = {
            "prompt": request.prompt,
            "output_format": "png",
        }
        if request.negative_prompt:
            data["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            data["seed"] = str(request.seed)

        return await self._execute_request(
            client=client,
            endpoint="/edit/inpaint",
            data=data,
            files=files,
            model=model,
            result=result,
            start_time=start_time,
        )

    async def _outpaint(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Extend image beyond its borders."""
        client = await self._get_client()

        if not request.reference_images:
            result.error = "Outpainting requires a reference image"
            result.error_type = "validation"
            return result

        source_bytes = self._image_to_bytes(request.reference_images[0])

        files = {
            "image": ("image.png", source_bytes, "image/png"),
        }

        data = {
            "prompt": request.prompt,
            "output_format": "png",
        }
        if request.negative_prompt:
            data["negative_prompt"] = request.negative_prompt

        # Outpaint directions — default to extending all sides equally
        for direction in ("left", "right", "up", "down"):
            data[direction] = "128"

        return await self._execute_request(
            client=client,
            endpoint="/edit/outpaint",
            data=data,
            files=files,
            model=model,
            result=result,
            start_time=start_time,
        )

    async def _upscale(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Upscale image resolution."""
        client = await self._get_client()

        if not request.reference_images:
            result.error = "Upscaling requires a reference image"
            result.error_type = "validation"
            return result

        source_bytes = self._image_to_bytes(request.reference_images[0])

        files = {
            "image": ("image.png", source_bytes, "image/png"),
        }

        data = {
            "prompt": request.prompt or "Enhance this image",
            "output_format": "png",
        }

        return await self._execute_request(
            client=client,
            endpoint="/upscale/conservative",
            data=data,
            files=files,
            model=model,
            result=result,
            start_time=start_time,
        )

    async def _execute_request(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        data: dict,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
        files: dict | None = None,
    ) -> GenerationResult:
        """Execute a Stability API request with retry logic."""
        config = self.RETRY_CONFIG
        last_error = None

        # Headers for each request (no Content-Type, httpx sets it for multipart)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        for attempt in range(config.max_retries + 1):
            try:
                if files:
                    response = await client.post(
                        endpoint,
                        data=data,
                        files=files,
                        headers=headers,
                    )
                else:
                    response = await client.post(
                        endpoint,
                        data=data,
                        headers=headers,
                    )

                if response.status_code == 200:
                    resp_data = response.json()

                    # Stability returns base64 image in JSON response
                    image_b64 = resp_data.get("image")
                    if image_b64:
                        image_data = base64.b64decode(image_b64)
                        result.image = Image.open(BytesIO(image_data))
                        result.success = True
                        result.duration = time.time() - start_time
                        result.cost = model.pricing_per_unit
                        self._record_stats(result.duration)
                        return result

                    # Check artifacts array format
                    artifacts = resp_data.get("artifacts", [])
                    if artifacts:
                        art = artifacts[0]
                        if art.get("base64"):
                            image_data = base64.b64decode(art["base64"])
                            result.image = Image.open(BytesIO(image_data))
                            result.success = True
                            result.duration = time.time() - start_time
                            result.cost = model.pricing_per_unit
                            self._record_stats(result.duration)
                            return result

                        if art.get("finishReason") == "CONTENT_FILTERED":
                            result.safety_blocked = True
                            result.error = "Content blocked by safety filter"
                            result.error_type = "safety_blocked"
                            result.duration = time.time() - start_time
                            return result

                # Handle errors
                error_data = {}
                try:
                    error_data = response.json()
                except Exception:
                    pass
                error_msg = (
                    error_data.get("message")
                    or error_data.get("name")
                    or f"HTTP {response.status_code}"
                )
                last_error = error_msg

                if self._is_safety_error(error_msg):
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return result

                if is_retryable_error(error_msg) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[Stability] Retryable error on attempt {attempt + 1}: {error_msg}. "
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
                        f"[Stability] Exception on attempt {attempt + 1}: {e}. Retrying..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        result.error = last_error
        result.error_type = classify_error(last_error) if last_error else "unknown"
        result.retryable = is_retryable_error(last_error) if last_error else False
        result.duration = time.time() - start_time
        return result

    async def health_check(self) -> dict:
        if not self._api_key:
            return {"status": "unhealthy", "message": "API key not configured"}

        try:
            client = await self._get_client()
            start = time.time()

            # Check API reachability via account endpoint
            response = await client.get(
                "/user/account",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                },
                timeout=10.0,
            )
            latency = time.time() - start

            if response.status_code in [200, 401, 403]:
                status = "healthy" if response.status_code == 200 else "degraded"
                return {
                    "status": status,
                    "latency_ms": int(latency * 1000),
                    "models_available": len(self._models),
                }
            return {"status": "unhealthy", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)[:100]}
