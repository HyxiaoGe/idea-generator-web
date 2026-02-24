"""Provider management endpoints."""

from fastapi import APIRouter

from core.config import get_settings
from services import (
    MediaType,
    get_provider_router,
)

router = APIRouter()


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
