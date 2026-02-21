"""
Background task for image operations: blend, inpaint, outpaint, search.

Simpler than generation_task.py's race pattern — single provider execution,
no staggered fallbacks.

# TODO: migrate to ARQ for production reliability
"""

import json
import logging
from datetime import datetime

from core.config import get_settings
from core.redis import get_redis
from database import get_session, is_database_available
from database.repositories import ImageRepository, QuotaRepository

from .provider_router import get_provider_router
from .providers.base import GenerationRequest, MediaType
from .providers.registry import get_provider_registry
from .storage import get_storage_manager
from .websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


async def execute_image_task(
    task_id: str,
    mode: str,
    user_id: str,
    prompt: str,
    settings_dict: dict,
    task_spec: dict,
) -> None:
    """Background task entry point for blend/inpaint/outpaint/search.

    Runs outside of FastAPI request context — all services are
    manually instantiated (no Depends()).

    Args:
        task_id: Unique task ID (gen_* prefix).
        mode: One of "blend", "inpaint", "outpaint", "search".
        user_id: User ID for quota/storage/websocket.
        prompt: The prompt to use for generation.
        settings_dict: Serialized generation settings.
        task_spec: Mode-specific parameters (image_keys, mask_key, etc.).
    """
    redis = await get_redis()
    task_key = f"task:{task_id}"
    ws_manager = get_websocket_manager()

    try:
        # Update status → generating
        now = datetime.now().isoformat()
        await redis.hset(
            task_key,
            mapping={
                "status": "generating",
                "stage": "generating",
                "progress": "0.2",
                "started_at": now,
            },
        )
        await ws_manager.send_generate_progress(
            user_id=user_id,
            request_id=task_id,
            stage="generating",
            progress=0.2,
        )

        # Execute the appropriate mode
        result = await _execute_mode(
            mode=mode,
            prompt=prompt,
            settings_dict=settings_dict,
            task_spec=task_spec,
            user_id=user_id,
        )

        if not result.success or not result.image:
            error_msg = result.error or f"Failed to {mode} image"
            await redis.hset(
                task_key,
                mapping={
                    "status": "failed",
                    "error": error_msg,
                    "error_code": result.error_type or "",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            await ws_manager.send_generate_error(
                user_id=user_id,
                request_id=task_id,
                error=error_msg,
                code=result.error_type,
            )
            # Refund quota
            quota_svc = _get_quota_service(redis)
            await quota_svc.refund_quota(user_id, 1)
            return

        # Success — save and finalize
        response_data = await _save_and_finalize(
            result=result,
            mode=mode,
            prompt=prompt,
            settings_dict=settings_dict,
            user_id=user_id,
            task_spec=task_spec,
        )

        await redis.hset(
            task_key,
            mapping={
                "status": "completed",
                "progress": "1.0",
                "provider": result.provider or "",
                "model": result.model or "",
                "result_json": json.dumps(response_data),
                "completed_at": datetime.now().isoformat(),
            },
        )

        await ws_manager.send_generate_complete(
            user_id=user_id,
            request_id=task_id,
            image_id=response_data.get("image", {}).get("key", ""),
            url=response_data.get("image", {}).get("url", ""),
            prompt=prompt,
            provider=result.provider or "",
            duration_ms=int(result.duration * 1000) if result.duration else 0,
        )

    except Exception:
        logger.exception("Unhandled error in image task %s (mode=%s)", task_id, mode)
        try:
            await redis.hset(
                task_key,
                mapping={
                    "status": "failed",
                    "error": "Internal server error",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            await ws_manager.send_generate_error(
                user_id=user_id,
                request_id=task_id,
                error="Internal server error",
            )
            # Refund quota on unexpected failure
            quota_svc = _get_quota_service(redis)
            await quota_svc.refund_quota(user_id, 1)
        except Exception:
            logger.exception("Failed to update task status after error for %s", task_id)


async def _execute_mode(
    mode: str,
    prompt: str,
    settings_dict: dict,
    task_spec: dict,
    user_id: str,
):
    """Execute the provider call for the given mode.

    Returns a GenerationResult.
    """
    from api.schemas.generate import GenerationSettings

    storage = get_storage_manager(user_id=user_id if user_id != "anonymous" else None)
    router = get_provider_router()

    # Reconstruct GenerationSettings for build_provider_request
    settings = GenerationSettings(
        aspect_ratio=settings_dict.get("aspect_ratio", "16:9"),
        resolution=settings_dict.get("resolution", "1K"),
        safety_level=settings_dict.get("safety_level", "moderate"),
    )

    if mode == "blend":
        return await _execute_blend(storage, router, prompt, settings, user_id, task_spec)
    elif mode == "inpaint":
        return await _execute_inpaint(storage, router, prompt, settings, user_id, task_spec)
    elif mode == "outpaint":
        return await _execute_outpaint(storage, router, prompt, settings, user_id, task_spec)
    elif mode == "search":
        return await _execute_search(router, prompt, settings, user_id, task_spec)
    else:
        from .providers.base import GenerationResult

        return GenerationResult(
            success=False,
            error=f"Unknown mode: {mode}",
            provider="none",
        )


async def _execute_blend(storage, router, prompt, settings, user_id, task_spec):
    """Execute blend mode."""
    from .providers.base import GenerationResult

    image_keys = task_spec["image_keys"]
    loaded_images = []
    for key in image_keys:
        img = await storage.load_image(key)
        if img is None:
            return GenerationResult(
                success=False,
                error=f"Image not found: {key}",
                provider="none",
            )
        loaded_images.append(img)

    provider_request = _build_request(
        prompt=prompt,
        settings=settings,
        user_id=user_id,
        preferred_provider="google",
        reference_images=loaded_images,
    )

    return await router.execute(
        request=provider_request,
        media_type=MediaType.IMAGE,
    )


async def _execute_inpaint(storage, router, prompt, settings, user_id, task_spec):
    """Execute inpaint mode."""
    from .providers.base import GenerationResult

    source_img = await storage.load_image(task_spec["image_key"])
    if source_img is None:
        return GenerationResult(
            success=False,
            error=f"Image not found: {task_spec['image_key']}",
            provider="none",
        )

    mask_img = None
    if task_spec.get("mask_key"):
        mask_img = await storage.load_image(task_spec["mask_key"])
        if mask_img is None:
            return GenerationResult(
                success=False,
                error=f"Mask image not found: {task_spec['mask_key']}",
                provider="none",
            )

    edit_mode = "inpaint_remove" if task_spec.get("remove_mode") else "inpaint_insert"

    provider_request = _build_request(
        prompt=prompt,
        settings=settings,
        user_id=user_id,
        preferred_provider="google",
        negative_prompt=task_spec.get("negative_prompt"),
        reference_images=[source_img],
        mask_image=mask_img,
        edit_mode=edit_mode,
        mask_mode=task_spec.get("mask_mode", "user_provided"),
        mask_dilation=task_spec.get("mask_dilation", 0.03),
    )

    return await router.execute(
        request=provider_request,
        media_type=MediaType.IMAGE,
    )


async def _execute_outpaint(storage, router, prompt, settings, user_id, task_spec):
    """Execute outpaint mode."""
    from .providers.base import GenerationResult

    source_img = await storage.load_image(task_spec["image_key"])
    if source_img is None:
        return GenerationResult(
            success=False,
            error=f"Image not found: {task_spec['image_key']}",
            provider="none",
        )

    mask_img = await storage.load_image(task_spec["mask_key"])
    if mask_img is None:
        return GenerationResult(
            success=False,
            error=f"Mask image not found: {task_spec['mask_key']}",
            provider="none",
        )

    provider_request = _build_request(
        prompt=prompt,
        settings=settings,
        user_id=user_id,
        preferred_provider="google",
        negative_prompt=task_spec.get("negative_prompt"),
        reference_images=[source_img],
        mask_image=mask_img,
        edit_mode="outpaint",
    )

    return await router.execute(
        request=provider_request,
        media_type=MediaType.IMAGE,
    )


async def _execute_search(router, prompt, settings, user_id, task_spec):
    """Execute search-grounded generation."""
    provider_request = _build_request(
        prompt=prompt,
        settings=settings,
        user_id=user_id,
        preferred_provider=task_spec.get("preferred_provider", "google"),
        preferred_model=task_spec.get("preferred_model"),
        enable_search=True,
        negative_prompt=task_spec.get("negative_prompt"),
    )

    return await router.execute_with_fallback(
        request=provider_request,
        media_type=MediaType.IMAGE,
    )


def _build_request(
    prompt: str,
    settings,
    user_id: str,
    preferred_provider: str | None = None,
    preferred_model: str | None = None,
    enable_search: bool = False,
    negative_prompt: str | None = None,
    reference_images: list | None = None,
    mask_image=None,
    edit_mode: str | None = None,
    mask_mode: str | None = None,
    mask_dilation: float = 0.03,
) -> GenerationRequest:
    """Build a GenerationRequest (same as generate.py's build_provider_request)."""
    import uuid

    return GenerationRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        aspect_ratio=settings.aspect_ratio.value,
        resolution=settings.resolution.value,
        safety_level=settings.safety_level.value,
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
        enable_search=enable_search,
        reference_images=reference_images,
        mask_image=mask_image,
        edit_mode=edit_mode,
        mask_mode=mask_mode,
        mask_dilation=mask_dilation,
        user_id=user_id,
        request_id=f"gen_{uuid.uuid4().hex[:12]}",
    )


async def _save_and_finalize(
    result,
    mode: str,
    prompt: str,
    settings_dict: dict,
    user_id: str,
    task_spec: dict,
) -> dict:
    """Save image to storage + DB and return serializable response dict."""
    from api.schemas.generate import (
        GeneratedImage,
        GenerateImageResponse,
        GenerationMode,
        GenerationSettings,
    )

    storage = get_storage_manager(user_id=user_id if user_id != "anonymous" else None)

    storage_obj = await storage.save_image(
        image=result.image,
        prompt=prompt,
        settings={
            "aspect_ratio": settings_dict.get("aspect_ratio", "16:9"),
            "resolution": settings_dict.get("resolution", "1K"),
            "provider": result.provider,
            "model": result.model,
        },
        duration=result.duration,
        mode=mode,
        text_response=result.text_response,
    )

    # Save to PostgreSQL if available
    if is_database_available():
        try:
            async for session in get_session():
                image_repo = ImageRepository(session)
                await image_repo.create(
                    storage_key=storage_obj.key,
                    filename=storage_obj.filename,
                    prompt=prompt,
                    mode=mode,
                    storage_backend=get_settings().storage_backend,
                    public_url=storage_obj.public_url,
                    aspect_ratio=settings_dict.get("aspect_ratio", "16:9"),
                    resolution=settings_dict.get("resolution", "1K"),
                    provider=result.provider,
                    model=result.model,
                    width=result.image.width if result.image else None,
                    height=result.image.height if result.image else None,
                    generation_duration_ms=int(result.duration * 1000) if result.duration else None,
                    text_response=result.text_response,
                    user_id=None,
                )
        except Exception as e:
            logger.warning("Failed to save image to database: %s", e)

    # Record quota usage to PostgreSQL if available
    if is_database_available():
        try:
            async for session in get_session():
                quota_repo = QuotaRepository(session)
                await quota_repo.record_usage(
                    mode=mode,
                    points_used=1,
                    provider=result.provider,
                    model=result.model,
                    resolution=settings_dict.get("resolution", "1K"),
                    media_type="image",
                )
        except Exception as e:
            logger.warning("Failed to record quota usage to database: %s", e)

    # Resolve model display name
    model_display_name = None
    if result.model:
        registry = get_provider_registry()
        for p in registry.get_available_image_providers():
            m = p.get_model_by_id(result.model)
            if m:
                model_display_name = m.name
                break

    gen_settings = GenerationSettings(
        aspect_ratio=settings_dict.get("aspect_ratio", "16:9"),
        resolution=settings_dict.get("resolution", "1K"),
        safety_level=settings_dict.get("safety_level", "moderate"),
    )

    # Map mode string to GenerationMode enum
    mode_enum = GenerationMode(mode)

    response = GenerateImageResponse(
        image=GeneratedImage(
            key=storage_obj.key,
            filename=storage_obj.filename,
            url=storage_obj.public_url,
            width=result.image.width if result.image else None,
            height=result.image.height if result.image else None,
        ),
        prompt=prompt,
        text_response=result.text_response,
        search_sources=getattr(result, "search_sources", None),
        duration=result.duration,
        mode=mode_enum,
        settings=gen_settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
        model_display_name=model_display_name,
        quality_preset=task_spec.get("quality_preset"),
        processed_prompt=task_spec.get("processed_prompt"),
        negative_prompt=task_spec.get("negative_prompt"),
        template_used=task_spec.get("template_used", False),
        was_translated=task_spec.get("was_translated", False),
        was_enhanced=task_spec.get("was_enhanced", False),
        template_name=task_spec.get("template_name"),
    )

    return response.model_dump(mode="json")


def _get_quota_service(redis):
    """Get quota service instance outside of DI."""
    from .quota_service import get_quota_service

    return get_quota_service(redis)
