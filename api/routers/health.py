"""
Health check endpoints.

Provides basic and detailed health check functionality.
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from api.schemas.common import (
    HealthStatus,
    HealthCheckResponse,
    DetailedHealthCheckResponse,
    ComponentHealth,
)
from core.config import get_settings, Settings
from core.redis import RedisHealthCheck

router = APIRouter(prefix="/health", tags=["health"])

# Track application start time for uptime calculation
_start_time = time.time()


@router.get(
    "",
    response_model=HealthCheckResponse,
    summary="Basic health check",
    description="Quick health check endpoint for load balancers and container orchestration.",
)
async def health_check() -> HealthCheckResponse:
    """
    Basic health check.

    Returns a simple healthy status if the API is running.
    Used by load balancers and container health checks.
    """
    return HealthCheckResponse(
        status=HealthStatus.HEALTHY,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/detailed",
    response_model=DetailedHealthCheckResponse,
    summary="Detailed health check",
    description="Comprehensive health check with status of all components.",
)
async def detailed_health_check(
    settings: Settings = Depends(get_settings),
) -> DetailedHealthCheckResponse:
    """
    Detailed health check with component status.

    Checks the health of:
    - Redis connection
    - R2 storage (if configured)
    - Gemini API (if API key configured)
    """
    components = {}
    overall_status = HealthStatus.HEALTHY

    # Check Redis
    redis_health = await RedisHealthCheck.check()
    components["redis"] = ComponentHealth(
        status=HealthStatus.HEALTHY if redis_health["status"] == "healthy" else HealthStatus.UNHEALTHY,
        latency_ms=redis_health.get("latency_ms"),
        error=redis_health.get("error"),
        details={"version": redis_health.get("version")} if redis_health.get("version") else None,
    )
    if redis_health["status"] != "healthy":
        overall_status = HealthStatus.UNHEALTHY

    # Check R2 Storage configuration
    if settings.is_r2_configured:
        components["r2_storage"] = ComponentHealth(
            status=HealthStatus.HEALTHY,
            details={"bucket": settings.r2_bucket_name},
        )
    else:
        components["r2_storage"] = ComponentHealth(
            status=HealthStatus.DEGRADED,
            error="R2 storage not configured",
        )
        if overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

    # Check Gemini API configuration
    if settings.google_api_key:
        components["gemini_api"] = ComponentHealth(
            status=HealthStatus.HEALTHY,
            details={"configured": True},
        )
    else:
        components["gemini_api"] = ComponentHealth(
            status=HealthStatus.DEGRADED,
            error="No default API key configured (users must provide their own)",
        )

    # Calculate uptime
    uptime_seconds = time.time() - _start_time

    return DetailedHealthCheckResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=round(uptime_seconds, 2),
        components=components,
    )


@router.get(
    "/ready",
    response_model=HealthCheckResponse,
    summary="Readiness check",
    description="Check if the application is ready to accept traffic.",
)
async def readiness_check() -> HealthCheckResponse:
    """
    Readiness check for Kubernetes.

    Verifies that Redis is connected and the app is ready to serve requests.
    """
    redis_health = await RedisHealthCheck.check()

    if redis_health["status"] == "healthy":
        return HealthCheckResponse(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(timezone.utc),
        )
    else:
        return HealthCheckResponse(
            status=HealthStatus.UNHEALTHY,
            timestamp=datetime.now(timezone.utc),
        )


@router.get(
    "/live",
    response_model=HealthCheckResponse,
    summary="Liveness check",
    description="Check if the application is alive.",
)
async def liveness_check() -> HealthCheckResponse:
    """
    Liveness check for Kubernetes.

    Simple check that the application process is running.
    """
    return HealthCheckResponse(
        status=HealthStatus.HEALTHY,
        timestamp=datetime.now(timezone.utc),
    )
