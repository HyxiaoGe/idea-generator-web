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

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from api.dependencies import get_image_repository, get_quota_repository, get_template_repository
from api.routers.auth import get_current_user
from api.schemas.generate import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    GeneratedImage,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerationMode,
    GenerationSettings,
    SearchGenerateRequest,
    TaskProgress,
)
from core.config import get_settings
from core.exceptions import QuotaExceededError
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
from services.auth_service import GitHubUser
from services.prompt_pipeline import get_prompt_pipeline
from services.storage import get_storage_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])


# ============ Helpers ============


def get_user_id_from_user(user: GitHubUser | None) -> str:
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
        raise HTTPException(status_code=400, detail="No API key configured")

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
        user_id=user_id,
        request_id=f"gen_{uuid.uuid4().hex[:12]}",
    )


# ============ Endpoints ============


@router.post("", response_model=GenerateImageResponse)
async def generate_image(
    request: GenerateImageRequest,
    user: GitHubUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    template_repo: TemplateRepository | None = Depends(get_template_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_provider: str | None = Header(None, alias="X-Provider"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_routing_strategy: str | None = Header(None, alias="X-Routing-Strategy"),  # noqa: ARG001
):
    """
    Generate a single image from a text prompt.

    Supports multi-provider routing via headers:
    - X-Provider: Specify provider (google, openai, bfl, stability)
    - X-Model: Specify model ID
    - X-Routing-Strategy: Override routing (priority, cost, quality, speed)

    Returns the generated image info and metadata.
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

    # Build provider request
    provider_request = build_provider_request(
        prompt=final_prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider=x_provider,
        preferred_model=x_model,
        enable_thinking=request.include_thinking,
        negative_prompt=negative_prompt,
    )

    # Use multi-provider router
    router_instance = get_provider_router()

    try:
        # Route and execute with fallback
        result = await router_instance.execute_with_fallback(
            request=provider_request,
            media_type=MediaType.IMAGE,
        )
    except ValueError as e:
        # No providers available
        logger.warning(f"No providers available, falling back to legacy: {e}")
        # Fallback to legacy generator
        generator = create_generator(x_api_key)
        legacy_result = generator.generate(
            prompt=request.prompt,
            aspect_ratio=request.settings.aspect_ratio.value,
            resolution=request.settings.resolution.value,
            enable_thinking=request.include_thinking,
            safety_level=request.settings.safety_level.value,
        )
        # Convert legacy result
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
        raise HTTPException(status_code=400, detail=get_friendly_error_message(result.error))

    if not result.image:
        raise HTTPException(status_code=500, detail="Failed to generate image")

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
        raise HTTPException(status_code=500, detail="Failed to save image")

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
                user_id=None,  # TODO: Get user UUID from authenticated user
            )
        except Exception as e:
            logger.warning(f"Failed to save image to database: {e}")
            # Continue - file storage is the primary storage

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
        # New: provider info
        provider=result.provider,
        model=result.model,
        # Prompt pipeline
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
    user: GitHubUser | None = Depends(get_current_user),
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


@router.get("/task/{task_id}", response_model=TaskProgress)
async def get_task_progress(task_id: str):
    """Get progress of a batch generation task."""
    import json

    redis = await get_redis()
    task_key = f"task:{task_id}"

    task_data = await redis.hgetall(task_key)

    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    results = json.loads(task_data.get("results", "[]"))
    errors = json.loads(task_data.get("errors", "[]"))

    return TaskProgress(
        task_id=task_id,
        status=task_data.get("status", "unknown"),
        progress=int(task_data.get("progress", 0)),
        total=int(task_data.get("total", 0)),
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
    user: GitHubUser | None = Depends(get_current_user),
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

    # Build provider request with search enabled
    provider_request = build_provider_request(
        prompt=final_prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider=x_provider or "google",  # Search only works with Google
        preferred_model=x_model,
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
        raise HTTPException(status_code=400, detail=get_friendly_error_message(result.error))

    if not result.image:
        raise HTTPException(status_code=500, detail="Failed to generate image")

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
        raise HTTPException(status_code=500, detail="Failed to save image")

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
        # Prompt pipeline
        processed_prompt=processed.final if processed else None,
        negative_prompt=negative_prompt,
        template_used=processed.template_used if processed else False,
        was_translated=processed.was_translated if processed else False,
        was_enhanced=processed.was_enhanced if processed else False,
        template_name=processed.template_name if processed else None,
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
