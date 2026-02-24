"""Search-grounded generation endpoint."""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query

from api.dependencies import (
    check_quota_and_consume,
    get_image_repository,
    get_quota_repository,
    get_template_repository,
    get_user_id_from_user,
)
from api.schemas.generate import (
    AsyncGenerateResponse,
    GeneratedImage,
    GenerateImageResponse,
    GenerationMode,
    SearchGenerateRequest,
)
from core.auth import AppUser, get_current_user
from core.config import get_settings
from core.exceptions import (
    GenerationError,
    StorageError,
)
from core.redis import get_redis
from database.repositories import ImageRepository, QuotaRepository, TemplateRepository
from services import (
    MediaType,
    get_friendly_error_message,
    get_provider_router,
)
from services.prompt_pipeline import get_prompt_pipeline
from services.storage import get_storage_manager

from ._helpers import build_provider_request, create_generator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search")
async def search_grounded_generate(
    request: SearchGenerateRequest,
    background_tasks: BackgroundTasks,
    sync: bool = Query(False, description="If true, run synchronously and return full result"),
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_provider: str | None = Header(None, alias="X-Provider"),
    x_model: str | None = Header(None, alias="X-Model"),
) -> GenerateImageResponse | AsyncGenerateResponse:
    """
    Generate an image with search grounding.

    By default runs asynchronously (returns task_id for polling).
    Pass ?sync=true for synchronous mode (blocks until complete).

    Uses real-time search data to inform generation.
    Note: Search grounding is currently only supported by Google Gemini.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # Run prompt pipeline
    app_settings = get_settings()
    if app_settings.is_prompt_pipeline_configured:
        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(
            prompt=request.prompt,
            enhance=request.enhance_prompt
            if request.enhance_prompt is not None
            else app_settings.prompt_auto_enhance,
            generate_negative=request.generate_negative
            if request.generate_negative is not None
            else app_settings.prompt_auto_negative,
            template_id=request.template_id,
            template_repo=template_repo,
        )
        final_prompt = processed.final
        negative_prompt = processed.negative_prompt
    else:
        final_prompt = request.prompt
        negative_prompt = None
        processed = None

    # Model resolution: alias or quality preset
    from services.model_router import QualityPreset, resolve_alias, select_model_by_preset

    search_effective_provider = x_provider or "google"  # Search only works with Google
    search_effective_model = x_model
    search_preset_used = None

    if x_model:
        resolved_provider, resolved_model = resolve_alias(x_model)
        search_effective_model = resolved_model
        if resolved_provider and not x_provider:
            search_effective_provider = resolved_provider
        search_preset_used = "manual"
    else:
        preset_str = request.quality_preset or "balanced"
        try:
            preset = QualityPreset(preset_str)
        except ValueError:
            preset = QualityPreset.BALANCED
        p_provider, p_model = select_model_by_preset(preset, search_effective_provider)
        if p_model:
            search_effective_provider = p_provider or search_effective_provider
            search_effective_model = p_model
        search_preset_used = preset_str

    # -- sync path --
    if sync:
        return await _search_sync(
            request=request,
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            processed=processed,
            effective_provider=search_effective_provider,
            effective_model=search_effective_model,
            preset_used=search_preset_used,
            user_id=user_id,
            user=user,
            image_repo=image_repo,
            quota_repo=quota_repo,
            x_api_key=x_api_key,
        )

    # -- async path (default) --
    task_id = f"gen_{uuid.uuid4().hex[:12]}"
    settings_dict = {
        "aspect_ratio": request.settings.aspect_ratio.value,
        "resolution": request.settings.resolution.value,
        "safety_level": request.settings.safety_level.value,
    }

    redis = await get_redis()
    task_key = f"task:{task_id}"
    await redis.hset(
        task_key,
        mapping={
            "status": "queued",
            "stage": "queued",
            "progress": "0",
            "user_id": user_id,
            "prompt": request.prompt,
            "processed_prompt": final_prompt if processed else "",
            "negative_prompt": negative_prompt or "",
            "request_json": json.dumps(settings_dict),
            "created_at": datetime.now().isoformat(),
        },
    )
    await redis.expire(task_key, 86400)

    from services.image_task import execute_image_task

    background_tasks.add_task(
        execute_image_task,
        task_id=task_id,
        mode="search",
        user_id=user_id,
        prompt=final_prompt,
        settings_dict=settings_dict,
        task_spec={
            "preferred_provider": search_effective_provider,
            "preferred_model": search_effective_model,
            "negative_prompt": negative_prompt,
            "quality_preset": search_preset_used,
            "processed_prompt": processed.final if processed else None,
            "template_used": processed.template_used if processed else False,
            "was_translated": processed.was_translated if processed else False,
            "was_enhanced": processed.was_enhanced if processed else False,
            "template_name": processed.template_name if processed else None,
        },
    )

    return AsyncGenerateResponse(
        task_id=task_id,
        status="queued",
        message="Search generation task queued",
    )


async def _search_sync(
    request: SearchGenerateRequest,
    final_prompt: str,
    negative_prompt: str | None,
    processed,
    effective_provider: str,
    effective_model: str | None,
    preset_used: str | None,
    user_id: str,
    user: AppUser | None,
    image_repo: ImageRepository | None,
    quota_repo: QuotaRepository | None,
    x_api_key: str | None,
) -> GenerateImageResponse:
    """Synchronous search generation -- keeps the original blocking behavior."""
    # Build provider request with search enabled
    provider_request = build_provider_request(
        prompt=final_prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider=effective_provider,
        preferred_model=effective_model,
        enable_search=True,
        negative_prompt=negative_prompt,
    )

    # Use multi-provider router
    router_instance = get_provider_router()

    try:
        result = await router_instance.execute_with_fallback(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available for search, falling back to legacy: {e}")
        generator = create_generator(x_api_key)
        legacy_result = generator.generate(
            prompt=request.prompt,
            aspect_ratio=request.settings.aspect_ratio.value,
            resolution=request.settings.resolution.value,
            enable_search=True,
            safety_level=request.settings.safety_level.value,
        )
        result = type(
            "Result",
            (),
            {
                "success": legacy_result.image is not None,
                "image": legacy_result.image,
                "error": legacy_result.error,
                "text_response": legacy_result.text,
                "search_sources": legacy_result.search_sources,
                "duration": legacy_result.duration,
                "provider": "google",
                "model": "gemini-3-pro-image-preview",
            },
        )()

    if result.error:
        raise GenerationError(message=get_friendly_error_message(result.error))

    if not result.image:
        raise GenerationError(message="Failed to generate image")

    # Save to storage
    storage = get_storage_manager(user_id=user_id if user else None)

    try:
        storage_obj = await storage.save_image(
            image=result.image,
            prompt=request.prompt,
            settings={
                "aspect_ratio": request.settings.aspect_ratio.value,
                "resolution": request.settings.resolution.value,
                "provider": result.provider,
                "model": result.model,
            },
            duration=result.duration,
            mode="search",
            text_response=result.text_response,
        )
    except Exception as e:
        logger.error(f"Failed to save image: {e}")
        raise StorageError(message="Failed to save image")

    # Save to PostgreSQL if available
    if image_repo:
        try:
            await image_repo.create(
                storage_key=storage_obj.key,
                filename=storage_obj.filename,
                prompt=request.prompt,
                mode="search",
                storage_backend=get_settings().storage_backend,
                public_url=storage_obj.public_url,
                aspect_ratio=request.settings.aspect_ratio.value,
                resolution=request.settings.resolution.value,
                provider=result.provider,
                model=result.model,
                width=result.image.width,
                height=result.image.height,
                generation_duration_ms=int(result.duration * 1000) if result.duration else None,
                text_response=result.text_response,
                user_id=None,
            )
        except Exception as e:
            logger.warning(f"Failed to save image to database: {e}")

    # Record quota usage to PostgreSQL if available
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="search",
                points_used=1,
                provider=result.provider,
                model=result.model,
                resolution=request.settings.resolution.value,
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

    # Resolve model display name
    search_model_display_name = None
    if result.model:
        from services.providers.registry import get_provider_registry

        registry = get_provider_registry()
        for p in registry.get_available_image_providers():
            m = p.get_model_by_id(result.model)
            if m:
                search_model_display_name = m.name
                break

    return GenerateImageResponse(
        image=GeneratedImage(
            key=storage_obj.key,
            filename=storage_obj.filename,
            url=storage_obj.public_url,
            width=result.image.width,
            height=result.image.height,
        ),
        prompt=request.prompt,
        text_response=result.text_response,
        search_sources=getattr(result, "search_sources", None),
        duration=result.duration,
        mode=GenerationMode.SEARCH,
        settings=request.settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
        model_display_name=search_model_display_name,
        quality_preset=preset_used,
        processed_prompt=processed.final if processed else None,
        negative_prompt=negative_prompt,
        template_used=processed.template_used if processed else False,
        was_translated=processed.was_translated if processed else False,
        was_enhanced=processed.was_enhanced if processed else False,
        template_name=processed.template_name if processed else None,
    )
