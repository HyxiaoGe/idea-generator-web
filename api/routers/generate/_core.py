"""Core generation endpoints: single generate, batch, and task progress."""

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
    BatchGenerateRequest,
    BatchGenerateResponse,
    GeneratedImage,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerateTaskProgress,
    GenerationMode,
    GenerationSettings,
)
from core.auth import AppUser, get_current_user
from core.config import get_settings
from core.exceptions import (
    GenerationError,
    StorageError,
    TaskNotFoundError,
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
        # Manual model -> resolve alias
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

    # -- sync path --
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

    # -- async path (default) --
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
    provider_request,
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
    """Synchronous generation path -- keeps the original blocking behavior."""
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
