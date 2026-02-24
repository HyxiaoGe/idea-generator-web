"""Shared helpers for the generate router package."""

import uuid

from api.schemas.generate import GenerationSettings
from core.config import get_settings
from core.exceptions import ValidationError
from services import (
    GenerationRequest as ProviderRequest,
)
from services import (
    ImageGenerator,
)


def create_generator(api_key: str | None = None) -> ImageGenerator:
    """Create image generator with appropriate API key (legacy, for backward compatibility)."""
    settings = get_settings()
    key = api_key or settings.get_google_api_key()

    if not key:
        raise ValidationError(message="No API key configured")

    return ImageGenerator(api_key=key)


def build_provider_request(
    prompt: str,
    settings: GenerationSettings,
    user_id: str | None = None,
    preferred_provider: str | None = None,
    preferred_model: str | None = None,
    enable_thinking: bool = False,
    enable_search: bool = False,
    reference_images: list | None = None,
    negative_prompt: str | None = None,
    mask_image=None,
    edit_mode: str | None = None,
    mask_mode: str | None = None,
    mask_dilation: float = 0.03,
) -> ProviderRequest:
    """Build a unified provider request from API parameters."""
    return ProviderRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        aspect_ratio=settings.aspect_ratio.value,
        resolution=settings.resolution.value,
        safety_level=settings.safety_level.value,
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
        enable_thinking=enable_thinking,
        enable_search=enable_search,
        reference_images=reference_images,
        mask_image=mask_image,
        edit_mode=edit_mode,
        mask_mode=mask_mode,
        mask_dilation=mask_dilation,
        user_id=user_id,
        request_id=f"gen_{uuid.uuid4().hex[:12]}",
    )
