"""Blend images endpoint."""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from api.dependencies import (
    check_quota_and_consume,
    get_image_repository,
    get_quota_repository,
    get_user_id_from_user,
)
from api.schemas.generate import (
    AsyncGenerateResponse,
    BlendImagesRequest,
    GeneratedImage,
    GenerateImageResponse,
    GenerationMode,
)
from core.auth import AppUser, get_current_user
from core.config import get_settings
from core.exceptions import (
    GenerationError,
    StorageError,
    ValidationError,
)
from core.redis import get_redis
from database.repositories import ImageRepository, QuotaRepository
from services import (
    MediaType,
    get_friendly_error_message,
    get_provider_router,
)
from services.providers.base import ProviderCapability
from services.storage import get_storage_manager

from ._helpers import build_provider_request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/blend")
async def blend_images(
    request: BlendImagesRequest,
    background_tasks: BackgroundTasks,
    sync: bool = Query(False, description="If true, run synchronously and return full result"),
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
) -> GenerateImageResponse | AsyncGenerateResponse:
    """
    Blend 2-4 existing images together with an optional prompt.

    By default runs asynchronously (returns task_id for polling).
    Pass ?sync=true for synchronous mode (blocks until complete).

    Takes image storage keys, loads them, and uses Google Gemini to blend them.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # -- sync path --
    if sync:
        return await _blend_sync(request, user_id, user, image_repo, quota_repo)

    # -- async path (default) --
    # Validate images exist before queuing (fast check)
    storage = get_storage_manager(user_id=user_id if user else None)
    for key in request.image_keys:
        img = await storage.load_image(key)
        if img is None:
            raise ValidationError(message=f"Image not found: {key}")

    task_id = f"gen_{uuid.uuid4().hex[:12]}"
    prompt = request.blend_prompt or "Blend these images together creatively"
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
            "prompt": prompt,
            "request_json": json.dumps(settings_dict),
            "created_at": datetime.now().isoformat(),
        },
    )
    await redis.expire(task_key, 86400)

    from services.image_task import execute_image_task

    background_tasks.add_task(
        execute_image_task,
        task_id=task_id,
        mode="blend",
        user_id=user_id,
        prompt=prompt,
        settings_dict=settings_dict,
        task_spec={
            "image_keys": request.image_keys,
        },
    )

    return AsyncGenerateResponse(
        task_id=task_id,
        status="queued",
        message="Blend task queued",
    )


async def _blend_sync(
    request: BlendImagesRequest,
    user_id: str,
    user: AppUser | None,
    image_repo: ImageRepository | None,
    quota_repo: QuotaRepository | None,
) -> GenerateImageResponse:
    """Synchronous blend -- keeps the original blocking behavior."""
    storage = get_storage_manager(user_id=user_id if user else None)
    loaded_images = []

    for key in request.image_keys:
        img = await storage.load_image(key)
        if img is None:
            raise ValidationError(message=f"Image not found: {key}")
        loaded_images.append(img)

    prompt = request.blend_prompt or "Blend these images together creatively"

    provider_request = build_provider_request(
        prompt=prompt,
        settings=request.settings,
        user_id=user_id,
        preferred_provider="google",
        reference_images=loaded_images,
        required_capability=ProviderCapability.IMAGE_BLEND,
    )

    router_instance = get_provider_router()

    try:
        result = await router_instance.execute_with_fallback(
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
