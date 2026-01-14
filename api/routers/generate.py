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

import uuid
import time
import base64
import logging
from io import BytesIO
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header

from core.config import get_settings
from core.redis import get_redis
from core.exceptions import QuotaExceededError, GenerationError
from services import (
    ImageGenerator,
    R2Storage,
    get_r2_storage,
    QuotaService,
    get_quota_service,
    is_trial_mode,
    get_friendly_error_message,
)
from api.schemas.generate import (
    GenerateImageRequest,
    GenerateImageResponse,
    GeneratedImage,
    GenerationSettings,
    GenerationMode,
    BatchGenerateRequest,
    BatchGenerateResponse,
    TaskProgress,
    BlendImagesRequest,
    StyleTransferRequest,
    SearchGenerateRequest,
    AspectRatio,
    Resolution,
    SafetyLevel,
)
from api.routers.auth import get_current_user
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])


# ============ Helpers ============

def get_user_id_from_user(user: Optional[GitHubUser]) -> str:
    """Get user ID for quota tracking."""
    if user:
        return user.user_folder_id
    return "anonymous"


async def check_quota_and_consume(
    user_id: str,
    mode: str,
    resolution: str,
    count: int = 1,
    api_key: Optional[str] = None,
) -> bool:
    """
    Check quota and consume if available.

    Raises:
        QuotaExceededError: If quota exceeded
    """
    # Skip quota check if user has own API key
    if api_key and not is_trial_mode(api_key):
        return True

    redis = await get_redis()
    quota_service = get_quota_service(redis)

    if not quota_service.is_trial_enabled:
        return True

    can_generate, reason, info = await quota_service.check_quota(
        user_id=user_id,
        mode=mode,
        resolution=resolution,
        count=count,
    )

    if not can_generate:
        raise QuotaExceededError(
            message=reason,
            details=info,
        )

    # Consume quota
    await quota_service.consume_quota(
        user_id=user_id,
        mode=mode,
        resolution=resolution,
        count=count,
    )

    return True


def create_generator(api_key: Optional[str] = None) -> ImageGenerator:
    """Create image generator with appropriate API key."""
    settings = get_settings()
    key = api_key or settings.google_api_key

    if not key:
        raise HTTPException(
            status_code=400,
            detail="No API key configured"
        )

    return ImageGenerator(api_key=key)


# ============ Endpoints ============

@router.post("", response_model=GenerateImageResponse)
async def generate_image(
    request: GenerateImageRequest,
    user: Optional[GitHubUser] = Depends(get_current_user),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Generate a single image from a text prompt.

    Returns the generated image info and metadata.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(
        user_id=user_id,
        mode="basic",
        resolution=request.settings.resolution.value,
        api_key=x_api_key,
    )

    # Create generator
    generator = create_generator(x_api_key)

    # Generate image
    start_time = time.time()
    result = generator.generate(
        prompt=request.prompt,
        aspect_ratio=request.settings.aspect_ratio.value,
        resolution=request.settings.resolution.value,
        enable_thinking=request.include_thinking,
        safety_level=request.settings.safety_level.value,
    )

    if result.error:
        raise HTTPException(
            status_code=400,
            detail=get_friendly_error_message(result.error)
        )

    if not result.image:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate image"
        )

    # Save to storage
    r2_storage = get_r2_storage(user_id=user_id if user else None)

    image_key = r2_storage.save_image(
        image=result.image,
        prompt=request.prompt,
        settings={
            "aspect_ratio": request.settings.aspect_ratio.value,
            "resolution": request.settings.resolution.value,
        },
        duration=result.duration,
        mode="basic",
        text_response=result.text,
        thinking=result.thinking,
    )

    if not image_key:
        raise HTTPException(
            status_code=500,
            detail="Failed to save image"
        )

    # Build response
    public_url = r2_storage.get_public_url(image_key)

    return GenerateImageResponse(
        image=GeneratedImage(
            key=image_key,
            filename=image_key.split("/")[-1],
            url=public_url,
            width=result.image.width,
            height=result.image.height,
        ),
        prompt=request.prompt,
        thinking=result.thinking,
        text_response=result.text,
        duration=result.duration,
        mode=GenerationMode.BASIC,
        settings=request.settings,
        created_at=datetime.now(),
    )


@router.post("/batch", response_model=BatchGenerateResponse)
async def batch_generate(
    request: BatchGenerateRequest,
    background_tasks: BackgroundTasks,
    user: Optional[GitHubUser] = Depends(get_current_user),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Queue a batch image generation task.

    Returns a task ID for tracking progress via WebSocket or polling.
    """
    user_id = get_user_id_from_user(user)
    count = len(request.prompts)

    # Check quota for entire batch
    await check_quota_and_consume(
        user_id=user_id,
        mode="batch",
        resolution=request.settings.resolution.value,
        count=count,
        api_key=x_api_key,
    )

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

    await redis.hset(f"task:{task_id}", mapping={
        k: str(v) if not isinstance(v, (list, dict)) else __import__("json").dumps(v)
        for k, v in task_data.items()
    })
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
    api_key: Optional[str],
):
    """Background task to process batch generation."""
    import json

    redis = await get_redis()
    task_key = f"task:{task_id}"

    await redis.hset(task_key, "status", "processing")
    await redis.hset(task_key, "started_at", datetime.now().isoformat())

    generator = create_generator(api_key)
    r2_storage = get_r2_storage(user_id=user_id if user_id != "anonymous" else None)

    results = []
    errors = []

    for i, prompt in enumerate(prompts):
        try:
            # Update current prompt
            await redis.hset(task_key, "current_prompt", prompt)

            result = generator.generate(
                prompt=prompt,
                aspect_ratio=settings.aspect_ratio.value,
                resolution=settings.resolution.value,
                safety_level=settings.safety_level.value,
            )

            if result.error:
                errors.append(f"Prompt {i+1}: {result.error}")
            elif result.image:
                image_key = r2_storage.save_image(
                    image=result.image,
                    prompt=prompt,
                    settings={
                        "aspect_ratio": settings.aspect_ratio.value,
                        "resolution": settings.resolution.value,
                    },
                    duration=result.duration,
                    mode="batch",
                )

                if image_key:
                    results.append({
                        "key": image_key,
                        "filename": image_key.split("/")[-1],
                        "url": r2_storage.get_public_url(image_key),
                    })

        except Exception as e:
            errors.append(f"Prompt {i+1}: {str(e)}")
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
        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )

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
        started_at=datetime.fromisoformat(task_data["started_at"]) if "started_at" in task_data else None,
        completed_at=datetime.fromisoformat(task_data["completed_at"]) if "completed_at" in task_data else None,
    )


@router.post("/search", response_model=GenerateImageResponse)
async def search_grounded_generate(
    request: SearchGenerateRequest,
    user: Optional[GitHubUser] = Depends(get_current_user),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Generate an image with search grounding.

    Uses real-time search data to inform generation.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(
        user_id=user_id,
        mode="search",
        resolution=request.settings.resolution.value,
        api_key=x_api_key,
    )

    # Create generator
    generator = create_generator(x_api_key)

    # Generate with search enabled
    result = generator.generate(
        prompt=request.prompt,
        aspect_ratio=request.settings.aspect_ratio.value,
        resolution=request.settings.resolution.value,
        enable_search=True,
        safety_level=request.settings.safety_level.value,
    )

    if result.error:
        raise HTTPException(
            status_code=400,
            detail=get_friendly_error_message(result.error)
        )

    if not result.image:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate image"
        )

    # Save to storage
    r2_storage = get_r2_storage(user_id=user_id if user else None)

    image_key = r2_storage.save_image(
        image=result.image,
        prompt=request.prompt,
        settings={
            "aspect_ratio": request.settings.aspect_ratio.value,
            "resolution": request.settings.resolution.value,
        },
        duration=result.duration,
        mode="search",
        text_response=result.text,
    )

    if not image_key:
        raise HTTPException(
            status_code=500,
            detail="Failed to save image"
        )

    public_url = r2_storage.get_public_url(image_key)

    return GenerateImageResponse(
        image=GeneratedImage(
            key=image_key,
            filename=image_key.split("/")[-1],
            url=public_url,
            width=result.image.width,
            height=result.image.height,
        ),
        prompt=request.prompt,
        text_response=result.text,
        duration=result.duration,
        mode=GenerationMode.SEARCH,
        settings=request.settings,
        created_at=datetime.now(),
    )
