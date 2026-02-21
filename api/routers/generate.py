"""
Image generation router.

Endpoints:
- POST /api/generate - Generate a single image
- POST /api/generate/batch - Queue batch generation
- GET /api/generate/task/{task_id} - Get task progress
- POST /api/generate/blend - Blend multiple images
- POST /api/generate/style - Style transfer
- POST /api/generate/search - Search-grounded generation
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query

from api.dependencies import get_image_repository, get_quota_repository, get_template_repository
from api.schemas.generate import (
    AsyncGenerateResponse,
    BatchGenerateRequest,
    BatchGenerateResponse,
    BlendImagesRequest,
    DescribeImageRequest,
    DescribeImageResponse,
    GeneratedImage,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerateTaskProgress,
    GenerationMode,
    GenerationSettings,
    InpaintRequest,
    OutpaintRequest,
    SearchGenerateRequest,
)
from core.auth import AppUser, get_current_user
from core.config import get_settings
from core.exceptions import (
    GenerationError,
    QuotaExceededError,
    StorageError,
    TaskNotFoundError,
    ValidationError,
)
from core.redis import get_redis
from database.repositories import ImageRepository, QuotaRepository, TemplateRepository
from services import (
    # Multi-provider support
    GenerationRequest as ProviderRequest,
)
from services import (
    # Legacy (still used for backward compatibility)
    ImageGenerator,
    MediaType,
    get_friendly_error_message,
    get_provider_router,
    get_quota_service,
)
from services.prompt_pipeline import get_prompt_pipeline
from services.storage import get_storage_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])


# ============ Helpers ============


def get_user_id_from_user(user: AppUser | None) -> str:
    """Get user ID for quota tracking."""
    if user:
        return user.user_folder_id
    return "anonymous"


async def check_quota_and_consume(user_id: str, count: int = 1) -> None:
    """
    Check daily quota and consume if available.

    Raises:
        QuotaExceededError: If quota exceeded or cooldown active
    """
    redis = await get_redis()
    quota_service = get_quota_service(redis)

    can_generate, reason, info = await quota_service.check_quota(
        user_id=user_id,
        count=count,
    )

    if not can_generate:
        raise QuotaExceededError(message=reason, details=info)

    await quota_service.consume_quota(user_id=user_id, count=count)


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


# ============ Endpoints ============


@router.post("")
async def generate_image(
    request: GenerateImageRequest,
    background_tasks: BackgroundTasks,
    sync: bool = Query(False, description="If true, run synchronously and return full result"),
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_provider: str | None = Header(None, alias="X-Provider"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_routing_strategy: str | None = Header(None, alias="X-Routing-Strategy"),  # noqa: ARG001
) -> GenerateImageResponse | AsyncGenerateResponse:
    """
    Generate a single image from a text prompt.

    By default runs asynchronously (returns task_id for polling).
    Pass ?sync=true for synchronous mode (blocks until complete).

    Supports multi-provider routing via headers:
    - X-Provider: Specify provider (google, openai, bfl, stability)
    - X-Model: Specify model ID
    - X-Routing-Strategy: Override routing (priority, cost, quality, speed)
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

    effective_provider = x_provider
    effective_model = x_model
    preset_used = None

    if x_model:
        # Manual model → resolve alias
        resolved_provider, resolved_model = resolve_alias(x_model)
        effective_model = resolved_model
        if resolved_provider and not x_provider:
            effective_provider = resolved_provider
        preset_used = "manual"
    else:
        # Quality preset routing (default: balanced)
        preset_str = request.quality_preset or "balanced"
        try:
            preset = QualityPreset(preset_str)
        except ValueError:
            preset = QualityPreset.BALANCED
        p_provider, p_model = select_model_by_preset(preset, x_provider)
        if p_model:
            effective_provider = p_provider or x_provider
            effective_model = p_model
        preset_used = preset_str

    # Build provider request
    provider_request = build_provider_request(
        prompt=final_prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider=effective_provider,
        preferred_model=effective_model,
        enable_thinking=request.include_thinking,
        negative_prompt=negative_prompt,
    )

    # Route to determine primary provider and fallbacks
    router_instance = get_provider_router()

    try:
        decision = await router_instance.route(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available: {e}")
        raise GenerationError(message="No providers available")

    # ── sync path ──────────────────────────────────────────────────
    if sync:
        return await _generate_sync(
            request=request,
            provider_request=provider_request,
            decision=decision,
            router_instance=router_instance,
            user_id=user_id,
            user=user,
            preset_used=preset_used,
            processed=processed,
            negative_prompt=negative_prompt,
            image_repo=image_repo,
            quota_repo=quota_repo,
            x_api_key=x_api_key,
        )

    # ── async path (default) ──────────────────────────────────────
    task_id = f"gen_{uuid.uuid4().hex[:12]}"

    redis = await get_redis()
    task_key = f"task:{task_id}"
    settings_dict = {
        "aspect_ratio": request.settings.aspect_ratio.value,
        "resolution": request.settings.resolution.value,
        "safety_level": request.settings.safety_level.value,
    }
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
    await redis.expire(task_key, 86400)  # 24h TTL

    from services.generation_task import execute_generation_race

    background_tasks.add_task(
        execute_generation_race,
        task_id=task_id,
        request=provider_request,
        original_prompt=request.prompt,
        processed_prompt=processed.final if processed else None,
        negative_prompt=negative_prompt,
        settings_dict=settings_dict,
        user_id=user_id,
        primary_provider=decision.provider_name,
        primary_model=decision.model_id,
        fallback_names=decision.fallback_providers or [],
        preset_used=preset_used,
        template_used=processed.template_used if processed else False,
        was_translated=processed.was_translated if processed else False,
        was_enhanced=processed.was_enhanced if processed else False,
        template_name=processed.template_name if processed else None,
    )

    return AsyncGenerateResponse(
        task_id=task_id,
        status="queued",
        message="Generation task queued",
    )


async def _generate_sync(
    request: GenerateImageRequest,
    provider_request: ProviderRequest,
    decision,
    router_instance,
    user_id: str,
    user: AppUser | None,
    preset_used: str | None,
    processed,
    negative_prompt: str | None,
    image_repo: ImageRepository | None,
    quota_repo: QuotaRepository | None,
    x_api_key: str | None,
) -> GenerateImageResponse:
    """Synchronous generation path — keeps the original blocking behavior."""
    try:
        result = await router_instance.execute_with_fallback(
            request=provider_request,
            decision=decision,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available, falling back to legacy: {e}")
        generator = create_generator(x_api_key)
        legacy_result = generator.generate(
            prompt=request.prompt,
            aspect_ratio=request.settings.aspect_ratio.value,
            resolution=request.settings.resolution.value,
            enable_thinking=request.include_thinking,
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
                "thinking": legacy_result.thinking,
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
            mode="basic",
            text_response=result.text_response,
            thinking=result.thinking,
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
                mode="basic",
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
                thinking=result.thinking,
                user_id=None,
            )
        except Exception as e:
            logger.warning(f"Failed to save image to database: {e}")

    # Record quota usage to PostgreSQL if available
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="basic",
                points_used=1,
                provider=result.provider,
                model=result.model,
                resolution=request.settings.resolution.value,
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

    # Resolve model display name
    model_display_name = None
    if result.model:
        from services.providers.registry import get_provider_registry

        registry = get_provider_registry()
        for p in registry.get_available_image_providers():
            m = p.get_model_by_id(result.model)
            if m:
                model_display_name = m.name
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
        thinking=result.thinking,
        text_response=result.text_response,
        duration=result.duration,
        mode=GenerationMode.BASIC,
        settings=request.settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
        model_display_name=model_display_name,
        quality_preset=preset_used,
        processed_prompt=processed.final if processed else None,
        negative_prompt=negative_prompt,
        template_used=processed.template_used if processed else False,
        was_translated=processed.was_translated if processed else False,
        was_enhanced=processed.was_enhanced if processed else False,
        template_name=processed.template_name if processed else None,
    )


@router.post("/batch", response_model=BatchGenerateResponse)
async def batch_generate(
    request: BatchGenerateRequest,
    background_tasks: BackgroundTasks,
    user: AppUser | None = Depends(get_current_user),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """
    Queue a batch image generation task.

    Returns a task ID for tracking progress via WebSocket or polling.
    """
    user_id = get_user_id_from_user(user)
    count = len(request.prompts)

    # Check quota for entire batch
    await check_quota_and_consume(user_id, count=count)

    # Create task ID
    task_id = f"batch_{uuid.uuid4().hex[:16]}"

    # Store initial task state in Redis
    redis = await get_redis()
    task_data = {
        "status": "queued",
        "progress": 0,
        "total": count,
        "prompts": request.prompts,
        "settings": request.settings.model_dump(),
        "user_id": user_id,
        "api_key": x_api_key or "",
        "created_at": datetime.now().isoformat(),
    }

    await redis.hset(
        f"task:{task_id}",
        mapping={
            k: str(v) if not isinstance(v, list | dict) else __import__("json").dumps(v)
            for k, v in task_data.items()
        },
    )
    await redis.expire(f"task:{task_id}", 86400)  # 24 hour TTL

    # Queue task via arq (or run in background for simple cases)
    # For now, we'll use FastAPI background tasks
    # TODO: Replace with arq for production
    background_tasks.add_task(
        process_batch_generation,
        task_id=task_id,
        prompts=request.prompts,
        settings=request.settings,
        user_id=user_id,
        api_key=x_api_key,
    )

    return BatchGenerateResponse(
        task_id=task_id,
        total=count,
        status="queued",
    )


async def process_batch_generation(
    task_id: str,
    prompts: list,
    settings: GenerationSettings,
    user_id: str,
    api_key: str | None,
):
    """Background task to process batch generation."""
    import json

    redis = await get_redis()
    task_key = f"task:{task_id}"

    await redis.hset(task_key, "status", "processing")
    await redis.hset(task_key, "started_at", datetime.now().isoformat())

    generator = create_generator(api_key)
    storage = get_storage_manager(user_id=user_id if user_id != "anonymous" else None)

    results = []
    errors = []

    # Run pipeline on each prompt if configured
    app_settings = get_settings()
    pipeline_configured = app_settings.is_prompt_pipeline_configured

    for i, prompt in enumerate(prompts):
        # Check if task was cancelled
        cancelled = await redis.hget(task_key, "cancelled")
        if cancelled == "1":
            await redis.hset(task_key, "status", "cancelled")
            await redis.hset(task_key, "completed_at", datetime.now().isoformat())
            await redis.hdel(task_key, "current_prompt")
            return

        try:
            # Update current prompt
            await redis.hset(task_key, "current_prompt", prompt)

            # Apply prompt pipeline
            final_prompt = prompt
            if pipeline_configured:
                try:
                    pipeline = get_prompt_pipeline()
                    processed = await pipeline.process(
                        prompt=prompt,
                        enhance=app_settings.prompt_auto_enhance,
                        generate_negative=False,
                    )
                    final_prompt = processed.final
                except Exception as e:
                    logger.warning(f"Batch pipeline failed for prompt {i + 1}: {e}")

            result = generator.generate(
                prompt=final_prompt,
                aspect_ratio=settings.aspect_ratio.value,
                resolution=settings.resolution.value,
                safety_level=settings.safety_level.value,
            )

            if result.error:
                errors.append(f"Prompt {i + 1}: {result.error}")
            elif result.image:
                storage_obj = await storage.save_image(
                    image=result.image,
                    prompt=prompt,
                    settings={
                        "aspect_ratio": settings.aspect_ratio.value,
                        "resolution": settings.resolution.value,
                    },
                    duration=result.duration,
                    mode="batch",
                )

                results.append(
                    {
                        "key": storage_obj.key,
                        "filename": storage_obj.filename,
                        "url": storage_obj.public_url,
                    }
                )

        except Exception as e:
            errors.append(f"Prompt {i + 1}: {str(e)}")
            logger.error(f"Batch generation error: {e}")

        # Update progress
        await redis.hset(task_key, "progress", str(i + 1))
        await redis.hset(task_key, "results", json.dumps(results))
        await redis.hset(task_key, "errors", json.dumps(errors))

    # Mark complete
    await redis.hset(task_key, "status", "completed")
    await redis.hset(task_key, "completed_at", datetime.now().isoformat())
    await redis.hdel(task_key, "current_prompt")


@router.get("/task/{task_id}", response_model=GenerateTaskProgress)
async def get_task_progress(task_id: str):
    """Get progress of a generation task (single or batch)."""
    redis = await get_redis()
    task_key = f"task:{task_id}"

    task_data = await redis.hgetall(task_key)
    if not task_data:
        raise TaskNotFoundError()

    if task_id.startswith("gen_"):
        return _build_single_progress(task_id, task_data)
    else:
        return _build_batch_progress(task_id, task_data)


def _build_single_progress(task_id: str, task_data: dict) -> GenerateTaskProgress:
    """Build unified progress response for a single-image task."""
    result = None
    result_json = task_data.get("result_json")
    if result_json:
        result = GenerateImageResponse(**json.loads(result_json))

    return GenerateTaskProgress(
        task_id=task_id,
        task_type="single",
        status=task_data.get("status", "unknown"),
        progress=float(task_data.get("progress", 0)),
        stage=task_data.get("stage"),
        provider=task_data.get("provider"),
        result=result,
        error=task_data.get("error"),
        error_code=task_data.get("error_code") or None,
        started_at=datetime.fromisoformat(task_data["started_at"])
        if "started_at" in task_data
        else None,
        completed_at=datetime.fromisoformat(task_data["completed_at"])
        if "completed_at" in task_data
        else None,
    )


def _build_batch_progress(task_id: str, task_data: dict) -> GenerateTaskProgress:
    """Build unified progress response for a batch task."""
    results = json.loads(task_data.get("results", "[]"))
    errors = json.loads(task_data.get("errors", "[]"))
    total = int(task_data.get("total", 0))
    progress = int(task_data.get("progress", 0))

    return GenerateTaskProgress(
        task_id=task_id,
        task_type="batch",
        status=task_data.get("status", "unknown"),
        progress=float(progress),
        total=total,
        current_prompt=task_data.get("current_prompt"),
        results=[GeneratedImage(**r) for r in results],
        errors=errors,
        started_at=datetime.fromisoformat(task_data["started_at"])
        if "started_at" in task_data
        else None,
        completed_at=datetime.fromisoformat(task_data["completed_at"])
        if "completed_at" in task_data
        else None,
    )


@router.post("/search", response_model=GenerateImageResponse)
async def search_grounded_generate(
    request: SearchGenerateRequest,
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_provider: str | None = Header(None, alias="X-Provider"),
    x_model: str | None = Header(None, alias="X-Model"),
):
    """
    Generate an image with search grounding.

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

    # Build provider request with search enabled
    provider_request = build_provider_request(
        prompt=final_prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider=search_effective_provider,
        preferred_model=search_effective_model,
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
                user_id=None,  # TODO: Get user UUID from authenticated user
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
        quality_preset=search_preset_used,
        # Prompt pipeline
        processed_prompt=processed.final if processed else None,
        negative_prompt=negative_prompt,
        template_used=processed.template_used if processed else False,
        was_translated=processed.was_translated if processed else False,
        was_enhanced=processed.was_enhanced if processed else False,
        template_name=processed.template_name if processed else None,
    )


@router.post("/blend", response_model=GenerateImageResponse)
async def blend_images(
    request: BlendImagesRequest,
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
):
    """
    Blend 2-4 existing images together with an optional prompt.

    Takes image storage keys, loads them, and uses Google Gemini to blend them.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # Load images from storage
    storage = get_storage_manager(user_id=user_id if user else None)
    loaded_images = []

    for key in request.image_keys:
        img = await storage.load_image(key)
        if img is None:
            raise ValidationError(message=f"Image not found: {key}")
        loaded_images.append(img)

    # Build prompt
    prompt = request.blend_prompt or "Blend these images together creatively"

    # Build provider request — blend only supported by Google
    provider_request = build_provider_request(
        prompt=prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider="google",
        reference_images=loaded_images,
    )

    # Execute — use execute() (no fallback, no timeout) because only
    # Google supports blend with reference_images and it needs more time
    router_instance = get_provider_router()

    try:
        result = await router_instance.execute(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available for blend: {e}")
        raise GenerationError(message="No providers available for image blending")

    if result.error:
        raise GenerationError(message=get_friendly_error_message(result.error))

    if not result.image:
        raise GenerationError(message="Failed to blend images")

    # Save to storage
    try:
        storage_obj = await storage.save_image(
            image=result.image,
            prompt=prompt,
            settings={
                "aspect_ratio": request.settings.aspect_ratio.value,
                "resolution": request.settings.resolution.value,
                "provider": result.provider,
                "model": result.model,
            },
            duration=result.duration,
            mode="blend",
            text_response=result.text_response,
        )
    except Exception as e:
        logger.error(f"Failed to save blended image: {e}")
        raise StorageError(message="Failed to save blended image")

    # Save to PostgreSQL if available
    if image_repo:
        try:
            await image_repo.create(
                storage_key=storage_obj.key,
                filename=storage_obj.filename,
                prompt=prompt,
                mode="blend",
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
            logger.warning(f"Failed to save blended image to database: {e}")

    # Record quota usage
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="blend",
                points_used=1,
                provider=result.provider,
                model=result.model,
                resolution=request.settings.resolution.value,
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

    # Resolve model display name
    blend_model_display_name = None
    if result.model:
        from services.providers.registry import get_provider_registry

        registry = get_provider_registry()
        for p in registry.get_available_image_providers():
            m = p.get_model_by_id(result.model)
            if m:
                blend_model_display_name = m.name
                break

    return GenerateImageResponse(
        image=GeneratedImage(
            key=storage_obj.key,
            filename=storage_obj.filename,
            url=storage_obj.public_url,
            width=result.image.width,
            height=result.image.height,
        ),
        prompt=prompt,
        text_response=result.text_response,
        duration=result.duration,
        mode=GenerationMode.BLEND,
        settings=request.settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
        model_display_name=blend_model_display_name,
    )


@router.post("/inpaint", response_model=GenerateImageResponse)
async def inpaint_image(
    request: InpaintRequest,
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
):
    """
    Inpaint an image — insert or remove content in masked areas.

    Requires a source image key. Mask is required for user_provided mode,
    or auto-detected for foreground/background/semantic modes.
    Uses Google Imagen edit_image API.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # Load source image from storage
    storage = get_storage_manager(user_id=user_id if user else None)

    source_img = await storage.load_image(request.image_key)
    if source_img is None:
        raise ValidationError(message=f"Image not found: {request.image_key}")

    # Load mask image if provided
    mask_img = None
    if request.mask_key:
        mask_img = await storage.load_image(request.mask_key)
        if mask_img is None:
            raise ValidationError(message=f"Mask image not found: {request.mask_key}")
    elif request.mask_mode.value == "user_provided":
        raise ValidationError(message="mask_key is required when mask_mode is user_provided")

    # Determine edit mode
    edit_mode = "inpaint_remove" if request.remove_mode else "inpaint_insert"

    # Build provider request — inpaint only supported by Google
    provider_request = build_provider_request(
        prompt=request.prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider="google",
        negative_prompt=request.negative_prompt,
        reference_images=[source_img],
        mask_image=mask_img,
        edit_mode=edit_mode,
        mask_mode=request.mask_mode.value,
        mask_dilation=request.mask_dilation,
    )

    # Execute — use execute() (no fallback), Google-only
    router_instance = get_provider_router()

    try:
        result = await router_instance.execute(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available for inpaint: {e}")
        raise GenerationError(message="No providers available for inpainting")

    if result.error:
        raise GenerationError(message=get_friendly_error_message(result.error))

    if not result.image:
        raise GenerationError(message="Failed to inpaint image")

    # Save to storage
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
            mode="inpaint",
            text_response=result.text_response,
        )
    except Exception as e:
        logger.error(f"Failed to save inpainted image: {e}")
        raise StorageError(message="Failed to save inpainted image")

    # Save to PostgreSQL if available
    if image_repo:
        try:
            await image_repo.create(
                storage_key=storage_obj.key,
                filename=storage_obj.filename,
                prompt=request.prompt,
                mode="inpaint",
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
            logger.warning(f"Failed to save inpainted image to database: {e}")

    # Record quota usage
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="inpaint",
                points_used=1,
                provider=result.provider,
                model=result.model,
                resolution=request.settings.resolution.value,
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

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
        duration=result.duration,
        mode=GenerationMode.INPAINT,
        settings=request.settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
    )


@router.post("/outpaint", response_model=GenerateImageResponse)
async def outpaint_image(
    request: OutpaintRequest,
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
):
    """
    Outpaint an image — extend content beyond the original borders.

    Requires both a source image and a mask image that defines the outpaint area.
    Uses Google Imagen edit_image API.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # Load source and mask images from storage
    storage = get_storage_manager(user_id=user_id if user else None)

    source_img = await storage.load_image(request.image_key)
    if source_img is None:
        raise ValidationError(message=f"Image not found: {request.image_key}")

    mask_img = await storage.load_image(request.mask_key)
    if mask_img is None:
        raise ValidationError(message=f"Mask image not found: {request.mask_key}")

    # Build provider request — outpaint only supported by Google
    provider_request = build_provider_request(
        prompt=request.prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider="google",
        negative_prompt=request.negative_prompt,
        reference_images=[source_img],
        mask_image=mask_img,
        edit_mode="outpaint",
    )

    # Execute — use execute() (no fallback), Google-only
    router_instance = get_provider_router()

    try:
        result = await router_instance.execute(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        logger.warning(f"No providers available for outpaint: {e}")
        raise GenerationError(message="No providers available for outpainting")

    if result.error:
        raise GenerationError(message=get_friendly_error_message(result.error))

    if not result.image:
        raise GenerationError(message="Failed to outpaint image")

    # Save to storage
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
            mode="outpaint",
            text_response=result.text_response,
        )
    except Exception as e:
        logger.error(f"Failed to save outpainted image: {e}")
        raise StorageError(message="Failed to save outpainted image")

    # Save to PostgreSQL if available
    if image_repo:
        try:
            await image_repo.create(
                storage_key=storage_obj.key,
                filename=storage_obj.filename,
                prompt=request.prompt,
                mode="outpaint",
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
            logger.warning(f"Failed to save outpainted image to database: {e}")

    # Record quota usage
    if quota_repo:
        try:
            await quota_repo.record_usage(
                mode="outpaint",
                points_used=1,
                provider=result.provider,
                model=result.model,
                resolution=request.settings.resolution.value,
                media_type="image",
            )
        except Exception as e:
            logger.warning(f"Failed to record quota usage to database: {e}")

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
        duration=result.duration,
        mode=GenerationMode.OUTPAINT,
        settings=request.settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
    )


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

    # Build analysis prompt based on detail_level and language
    lang_instruction = (
        "Respond in Chinese (中文)." if request.language == "zh" else "Respond in English."
    )

    if request.detail_level == "brief":
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

    if request.include_tags:
        analysis_prompt += (
            " Also provide a list of keyword tags at the end in the format: "
            "Tags: tag1, tag2, tag3, ..."
        )

    # Build provider request — describe uses Google Gemini
    provider_request = build_provider_request(
        prompt=analysis_prompt,
        settings=GenerationSettings(),  # default settings (not used for image output)
        user_id=user_id,
        preferred_provider="google",
        reference_images=[img],
        edit_mode="describe",
    )

    # Execute — use execute() (no fallback), Google-only
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

    # Parse tags from response text
    description = result.text_response
    tags: list[str] = []

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
        tags=tags,
        duration=result.duration,
        provider=result.provider,
        model=result.model,
    )


# ============ Provider Management Endpoints ============


@router.get("/providers")
async def list_providers():
    """
    List all available image generation providers and their models.

    Returns provider info including:
    - Provider name and display name
    - Available models with capabilities
    - Pricing and quality scores
    """
    router_instance = get_provider_router()
    providers = router_instance.list_available_providers(media_type=MediaType.IMAGE)

    return {
        "providers": providers,
        "default_provider": get_settings().default_image_provider,
        "routing_strategy": get_settings().default_routing_strategy,
    }


@router.get("/providers/{provider_name}/health")
async def check_provider_health(provider_name: str):
    """
    Check health status of a specific provider.

    Returns:
    - is_healthy: bool
    - latency_ms: int
    - last_check: timestamp
    """
    router_instance = get_provider_router()
    health = await router_instance.check_provider_health(provider_name)

    return {
        "provider": provider_name,
        "is_healthy": health.is_healthy,
        "latency_ms": health.latency_ms,
        "error_count": health.error_count,
        "success_count": health.success_count,
    }
