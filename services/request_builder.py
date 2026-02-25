"""Shared request builder for constructing GenerationRequest instances.

Used by both the API layer (routers) and service layer (background tasks)
to avoid duplicating request construction logic.
"""

import uuid

from .providers.base import GenerationRequest, ProviderCapability


def build_provider_request(
    prompt: str,
    settings,
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
    required_capability: ProviderCapability | None = None,
) -> GenerationRequest:
    """Build a unified provider request from API parameters.

    Args:
        settings: Object with aspect_ratio, resolution, safety_level attributes
                  (each having a .value property, e.g. Pydantic enums).
    """
    return GenerationRequest(
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
        required_capability=required_capability,
        user_id=user_id,
        request_id=f"gen_{uuid.uuid4().hex[:12]}",
    )
