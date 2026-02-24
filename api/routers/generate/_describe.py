"""Describe image endpoint."""

import logging

from fastapi import APIRouter, Depends

from api.dependencies import (
    check_quota_and_consume,
    get_quota_repository,
    get_user_id_from_user,
)
from api.schemas.generate import (
    DescribeImageRequest,
    DescribeImageResponse,
    DescribeMode,
    GenerationSettings,
)
from core.auth import AppUser, get_current_user
from core.exceptions import (
    GenerationError,
    ValidationError,
)
from database.repositories import QuotaRepository
from services import (
    MediaType,
    get_friendly_error_message,
    get_provider_router,
)
from services.storage import get_storage_manager

from ._helpers import build_provider_request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/describe", response_model=DescribeImageResponse)
async def describe_image(
    request: DescribeImageRequest,
    user: AppUser | None = Depends(get_current_user),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
):
    """
    Describe/analyze an image and return a text description with optional tags.

    Uses Google Gemini generate_content with text-only output.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # Load image from storage
    storage = get_storage_manager(user_id=user_id if user else None)

    img = await storage.load_image(request.image_key)
    if img is None:
        raise ValidationError(message=f"Image not found: {request.image_key}")

    # Build analysis prompt based on mode, detail_level and language
    lang_instruction = (
        "Respond in Chinese (中文)." if request.language == "zh" else "Respond in English."
    )

    if request.mode == DescribeMode.REVERSE_PROMPT:
        # Reverse prompt mode: generate a reusable image generation prompt
        analysis_prompt = (
            "Analyze this image and generate a detailed image generation prompt that could "
            "recreate a similar image. Include the subject, scene, composition, lighting, "
            "color palette, artistic style, mood, and technical qualities. "
            "Format it as a single prompt string suitable for text-to-image AI models "
            "(e.g. Stable Diffusion, DALL-E, Midjourney). "
            "Use comma-separated descriptive phrases. Include quality modifiers like "
            "resolution, camera settings, and rendering style where appropriate. "
            f"{lang_instruction} "
            "Return ONLY the prompt, no explanations or prefixes."
        )
    elif request.detail_level == "brief":
        analysis_prompt = f"Describe this image in 1-2 sentences. {lang_instruction}"
    elif request.detail_level == "detailed":
        analysis_prompt = (
            f"Provide a comprehensive description of this image including subject, "
            f"composition, colors, mood, style, and notable details. {lang_instruction}"
        )
    else:  # standard
        analysis_prompt = (
            f"Describe this image in a short paragraph covering the main subject "
            f"and key visual elements. {lang_instruction}"
        )

    if request.mode != DescribeMode.REVERSE_PROMPT and request.include_tags:
        analysis_prompt += (
            " Also provide a list of keyword tags at the end in the format: "
            "Tags: tag1, tag2, tag3, ..."
        )

    # Build provider request -- describe uses Google Gemini
    provider_request = build_provider_request(
        prompt=analysis_prompt,
        settings=GenerationSettings(),  # default settings (not used for image output)
        user_id=user_id,
        preferred_provider="google",
        reference_images=[img],
        edit_mode="describe",
    )

    # Execute -- use execute() (no fallback), Google-only
    router_instance = get_provider_router()

    try:
        result = await router_instance.execute(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available for describe: {e}")
        raise GenerationError(message="No providers available for image description")

    if result.error:
        raise GenerationError(message=get_friendly_error_message(result.error))

    if not result.text_response:
        raise GenerationError(message="Failed to describe image")

    # Parse response based on mode
    raw_text = result.text_response
    description = ""
    generated_prompt: str | None = None
    tags: list[str] = []

    if request.mode == DescribeMode.REVERSE_PROMPT:
        generated_prompt = raw_text.strip()
        description = raw_text.strip()
    else:
        description = raw_text
        if request.include_tags and "Tags:" in description:
            parts = description.rsplit("Tags:", 1)
            description = parts[0].strip()
            tag_str = parts[1].strip()
            tags = [t.strip() for t in tag_str.split(",") if t.strip()]

    # Record quota usage
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="describe",
                points_used=1,
                provider=result.provider,
                model=result.model,
                resolution="1K",
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

    return DescribeImageResponse(
        description=description,
        prompt=generated_prompt,
        tags=tags,
        duration=result.duration,
        provider=result.provider,
        model=result.model,
    )
