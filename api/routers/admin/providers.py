"""
Admin provider management router.

Endpoints:
- GET /api/admin/providers - List providers
- PUT /api/admin/providers/{name} - Update provider config
- POST /api/admin/providers/{name}/enable - Enable provider
- POST /api/admin/providers/{name}/disable - Disable provider
- GET /api/admin/providers/{name}/health - Get provider health
- POST /api/admin/providers/circuit-breakers/reset - Reset circuit breakers
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.routers.auth import require_current_user
from api.schemas.admin import (
    AdminProviderInfo,
    ListProvidersResponse,
    ProviderActionResponse,
    ProviderStatus,
    ResetCircuitBreakersResponse,
    UpdateProviderRequest,
)
from services import MediaType, get_provider_router
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["admin-providers"])


# ============ Admin Check ============


async def require_admin(user: GitHubUser = Depends(require_current_user)) -> GitHubUser:
    """Require admin privileges."""
    return user


# ============ Endpoints ============


@router.get("", response_model=ListProvidersResponse)
async def list_providers(
    admin: GitHubUser = Depends(require_admin),
):
    """List all providers with their status."""
    provider_router = get_provider_router()

    providers = []

    # Get image providers
    for name, status in provider_router.list_available_providers(MediaType.IMAGE):
        providers.append(
            AdminProviderInfo(
                name=name,
                status=ProviderStatus.ENABLED if status else ProviderStatus.DISABLED,
                priority=100,  # TODO: get actual priority
                enabled=status,
                supports_image=True,
                supports_video=False,
                health_score=100.0 if status else 0.0,
                total_requests_24h=0,
                success_rate_24h=100.0,
                avg_latency_ms=0.0,
                circuit_breaker_state=None,
                last_error=None,
                last_error_at=None,
            )
        )

    # Get video providers
    for name, status in provider_router.list_available_providers(MediaType.VIDEO):
        # Check if already in list (some providers support both)
        existing = next((p for p in providers if p.name == name), None)
        if existing:
            existing.supports_video = True
        else:
            providers.append(
                AdminProviderInfo(
                    name=name,
                    status=ProviderStatus.ENABLED if status else ProviderStatus.DISABLED,
                    priority=100,
                    enabled=status,
                    supports_image=False,
                    supports_video=True,
                    health_score=100.0 if status else 0.0,
                    total_requests_24h=0,
                    success_rate_24h=100.0,
                    avg_latency_ms=0.0,
                    circuit_breaker_state=None,
                    last_error=None,
                    last_error_at=None,
                )
            )

    return ListProvidersResponse(providers=providers)


@router.put("/{provider_name}", response_model=ProviderActionResponse)
async def update_provider(
    provider_name: str,
    request: UpdateProviderRequest,
    admin: GitHubUser = Depends(require_admin),
):
    """Update provider configuration."""
    # TODO: Implement provider config update
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{provider_name}/enable", response_model=ProviderActionResponse)
async def enable_provider(
    provider_name: str,
    admin: GitHubUser = Depends(require_admin),
):
    """Enable a provider."""
    # TODO: Implement provider enabling
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{provider_name}/disable", response_model=ProviderActionResponse)
async def disable_provider(
    provider_name: str,
    admin: GitHubUser = Depends(require_admin),
):
    """Disable a provider."""
    # TODO: Implement provider disabling
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{provider_name}/health")
async def get_provider_health(
    provider_name: str,
    admin: GitHubUser = Depends(require_admin),
):
    """Get detailed health information for a provider."""
    provider_router = get_provider_router()

    health = await provider_router.check_provider_health(provider_name)
    if health is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    return {
        "provider": provider_name,
        "healthy": health,
        "details": {},  # TODO: Add detailed health info
    }


@router.post("/circuit-breakers/reset", response_model=ResetCircuitBreakersResponse)
async def reset_circuit_breakers(
    admin: GitHubUser = Depends(require_admin),
):
    """Reset all circuit breakers."""
    # TODO: Implement circuit breaker reset
    return ResetCircuitBreakersResponse(
        success=True,
        reset_count=0,
    )
