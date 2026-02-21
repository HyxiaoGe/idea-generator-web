"""
Google Gemini/Imagen Provider implementation.

This provider integrates with Google's generative AI APIs for image generation,
including Gemini 3 Pro Image and Imagen 4 models.
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from io import BytesIO
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

from .base import (
    BaseImageProvider,
    GenerationRequest,
    GenerationResult,
    MediaType,
    ProviderCapability,
    ProviderConfig,
    ProviderModel,
    RetryConfig,
    is_retryable_error,
)

logger = logging.getLogger(__name__)


# ============ Safety Configuration ============

SAFETY_LEVELS = {
    "strict": types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    "moderate": types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    "relaxed": types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    "none": types.HarmBlockThreshold.BLOCK_NONE,
}

HARM_CATEGORIES = [
    types.HarmCategory.HARM_CATEGORY_HARASSMENT,
    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
]


def build_safety_settings(level: str = "moderate") -> list[types.SafetySetting]:
    """Build safety settings based on the specified level."""
    threshold = SAFETY_LEVELS.get(level, types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)
    return [
        types.SafetySetting(category=category, threshold=threshold) for category in HARM_CATEGORIES
    ]


# ============ Model Definitions ============

GOOGLE_MODELS = [
    ProviderModel(
        id="gemini-3-pro-image-preview",
        name="Gemini 3 Pro Image",
        provider="google",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
            ProviderCapability.IMAGE_BLEND,
            ProviderCapability.SEARCH_GROUNDED,
            ProviderCapability.MULTI_TURN_CHAT,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.04,
        quality_score=0.90,
        latency_estimate=8.0,
        is_default=True,
        tier="balanced",
        arena_rank=5,
        arena_score=1185,
        strengths=["versatility", "multi-turn", "search-grounded"],
    ),
    ProviderModel(
        id="imagen-4.0-generate-001",
        name="Imagen 4",
        provider="google",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.04,
        quality_score=0.95,
        latency_estimate=10.0,
        is_default=False,
        tier="premium",
        arena_rank=3,
        arena_score=1200,
        strengths=["photorealism", "detail", "text-rendering"],
    ),
    ProviderModel(
        id="imagen-4.0-ultra-generate-001",
        name="Imagen 4 Ultra",
        provider="google",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="4K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.06,
        quality_score=0.97,
        latency_estimate=18.0,
        is_default=False,
        tier="premium",
        arena_rank=12,
        arena_score=1149,
        strengths=["ultra-detail", "photorealism", "4K"],
    ),
    ProviderModel(
        id="imagen-4.0-fast-generate-001",
        name="Imagen 4 Fast",
        provider="google",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.TEXT_TO_IMAGE,
        ],
        max_resolution="2K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.02,
        quality_score=0.85,
        latency_estimate=5.0,
        is_default=False,
        tier="fast",
        arena_rank=8,
        arena_score=1170,
        strengths=["speed", "efficiency"],
    ),
    ProviderModel(
        id="imagen-3.0-capability-001",
        name="Imagen 3 Edit",
        provider="google",
        media_type=MediaType.IMAGE,
        capabilities=[
            ProviderCapability.INPAINTING,
            ProviderCapability.OUTPAINTING,
        ],
        max_resolution="1K",
        supports_aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        pricing_per_unit=0.04,
        quality_score=0.85,
        latency_estimate=12.0,
        is_default=False,
        hidden=True,
        tier="balanced",
        strengths=["inpainting", "outpainting", "editing"],
    ),
]


class GoogleProvider(BaseImageProvider):
    """
    Google Gemini/Imagen image generation provider.

    Supports:
    - Text-to-image generation with multiple resolutions
    - Image blending with up to 14 reference images
    - Search-grounded generation with real-time data
    - Multi-turn chat-based image refinement
    """

    RETRY_CONFIG = RetryConfig(max_retries=1, retry_delays=[2])

    def __init__(self, config: ProviderConfig | None = None):
        """
        Initialize the Google provider.

        Args:
            config: Optional provider configuration with API key
        """
        self._config = config or ProviderConfig()
        self._api_key = (
            self._config.api_key
            or os.getenv("PROVIDER_GOOGLE_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        self._client: genai.Client | None = None
        self._models = GOOGLE_MODELS.copy()
        self._stats: list[dict] = []

        if self._api_key:
            self._client = genai.Client(api_key=self._api_key)

    @property
    def name(self) -> str:
        return "google"

    @property
    def display_name(self) -> str:
        return "Google Gemini"

    @property
    def models(self) -> list[ProviderModel]:
        return self._models

    @property
    def is_available(self) -> bool:
        return self._client is not None and self._api_key is not None

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate the configured API key."""
        if not self._api_key or len(self._api_key) < 10:
            return False, "API key is too short"

        try:
            client = genai.Client(api_key=self._api_key)
            # List models as a lightweight validation
            list(client.models.list())
            return True, "API key is valid"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
                return False, "Invalid API key"
            elif "quota" in error_msg.lower():
                return False, "API key quota exceeded"
            else:
                return False, f"Validation failed: {error_msg[:100]}"

    def update_api_key(self, api_key: str) -> None:
        """Update the API key and reinitialize the client."""
        self._api_key = api_key
        self._client = genai.Client(api_key=api_key)

    def _execute_with_retry(
        self,
        api_call: Callable[[], Any],
        result: GenerationResult,
        start_time: float,
    ) -> tuple[Any, str | None]:
        """Execute a sync API call with retry logic (for Google SDK)."""
        last_error = None
        config = self.RETRY_CONFIG

        for attempt in range(config.max_retries + 1):
            try:
                response = api_call()
                return response, None
            except Exception as e:
                error_msg = str(e)
                last_error = error_msg

                # Check if error is safety related (no retry)
                if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.error_type = "safety_blocked"
                    result.duration = time.time() - start_time
                    return None, error_msg

                # Check if error is retryable
                if is_retryable_error(error_msg) and attempt < config.max_retries:
                    delay = config.retry_delays[attempt]
                    logger.warning(
                        f"[Google] Retryable error on attempt {attempt + 1}: {error_msg}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                    continue

                # Non-retryable error or max retries reached
                break

        return None, last_error

    def _process_response(
        self,
        response: Any,
        result: GenerationResult,
        extract_search: bool = False,
    ) -> bool:
        """Process API response and extract data into result."""
        if not response.candidates:
            return True

        candidate = response.candidates[0]

        # Extract safety ratings
        if hasattr(candidate, "safety_ratings") and candidate.safety_ratings:
            result.safety_ratings = [
                {"category": str(r.category), "probability": str(r.probability)}
                for r in candidate.safety_ratings
            ]

        # Check if blocked by safety filter
        if hasattr(candidate, "finish_reason") and str(candidate.finish_reason) == "SAFETY":
            result.safety_blocked = True
            result.error = "Content blocked by safety filter"
            result.error_type = "safety_blocked"
            return False

        # Process response parts
        if hasattr(candidate, "content") and candidate.content:
            for part in candidate.content.parts:
                if hasattr(part, "thought") and part.thought:
                    result.thinking = part.text
                elif hasattr(part, "text") and part.text:
                    result.text_response = part.text
                elif hasattr(part, "inline_data") and part.inline_data:
                    image_data = part.inline_data.data
                    result.image = Image.open(BytesIO(image_data))

        # Extract search sources if requested
        if (
            extract_search
            and hasattr(candidate, "grounding_metadata")
            and candidate.grounding_metadata
        ):
            metadata = candidate.grounding_metadata
            if hasattr(metadata, "search_entry_point") and metadata.search_entry_point:
                result.search_sources = metadata.search_entry_point.rendered_content

        return True

    @staticmethod
    def _pil_to_genai_image(img: Image.Image) -> types.Image:
        """Convert a PIL Image to a google.genai types.Image."""
        buf = BytesIO()
        img.save(buf, format="PNG")
        return types.Image(image_bytes=buf.getvalue(), mime_type="image/png")

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

        if not self._client:
            result.error = "Google API client not initialized"
            result.error_type = "invalid_key"
            return result

        # Route edit_mode operations to specialised methods
        if request.edit_mode in ("inpaint_insert", "inpaint_remove"):
            edit_model = self.get_model_by_id("imagen-3.0-capability-001")
            if not edit_model:
                result.error = "Imagen edit model not available"
                return result
            result.model = edit_model.id
            return await self._generate_inpaint(request, edit_model, result, start_time)

        if request.edit_mode == "outpaint":
            edit_model = self.get_model_by_id("imagen-3.0-capability-001")
            if not edit_model:
                result.error = "Imagen edit model not available"
                return result
            result.model = edit_model.id
            return await self._generate_outpaint(request, edit_model, result, start_time)

        if request.edit_mode == "describe":
            model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
            if not model:
                result.error = f"Model not found: {model_id}"
                return result
            result.model = model.id
            return await self._describe_image(request, model, result, start_time)

        # Select model
        model = self.get_model_by_id(model_id) if model_id else self.get_default_model()
        if not model:
            result.error = f"Model not found: {model_id}"
            return result

        result.model = model.id

        # Route to appropriate generation method
        if request.reference_images:
            return await self._generate_blend(request, model, result, start_time)
        elif request.enable_search:
            return await self._generate_with_search(request, model, result, start_time)
        else:
            return await self._generate_basic(request, model, result, start_time)

    async def _generate_basic(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Basic text-to-image generation."""
        # Build config
        config_dict = {
            "response_modalities": ["Text", "Image"],
            "image_config": {
                "aspect_ratio": request.aspect_ratio,
            },
            "safety_settings": build_safety_settings(request.safety_level),
        }

        # Add resolution for higher quality
        if request.resolution in ["2K", "4K"]:
            config_dict["image_config"]["image_size"] = request.resolution

        # Add thinking config
        if request.enable_thinking:
            config_dict["thinking_config"] = {"include_thoughts": True}

        config = types.GenerateContentConfig(**config_dict)

        # Define API call
        def api_call():
            return self._client.models.generate_content(
                model=model.id,
                contents=request.prompt,
                config=config,
            )

        # Execute with retry (run sync call in thread pool)
        loop = asyncio.get_event_loop()
        response, last_error = await loop.run_in_executor(
            None, lambda: self._execute_with_retry(api_call, result, start_time)
        )

        if response is None:
            if not result.error:
                result.error = last_error
                result.retryable = is_retryable_error(last_error) if last_error else False
            result.duration = time.time() - start_time
            return result

        # Process response
        if not self._process_response(response, result):
            result.duration = time.time() - start_time
            return result

        result.success = result.image is not None
        result.duration = time.time() - start_time
        result.cost = self._estimate_cost(model, request.resolution)
        self._record_stats(result.duration)
        return result

    async def _generate_blend(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Blend multiple images based on a prompt."""
        if not request.reference_images:
            result.error = "No images provided for blending"
            return result

        # Build contents and config
        contents = [request.prompt] + list(request.reference_images)
        config = types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=request.aspect_ratio),
            safety_settings=build_safety_settings(request.safety_level),
        )

        def api_call():
            return self._client.models.generate_content(
                model=model.id,
                contents=contents,
                config=config,
            )

        loop = asyncio.get_event_loop()
        response, last_error = await loop.run_in_executor(
            None, lambda: self._execute_with_retry(api_call, result, start_time)
        )

        if response is None:
            if not result.error:
                result.error = last_error
                result.retryable = is_retryable_error(last_error) if last_error else False
            result.duration = time.time() - start_time
            return result

        if not self._process_response(response, result):
            result.duration = time.time() - start_time
            return result

        result.success = result.image is not None
        result.duration = time.time() - start_time
        result.cost = self._estimate_cost(model, request.resolution)
        self._record_stats(result.duration)
        return result

    async def _generate_with_search(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Generate an image using real-time search data."""
        config = types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=request.aspect_ratio),
            tools=[{"google_search": {}}],
            safety_settings=build_safety_settings(request.safety_level),
        )

        def api_call():
            return self._client.models.generate_content(
                model=model.id,
                contents=request.prompt,
                config=config,
            )

        loop = asyncio.get_event_loop()
        response, last_error = await loop.run_in_executor(
            None, lambda: self._execute_with_retry(api_call, result, start_time)
        )

        if response is None:
            if not result.error:
                result.error = last_error
                result.retryable = is_retryable_error(last_error) if last_error else False
            result.duration = time.time() - start_time
            return result

        if not self._process_response(response, result, extract_search=True):
            result.duration = time.time() - start_time
            return result

        result.success = result.image is not None
        result.duration = time.time() - start_time
        result.cost = self._estimate_cost(model, request.resolution) * 1.5  # Search costs more
        self._record_stats(result.duration)
        return result

    async def _generate_inpaint(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Inpaint an image using Imagen edit_image API."""
        if not request.reference_images or len(request.reference_images) < 1:
            result.error = "Source image is required for inpainting"
            return result

        source_image = request.reference_images[0]

        # Build raw reference image
        raw_ref = types.RawReferenceImage(
            referenceImage=self._pil_to_genai_image(source_image),
            referenceId=0,
        )

        # Build mask reference image
        mask_ref_kwargs: dict = {
            "referenceId": 1,
        }

        if request.mask_mode == "user_provided" and request.mask_image is not None:
            mask_ref_kwargs["referenceImage"] = self._pil_to_genai_image(request.mask_image)
            mask_ref_kwargs["config"] = types.MaskReferenceConfig(
                maskMode="MASK_MODE_USER_PROVIDED",
                maskDilation=request.mask_dilation,
            )
        elif request.mask_mode == "foreground":
            mask_ref_kwargs["config"] = types.MaskReferenceConfig(
                maskMode="MASK_MODE_FOREGROUND",
                maskDilation=request.mask_dilation,
            )
        elif request.mask_mode == "background":
            mask_ref_kwargs["config"] = types.MaskReferenceConfig(
                maskMode="MASK_MODE_BACKGROUND",
                maskDilation=request.mask_dilation,
            )
        elif request.mask_mode == "semantic":
            mask_ref_kwargs["config"] = types.MaskReferenceConfig(
                maskMode="MASK_MODE_SEMANTIC",
                maskDilation=request.mask_dilation,
            )
        else:
            # Default: user_provided but no mask image → error
            result.error = "Mask image is required for user_provided mask mode"
            return result

        mask_ref = types.MaskReferenceImage(**mask_ref_kwargs)

        # Determine edit mode
        edit_mode = (
            "EDIT_MODE_INPAINT_REMOVAL"
            if request.edit_mode == "inpaint_remove"
            else "EDIT_MODE_INPAINT_INSERTION"
        )

        def api_call():
            return self._client.models.edit_image(
                model=model.id,
                prompt=request.prompt,
                reference_images=[raw_ref, mask_ref],
                config=types.EditImageConfig(
                    editMode=edit_mode,
                    numberOfImages=1,
                ),
            )

        loop = asyncio.get_event_loop()
        response, last_error = await loop.run_in_executor(
            None, lambda: self._execute_with_retry(api_call, result, start_time)
        )

        if response is None:
            if not result.error:
                result.error = last_error
                result.retryable = is_retryable_error(last_error) if last_error else False
            result.duration = time.time() - start_time
            return result

        # Process edit_image response
        try:
            if response.generated_images and len(response.generated_images) > 0:
                image_bytes = response.generated_images[0].image.image_bytes
                result.image = Image.open(BytesIO(image_bytes))
                result.success = True
            else:
                result.error = "No images returned from inpainting"
        except Exception as e:
            result.error = f"Failed to process inpaint response: {e}"

        result.duration = time.time() - start_time
        result.cost = self._estimate_cost(model, request.resolution)
        self._record_stats(result.duration)
        return result

    async def _generate_outpaint(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Outpaint an image using Imagen edit_image API."""
        if not request.reference_images or len(request.reference_images) < 1:
            result.error = "Source image is required for outpainting"
            return result

        if not request.mask_image:
            result.error = "Mask image is required for outpainting"
            return result

        source_image = request.reference_images[0]

        raw_ref = types.RawReferenceImage(
            referenceImage=self._pil_to_genai_image(source_image),
            referenceId=0,
        )

        mask_ref = types.MaskReferenceImage(
            referenceId=1,
            referenceImage=self._pil_to_genai_image(request.mask_image),
            config=types.MaskReferenceConfig(
                maskMode="MASK_MODE_USER_PROVIDED",
                maskDilation=request.mask_dilation,
            ),
        )

        def api_call():
            return self._client.models.edit_image(
                model=model.id,
                prompt=request.prompt,
                reference_images=[raw_ref, mask_ref],
                config=types.EditImageConfig(
                    editMode="EDIT_MODE_OUTPAINT",
                    numberOfImages=1,
                ),
            )

        loop = asyncio.get_event_loop()
        response, last_error = await loop.run_in_executor(
            None, lambda: self._execute_with_retry(api_call, result, start_time)
        )

        if response is None:
            if not result.error:
                result.error = last_error
                result.retryable = is_retryable_error(last_error) if last_error else False
            result.duration = time.time() - start_time
            return result

        # Process edit_image response
        try:
            if response.generated_images and len(response.generated_images) > 0:
                image_bytes = response.generated_images[0].image.image_bytes
                result.image = Image.open(BytesIO(image_bytes))
                result.success = True
            else:
                result.error = "No images returned from outpainting"
        except Exception as e:
            result.error = f"Failed to process outpaint response: {e}"

        result.duration = time.time() - start_time
        result.cost = self._estimate_cost(model, request.resolution)
        self._record_stats(result.duration)
        return result

    async def _describe_image(
        self,
        request: GenerationRequest,
        model: ProviderModel,
        result: GenerationResult,
        start_time: float,
    ) -> GenerationResult:
        """Describe/analyze an image using generate_content (text-only output)."""
        if not request.reference_images or len(request.reference_images) < 1:
            result.error = "Image is required for description"
            return result

        image = request.reference_images[0]

        contents = [request.prompt, image]
        config = types.GenerateContentConfig(
            response_modalities=["Text"],
            safety_settings=build_safety_settings(request.safety_level),
        )

        def api_call():
            return self._client.models.generate_content(
                model=model.id,
                contents=contents,
                config=config,
            )

        loop = asyncio.get_event_loop()
        response, last_error = await loop.run_in_executor(
            None, lambda: self._execute_with_retry(api_call, result, start_time)
        )

        if response is None:
            if not result.error:
                result.error = last_error
                result.retryable = is_retryable_error(last_error) if last_error else False
            result.duration = time.time() - start_time
            return result

        if not self._process_response(response, result):
            result.duration = time.time() - start_time
            return result

        # For describe, success means we got text back
        result.success = result.text_response is not None
        result.duration = time.time() - start_time
        result.cost = self._estimate_cost(model, request.resolution)
        self._record_stats(result.duration)
        return result

    def _estimate_cost(self, model: ProviderModel, resolution: str) -> float:
        """Estimate cost for a generation."""
        base_cost = model.pricing_per_unit
        if resolution == "4K":
            return base_cost * 2
        elif resolution == "2K":
            return base_cost * 1.5
        return base_cost

    async def health_check(self) -> dict:
        """Perform a health check on this provider."""
        if not self._client:
            return {
                "status": "unhealthy",
                "message": "API client not initialized",
            }

        try:
            # Quick validation by listing models
            start = time.time()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: list(self._client.models.list()))
            latency = time.time() - start

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

    def get_stats_summary(self) -> str:
        """Get summary of generation statistics."""
        if not self._stats:
            return "No generations recorded."
        total = sum(s["duration"] for s in self._stats)
        avg = total / len(self._stats)
        return f"Generations: {len(self._stats)} | Total: {total:.2f}s | Avg: {avg:.2f}s"
