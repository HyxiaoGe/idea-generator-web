"""Inpaint image endpoint."""

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
    GeneratedImage,
    GenerateImageResponse,
    GenerationMode,
    InpaintRequest,
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


@router.post("/inpaint")
async def inpaint_image(
    request: InpaintRequest,
    background_tasks: BackgroundTasks,
    sync: bool = Query(False, description="If true, run synchronously and return full result"),
    user: AppUser | None = Depends(get_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    quota_repo: QuotaRepository | None = Depends(get_quota_repository),
) -> GenerateImageResponse | AsyncGenerateResponse:
    """
    Inpaint an image -- insert or remove content in masked areas.

    By default runs asynchronously (returns task_id for polling).
    Pass ?sync=true for synchronous mode (blocks until complete).

    Requires a source image key. Mask is required for user_provided mode,
    or auto-detected for foreground/background/semantic modes.
    Uses Google Imagen edit_image API.
    """
    user_id = get_user_id_from_user(user)

    # Check quota
    await check_quota_and_consume(user_id)

    # Validate mask_mode constraint (no I/O needed)
    if not request.mask_key and request.mask_mode.value == "user_provided":
        raise ValidationError(message="mask_key is required when mask_mode is user_provided")

    # -- sync path --
    if sync:
        return await _inpaint_sync(request, user_id, user, image_repo, quota_repo)

    # -- async path (default) --
    # Validate images exist before queuing (fast check)
    storage = get_storage_manager(user_id=user_id if user else None)

    source_img = await storage.load_image(request.image_key)
    if source_img is None:
        raise ValidationError(message=f"Image not found: {request.image_key}")

    if request.mask_key:
        mask_img = await storage.load_image(request.mask_key)
        if mask_img is None:
            raise ValidationError(message=f"Mask image not found: {request.mask_key}")

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
            "request_json": json.dumps(settings_dict),
            "created_at": datetime.now().isoformat(),
        },
    )
    await redis.expire(task_key, 86400)

    from services.image_task import execute_image_task

    background_tasks.add_task(
        execute_image_task,
        task_id=task_id,
        mode="inpaint",
        user_id=user_id,
        prompt=request.prompt,
        settings_dict=settings_dict,
        task_spec={
            "image_key": request.image_key,
            "mask_key": request.mask_key,
            "mask_mode": request.mask_mode.value,
            "mask_dilation": request.mask_dilation,
            "remove_mode": request.remove_mode,
            "negative_prompt": request.negative_prompt,
        },
    )

    return AsyncGenerateResponse(
        task_id=task_id,
        status="queued",
        message="Inpaint task queued",
    )


async def _inpaint_sync(
    request: InpaintRequest,
    user_id: str,
    user: AppUser | None,
    image_repo: ImageRepository | None,
    quota_repo: QuotaRepository | None,
) -> GenerateImageResponse:
    """Synchronous inpaint -- keeps the original blocking behavior."""
    storage = get_storage_manager(user_id=user_id if user else None)

    source_img = await storage.load_image(request.image_key)
    if source_img is None:
        raise ValidationError(message=f"Image not found: {request.image_key}")

    mask_img = None
    if request.mask_key:
        mask_img = await storage.load_image(request.mask_key)
        if mask_img is None:
            raise ValidationError(message=f"Mask image not found: {request.mask_key}")

    edit_mode = "inpaint_remove" if request.remove_mode else "inpaint_insert"

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
        required_capability=ProviderCapability.INPAINTING,
    )

    router_instance = get_provider_router()

    try:
        result = await router_instance.execute_with_fallback(
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
