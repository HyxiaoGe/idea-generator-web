"""
Video generation router.

Endpoints:
- POST /api/video - Start video generation
- GET /api/video/task/{task_id} - Get task progress
- GET /api/video/providers - List available video providers
- GET /api/video/providers/{name}/health - Check provider health
"""

import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header

from api.schemas.video import (
    GeneratedVideo,
    GenerateVideoRequest,
    GenerateVideoResponse,
    ImageToVideoRequest,
    ListVideoProvidersResponse,
    VideoProviderInfo,
    VideoTaskProgress,
    VideoTaskStatus,
)
from core.auth import AppUser, get_current_user
from core.config import get_settings
from core.exceptions import (
    AppException,
    GenerationError,
    ModelUnavailableError,
    QuotaExceededError,
    TaskNotFoundError,
    ValidationError,
)
from core.redis import get_redis
from services import get_quota_service
from services.providers import (
    GenerationRequest as ProviderRequest,
)
from services.providers import (
    KlingProvider,
    ProviderConfig,
    RunwayProvider,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


# ============ Provider Registry for Video ============

_video_providers: dict = {}


def _init_video_providers():
    """Initialize video providers based on configuration."""
    global _video_providers

    if _video_providers:
        return _video_providers

    settings = get_settings()

    # Initialize Runway if enabled
    if settings.provider_runway_enabled:
        api_key = settings.get_provider_api_key("runway")
        if api_key:
            _video_providers["runway"] = RunwayProvider(ProviderConfig(api_key=api_key))
            logger.info("Runway video provider initialized")

    # Initialize Kling if enabled
    if settings.provider_kling_enabled:
        api_key = settings.get_provider_api_key("kling")
        secret_key = getattr(settings, "provider_kling_secret_key", None)
        if api_key:
            _video_providers["kling"] = KlingProvider(
                ProviderConfig(
                    api_key=api_key,
                    extra={"secret_key": secret_key} if secret_key else {},
                )
            )
            logger.info("Kling video provider initialized")

    return _video_providers


def get_video_provider(provider_name: str | None = None):
    """Get a video provider by name or return default."""
    providers = _init_video_providers()

    if not providers:
        raise ModelUnavailableError(
            message="No video providers configured. Please configure Runway or Kling API keys.",
        )

    if provider_name:
        if provider_name not in providers:
            raise ValidationError(
                message=f"Provider '{provider_name}' not found. Available: {list(providers.keys())}",
            )
        return providers[provider_name]

    # Return default provider based on priority
    settings = get_settings()
    default_provider = settings.default_video_provider

    if default_provider in providers:
        return providers[default_provider]

    # Return first available
    return next(iter(providers.values()))


def get_user_id_from_user(user: AppUser | None) -> str:
    """Get user ID for tracking."""
    if user:
        return user.user_folder_id
    return "anonymous"


# ============ Task Storage (Redis-based) ============


async def store_video_task(task_id: str, task_data: dict):
    """Store video task info in Redis."""
    redis = await get_redis()
    if redis:
        import json

        await redis.setex(
            f"video_task:{task_id}",
            3600 * 24,  # 24 hour TTL
            json.dumps(task_data),
        )


async def get_video_task(task_id: str) -> dict | None:
    """Get video task info from Redis."""
    redis = await get_redis()
    if redis:
        import json

        data = await redis.get(f"video_task:{task_id}")
        if data:
            return json.loads(data)
    return None


async def update_video_task(task_id: str, updates: dict):
    """Update video task info in Redis."""
    task_data = await get_video_task(task_id)
    if task_data:
        task_data.update(updates)
        await store_video_task(task_id, task_data)


# ============ Endpoints ============


@router.post(
    "",
    response_model=GenerateVideoResponse,
    summary="Start video generation",
    description="Start async video generation. Returns a task ID for polling.",
)
async def generate_video(
    request: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    x_provider: str | None = Header(None, description="Preferred video provider"),
    x_model: str | None = Header(None, description="Specific model to use"),
    user: AppUser | None = Depends(get_current_user),
):
    """
    Start video generation from text prompt.

    Returns a task ID that can be used to poll for progress.
    """
    time.time()
    request_id = str(uuid.uuid4())
    user_id = get_user_id_from_user(user)

    logger.info(f"[{request_id}] Video generation request from user {user_id}")

    # Check and consume quota
    try:
        redis = await get_redis()
        quota_service = get_quota_service(redis)

        can_generate, reason, info = await quota_service.check_quota(
            user_id=user_id,
            count=1,
        )
        if not can_generate:
            raise QuotaExceededError(message=reason, details=info)

        await quota_service.consume_quota(user_id=user_id, count=1)
    except QuotaExceededError:
        raise
    except Exception as e:
        logger.warning(f"Quota check failed, allowing generation: {e}")

    try:
        # Get provider
        provider = get_video_provider(x_provider)
        provider_name = provider.name

        # Select model
        model_id = x_model
        if not model_id:
            default_model = provider.get_default_model()
            model_id = default_model.id if default_model else None

        # Build provider request
        provider_request = ProviderRequest(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            aspect_ratio=request.settings.aspect_ratio.value if request.settings else "16:9",
            duration=request.settings.duration if request.settings else 5,
            fps=request.settings.fps if request.settings else 24,
            seed=request.seed,
            user_id=user_id,
            request_id=request_id,
        )

        # Start generation
        result = await provider.generate(provider_request, model_id=model_id)

        if result.success and result.video_task_id:
            # Store task info for tracking
            task_data = {
                "task_id": result.video_task_id,
                "provider": provider_name,
                "model": result.model,
                "status": "queued",
                "progress": 0,
                "prompt": request.prompt[:200],  # Truncate for storage
                "created_at": datetime.now().isoformat(),
                "user_id": user_id,
                "estimated_cost": result.cost,
            }
            await store_video_task(result.video_task_id, task_data)

            return GenerateVideoResponse(
                task_id=result.video_task_id,
                status=VideoTaskStatus.QUEUED,
                message="Video generation started",
                estimated_duration=int(provider_request.duration * 15)
                if provider_request.duration
                else 60,
                provider=provider_name,
                model=result.model,
            )
        else:
            raise GenerationError(
                message=result.error or "Failed to start video generation",
                error_type=result.error_type,
            )

    except AppException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}")
        raise GenerationError(message=str(e))


@router.post(
    "/image-to-video",
    response_model=GenerateVideoResponse,
    summary="Generate video from image",
    description="Animate an image to create a video.",
)
async def image_to_video(
    request: ImageToVideoRequest,
    background_tasks: BackgroundTasks,
    x_provider: str | None = Header(None, description="Preferred video provider"),
    x_model: str | None = Header(None, description="Specific model to use"),
    user: AppUser | None = Depends(get_current_user),
):
    """
    Generate video from an image (image animation).

    The image_key should be a valid image key from the storage system.
    """
    request_id = str(uuid.uuid4())
    user_id = get_user_id_from_user(user)

    logger.info(f"[{request_id}] Image-to-video request from user {user_id}")

    # For now, return not implemented
    # Full implementation would:
    # 1. Load image from storage using image_key
    # 2. Convert to PIL Image
    # 3. Call provider.generate with reference_images
    from fastapi import HTTPException

    raise HTTPException(
        status_code=501,
        detail="Image-to-video is coming soon. Please use text-to-video for now.",
    )


@router.get(
    "/task/{task_id}",
    response_model=VideoTaskProgress,
    summary="Get video task progress",
    description="Poll for video generation task status.",
)
async def get_task_progress(
    task_id: str,
    user: AppUser | None = Depends(get_current_user),
):
    """
    Get the progress of a video generation task.

    Poll this endpoint to check if the video is ready.
    """
    # Get stored task info
    task_data = await get_video_task(task_id)

    if not task_data:
        raise TaskNotFoundError()

    provider_name = task_data.get("provider")
    if not provider_name:
        raise GenerationError(message="Task provider information missing")

    try:
        provider = get_video_provider(provider_name)
        status = await provider.get_task_status(task_id)

        # Map status to our enum
        status_map = {
            "queued": VideoTaskStatus.QUEUED,
            "processing": VideoTaskStatus.PROCESSING,
            "completed": VideoTaskStatus.COMPLETED,
            "failed": VideoTaskStatus.FAILED,
            "cancelled": VideoTaskStatus.CANCELLED,
        }

        task_status = status_map.get(status.get("status", ""), VideoTaskStatus.PROCESSING)

        # Update stored task
        await update_video_task(
            task_id,
            {
                "status": status.get("status"),
                "progress": status.get("progress", 0),
            },
        )

        # Build response
        response = VideoTaskProgress(
            task_id=task_id,
            status=task_status,
            progress=status.get("progress", 0),
            provider=provider_name,
            model=task_data.get("model"),
            estimated_cost=task_data.get("estimated_cost"),
            created_at=datetime.fromisoformat(task_data.get("created_at"))
            if task_data.get("created_at")
            else datetime.now(),
        )

        # Add video info if completed
        if task_status == VideoTaskStatus.COMPLETED and status.get("video_url"):
            response.video = GeneratedVideo(
                task_id=task_id,
                url=status.get("video_url"),
                thumbnail_url=status.get("thumbnail_url"),
            )
            response.completed_at = datetime.now()

        # Add error if failed
        if task_status == VideoTaskStatus.FAILED:
            response.error = status.get("error", "Unknown error")

        return response

    except AppException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise GenerationError(message=str(e))


@router.get(
    "/providers",
    response_model=ListVideoProvidersResponse,
    summary="List video providers",
    description="Get list of available video generation providers.",
)
async def list_providers():
    """List all configured video providers and their models."""
    providers = _init_video_providers()
    settings = get_settings()

    provider_list = []
    for name, provider in providers.items():
        models = [
            {
                "id": m.id,
                "name": m.name,
                "max_duration": m.max_video_duration,
                "pricing_per_second": m.pricing_per_unit,
                "quality_score": m.quality_score,
                "is_default": m.is_default,
            }
            for m in provider.models
        ]

        # Get max duration from models
        max_duration = max(m.max_video_duration or 0 for m in provider.models)

        # Get supported resolutions
        resolutions = list({m.max_resolution for m in provider.models})

        provider_list.append(
            VideoProviderInfo(
                name=name,
                display_name=provider.display_name,
                models=models,
                max_duration=max_duration,
                supported_resolutions=resolutions,
                pricing_per_second=provider.models[0].pricing_per_unit if provider.models else 0.0,
            )
        )

    return ListVideoProvidersResponse(
        providers=provider_list,
        default_provider=settings.default_video_provider,
        routing_strategy=settings.default_routing_strategy,
    )


@router.get(
    "/providers/{provider_name}/health",
    summary="Check provider health",
    description="Check the health status of a specific video provider.",
)
async def check_provider_health(provider_name: str):
    """Check health of a specific video provider."""
    try:
        provider = get_video_provider(provider_name)
        health = await provider.health_check()
        return health
    except AppException:
        raise
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": str(e)[:100],
        }


@router.delete(
    "/task/{task_id}",
    summary="Cancel video task",
    description="Cancel a pending or processing video generation task.",
)
async def cancel_task(
    task_id: str,
    user: AppUser | None = Depends(get_current_user),
):
    """
    Cancel a video generation task.

    Note: Not all providers support task cancellation.
    """
    task_data = await get_video_task(task_id)

    if not task_data:
        raise TaskNotFoundError()

    # For now, just update status to cancelled
    # Full implementation would call provider's cancel API if available
    await update_video_task(task_id, {"status": "cancelled"})

    return {"message": "Task cancellation requested", "task_id": task_id}
