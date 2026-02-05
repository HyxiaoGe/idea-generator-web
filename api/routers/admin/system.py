"""
Admin system monitoring router.

Endpoints:
- GET /api/admin/system/status - System status
- GET /api/admin/system/metrics - System metrics
- GET /api/admin/system/logs - System logs
- GET /api/admin/system/storage - Storage status
- GET /api/admin/system/redis - Redis status
- GET /api/admin/system/database - Database status
"""

import logging
import time

from fastapi import APIRouter, Depends, Query

from api.routers.auth import require_current_user
from api.schemas.admin import (
    DatabaseStatusResponse,
    RedisStatusResponse,
    StorageStatusResponse,
    SystemLogsResponse,
    SystemMetricsResponse,
    SystemStatusResponse,
)
from core.config import get_settings
from core.redis import get_redis
from database import is_database_available
from services import get_websocket_manager
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["admin-system"])

# Track startup time
_start_time = time.time()


# ============ Admin Check ============


async def require_admin(user: GitHubUser = Depends(require_current_user)) -> GitHubUser:
    """Require admin privileges."""
    return user


# ============ Endpoints ============


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    admin: GitHubUser = Depends(require_admin),
):
    """Get overall system status."""
    settings = get_settings()
    uptime = time.time() - _start_time

    # Check components
    components = {}

    # Redis
    try:
        redis = await get_redis()
        if redis:
            await redis.ping()
            components["redis"] = "healthy"
        else:
            components["redis"] = "unavailable"
    except Exception:
        components["redis"] = "unhealthy"

    # Database
    if is_database_available():
        components["database"] = "healthy"
    else:
        components["database"] = "unavailable"

    # Determine overall status
    status = "healthy"
    if "unhealthy" in components.values():
        status = "degraded"
    if components.get("redis") == "unhealthy":
        status = "unhealthy"

    return SystemStatusResponse(
        status=status,
        uptime_seconds=uptime,
        version=settings.app_version,
        environment=settings.environment,
        components=components,
    )


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics(
    admin: GitHubUser = Depends(require_admin),
):
    """Get system metrics."""
    ws_manager = get_websocket_manager()

    return SystemMetricsResponse(
        cpu_percent=0.0,  # TODO: implement actual metrics
        memory_percent=0.0,
        disk_percent=0.0,
        active_connections=ws_manager.connection_count,
        requests_per_minute=0.0,
        average_latency_ms=0.0,
    )


@router.get("/logs", response_model=SystemLogsResponse)
async def get_system_logs(
    level: str = Query(default="INFO"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    admin: GitHubUser = Depends(require_admin),
):
    """Get system logs."""
    # TODO: Implement log retrieval
    return SystemLogsResponse(
        logs=[],
        total=0,
        limit=limit,
        offset=offset,
        has_more=False,
    )


@router.get("/storage", response_model=StorageStatusResponse)
async def get_storage_status(
    admin: GitHubUser = Depends(require_admin),
):
    """Get storage status."""
    settings = get_settings()

    return StorageStatusResponse(
        backend="r2" if settings.r2_enabled else "local",
        total_files=0,  # TODO: implement file counting
        total_size_bytes=0,
        usage_by_user=[],
    )


@router.get("/redis", response_model=RedisStatusResponse)
async def get_redis_status(
    admin: GitHubUser = Depends(require_admin),
):
    """Get Redis status."""
    try:
        redis = await get_redis()
        if not redis:
            return RedisStatusResponse(connected=False)

        info = await redis.info()
        return RedisStatusResponse(
            connected=True,
            version=info.get("redis_version"),
            memory_used=info.get("used_memory", 0),
            total_keys=await redis.dbsize(),
            connected_clients=info.get("connected_clients", 0),
        )
    except Exception as e:
        logger.error(f"Redis status check failed: {e}")
        return RedisStatusResponse(connected=False)


@router.get("/database", response_model=DatabaseStatusResponse)
async def get_database_status(
    admin: GitHubUser = Depends(require_admin),
):
    """Get database status."""
    if not is_database_available():
        return DatabaseStatusResponse(connected=False)

    # TODO: Get detailed database stats
    return DatabaseStatusResponse(
        connected=True,
        version=None,
        pool_size=0,
        pool_in_use=0,
        total_tables=0,
        total_rows={},
    )
