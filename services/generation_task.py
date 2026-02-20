"""
Race-pattern generation task for async single-image generation.

Starts the primary provider, then launches staggered fallback providers
concurrently after a soft timeout — without killing the primary.
The first provider to succeed wins.

# TODO: migrate to ARQ for production reliability
"""

import asyncio
import json
import logging
import time
from datetime import datetime

from core.config import get_settings
from core.redis import get_redis
from database import get_session, is_database_available
from database.repositories import ImageRepository, QuotaRepository

from .provider_router import get_provider_router
from .providers.base import CircuitBreakerManager, GenerationRequest, GenerationResult
from .providers.registry import get_provider_registry
from .storage import get_storage_manager
from .websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


async def execute_generation_race(
    task_id: str,
    request: GenerationRequest,
    original_prompt: str,
    processed_prompt: str | None,
    negative_prompt: str | None,
    settings_dict: dict,
    user_id: str,
    primary_provider: str,
    primary_model: str,
    fallback_names: list[str],
    preset_used: str | None,
    template_used: bool,
    was_translated: bool,
    was_enhanced: bool,
    template_name: str | None,
) -> None:
    """Background task entry point for race-pattern image generation.

    Runs outside of FastAPI request context — all services are
    manually instantiated (no Depends()).
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

        # Run the race
        result = await _race_providers(
            task_id=task_id,
            task_key=task_key,
            request=request,
            user_id=user_id,
            primary_provider=primary_provider,
            primary_model=primary_model,
            fallback_names=fallback_names,
        )

        if result is None:
            # Cancelled
            return

        if not result.success or not result.image:
            # All providers failed
            error_msg = result.error or "All providers failed"
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
            original_prompt=original_prompt,
            processed_prompt=processed_prompt,
            negative_prompt=negative_prompt,
            settings_dict=settings_dict,
            user_id=user_id,
            preset_used=preset_used,
            template_used=template_used,
            was_translated=was_translated,
            was_enhanced=was_enhanced,
            template_name=template_name,
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
            prompt=original_prompt,
            provider=result.provider or "",
            duration_ms=int(result.duration * 1000) if result.duration else 0,
        )

    except Exception:
        logger.exception("Unhandled error in generation task %s", task_id)
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


async def _race_providers(
    task_id: str,
    task_key: str,
    request: GenerationRequest,
    user_id: str,
    primary_provider: str,
    primary_model: str,
    fallback_names: list[str],
) -> GenerationResult | None:
    """Staggered hedged-request race across providers.

    Returns the first successful result, or the last error result.
    Returns None if the task was cancelled.
    """
    redis = await get_redis()
    settings = get_settings()
    router = get_provider_router()
    router.initialize()
    ws_manager = get_websocket_manager()

    overall_timeout = settings.generation_overall_timeout
    stagger_interval = settings.provider_stagger_interval

    # Dynamic soft_timeout from primary provider's P90 latency
    latencies = router._adaptive.latencies.get(primary_provider, [])
    if len(latencies) >= 5:
        p90 = sorted(latencies)[int(len(latencies) * 0.9)]
        soft_timeout = min(p90 * 1.2, overall_timeout * 0.5)
        soft_timeout = max(soft_timeout, 10)  # floor at 10s
    else:
        soft_timeout = settings.provider_soft_timeout

    # Sort fallbacks by adaptive score descending
    scored = [(name, router._adaptive.score(name)) for name in fallback_names]
    scored.sort(key=lambda x: x[1], reverse=True)
    fallbacks = scored  # list of (name, score)

    # Resolve provider+model for each fallback
    fallback_configs: list[tuple[str, str]] = []
    for name, _ in fallbacks:
        provider_inst = router._registry.get_image_provider(name)
        if provider_inst and provider_inst.is_available:
            breaker = CircuitBreakerManager.get(name)
            if breaker.can_execute():
                model = provider_inst.get_default_model()
                if model:
                    fallback_configs.append((name, model.id))

    race_start = time.monotonic()
    last_error: GenerationResult | None = None

    # Helper to run a provider and tag the result
    async def _run_provider(prov_name: str, model_id: str) -> tuple[str, GenerationResult]:
        provider_inst = router._registry.get_image_provider(prov_name)
        if not provider_inst:
            return prov_name, GenerationResult(
                success=False,
                error=f"Provider not found: {prov_name}",
                provider=prov_name,
                model=model_id,
            )
        start = time.time()
        try:
            result = await provider_inst.generate(request, model_id=model_id)
            latency = time.time() - start
            if result.success:
                CircuitBreakerManager.get(prov_name).record_success()
                router._adaptive.update(
                    prov_name, success=True, latency=latency, cost=result.cost or 0
                )
            else:
                CircuitBreakerManager.get(prov_name).record_failure()
                router._adaptive.update(prov_name, success=False, latency=latency, cost=0)
            return prov_name, result
        except Exception as e:
            latency = time.time() - start
            CircuitBreakerManager.get(prov_name).record_failure()
            router._adaptive.update(prov_name, success=False, latency=latency, cost=0)
            return prov_name, GenerationResult(
                success=False,
                error=str(e),
                provider=prov_name,
                model=model_id,
            )

    # Phase 1: run primary until soft_timeout
    primary_task = asyncio.create_task(
        _run_provider(primary_provider, primary_model),
        name=f"gen:{primary_provider}",
    )

    pending: set[asyncio.Task] = {primary_task}

    done, pending = await asyncio.wait(pending, timeout=soft_timeout)

    for task in done:
        prov_name, result = task.result()
        if result.success:
            # Primary succeeded within soft_timeout — cancel nothing needed, pending is empty or just primary
            for p in pending:
                p.cancel()
            return result
        else:
            last_error = result
            pending.discard(task)
            # Primary failed outright; skip directly to Phase 2

    # Check cancellation before starting fallbacks
    cancelled = await redis.hget(task_key, "cancelled")
    if cancelled == "1":
        for t in pending:
            t.cancel()
        await redis.hset(
            task_key,
            mapping={
                "status": "cancelled",
                "completed_at": datetime.now().isoformat(),
            },
        )
        return None

    # Phase 2: staggered fallbacks (DON'T cancel primary — it may still finish)
    fallback_index = 0
    while time.monotonic() - race_start < overall_timeout:
        # Launch next fallback if available
        if fallback_index < len(fallback_configs):
            fb_name, fb_model = fallback_configs[fallback_index]
            fallback_index += 1

            logger.info("Race: launching fallback provider %s (index %d)", fb_name, fallback_index)
            await redis.hset(
                task_key,
                mapping={
                    "stage": "switching_provider",
                    "provider": fb_name,
                },
            )
            await ws_manager.send_generate_progress(
                user_id=user_id,
                request_id=task_id,
                stage="switching_provider",
                progress=0.5,
            )

            fb_task = asyncio.create_task(
                _run_provider(fb_name, fb_model),
                name=f"gen:{fb_name}",
            )
            pending.add(fb_task)

        if not pending:
            break

        # Wait for a winner or next stagger interval
        time_remaining = overall_timeout - (time.monotonic() - race_start)
        if time_remaining <= 0:
            break
        wait_time = min(stagger_interval, time_remaining)

        done, pending = await asyncio.wait(
            pending,
            return_when=asyncio.FIRST_COMPLETED,
            timeout=wait_time,
        )

        for task in done:
            prov_name, result = task.result()
            if result.success:
                # Winner! Cancel all pending
                for p in pending:
                    p.cancel()
                logger.info("Race winner: %s", prov_name)
                return result
            else:
                last_error = result

        # Check cancellation between stagger rounds
        cancelled = await redis.hget(task_key, "cancelled")
        if cancelled == "1":
            for t in pending:
                t.cancel()
            await redis.hset(
                task_key,
                mapping={
                    "status": "cancelled",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            return None

        # If no more fallbacks to launch and nothing pending, break
        if fallback_index >= len(fallback_configs) and not pending:
            break

    # Final wait for any remaining pending tasks
    if pending:
        time_remaining = overall_timeout - (time.monotonic() - race_start)
        if time_remaining > 0:
            done, pending = await asyncio.wait(pending, timeout=time_remaining)
            for task in done:
                prov_name, result = task.result()
                if result.success:
                    for p in pending:
                        p.cancel()
                    return result
                else:
                    last_error = result

        # Cancel any still-pending tasks
        for t in pending:
            t.cancel()

    # All failed or overall timeout
    return last_error or GenerationResult(
        success=False,
        error="All providers failed or timed out",
        provider="none",
    )


async def _save_and_finalize(
    result: GenerationResult,
    original_prompt: str,
    processed_prompt: str | None,
    negative_prompt: str | None,
    settings_dict: dict,
    user_id: str,
    preset_used: str | None,
    template_used: bool,
    was_translated: bool,
    was_enhanced: bool,
    template_name: str | None,
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
        prompt=original_prompt,
        settings={
            "aspect_ratio": settings_dict.get("aspect_ratio", "16:9"),
            "resolution": settings_dict.get("resolution", "1K"),
            "provider": result.provider,
            "model": result.model,
        },
        duration=result.duration,
        mode="basic",
        text_response=result.text_response,
        thinking=result.thinking,
    )

    # Save to PostgreSQL if available
    if is_database_available():
        try:
            async for session in get_session():
                image_repo = ImageRepository(session)
                await image_repo.create(
                    storage_key=storage_obj.key,
                    filename=storage_obj.filename,
                    prompt=original_prompt,
                    mode="basic",
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
                    thinking=result.thinking,
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
                    mode="basic",
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

    response = GenerateImageResponse(
        image=GeneratedImage(
            key=storage_obj.key,
            filename=storage_obj.filename,
            url=storage_obj.public_url,
            width=result.image.width if result.image else None,
            height=result.image.height if result.image else None,
        ),
        prompt=original_prompt,
        thinking=result.thinking,
        text_response=result.text_response,
        duration=result.duration,
        mode=GenerationMode.BASIC,
        settings=gen_settings,
        created_at=datetime.now(),
        provider=result.provider,
        model=result.model,
        model_display_name=model_display_name,
        quality_preset=preset_used,
        processed_prompt=processed_prompt,
        negative_prompt=negative_prompt,
        template_used=template_used,
        was_translated=was_translated,
        was_enhanced=was_enhanced,
        template_name=template_name,
    )

    return response.model_dump(mode="json")


def _get_quota_service(redis):
    """Get quota service instance outside of DI."""
    from .quota_service import get_quota_service

    return get_quota_service(redis)
