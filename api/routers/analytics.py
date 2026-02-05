"""
Analytics router for usage statistics and trends.

Endpoints:
- GET /api/analytics/overview - Overall statistics
- GET /api/analytics/usage - Usage statistics
- GET /api/analytics/costs - Cost analysis
- GET /api/analytics/providers - Provider statistics
- GET /api/analytics/trends - Trend analysis
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_image_repository, get_user_repository
from api.routers.auth import require_current_user
from api.schemas.analytics import (
    CostsResponse,
    ModeUsage,
    OverviewResponse,
    ProvidersResponse,
    TimeRange,
    Trend,
    TrendsResponse,
    UsageResponse,
)
from database.repositories import ImageRepository, UserRepository
from services.auth_service import GitHubUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ============ Helpers ============


async def get_db_user_id(
    user: GitHubUser,
    user_repo: UserRepository | None,
) -> UUID | None:
    """Get database user ID from GitHub user."""
    if not user_repo:
        return None

    db_user = await user_repo.get_by_github_id(int(user.id))
    return db_user.id if db_user else None


def get_date_range(time_range: TimeRange) -> tuple[datetime | None, datetime | None]:
    """Get start and end dates for a time range."""
    now = datetime.now()
    end = now

    if time_range == TimeRange.TODAY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif time_range == TimeRange.WEEK:
        start = now - timedelta(days=7)
    elif time_range == TimeRange.MONTH:
        start = now - timedelta(days=30)
    elif time_range == TimeRange.QUARTER:
        start = now - timedelta(days=90)
    elif time_range == TimeRange.YEAR:
        start = now - timedelta(days=365)
    else:  # ALL
        start = None
        end = None

    return start, end


# ============ Endpoints ============


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    time_range: TimeRange = Query(default=TimeRange.MONTH),
    user: GitHubUser = Depends(require_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Get overall analytics overview.

    Includes total generations, credits used, success rate, etc.
    """
    if not image_repo:
        return OverviewResponse(
            total_generations=0,
            total_credits_used=0.0,
            average_duration_ms=0.0,
            success_rate=100.0,
            favorite_provider=None,
            favorite_mode=None,
            period_start=None,
            period_end=None,
        )

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        return OverviewResponse(
            total_generations=0,
            total_credits_used=0.0,
            average_duration_ms=0.0,
            success_rate=100.0,
            favorite_provider=None,
            favorite_mode=None,
            period_start=None,
            period_end=None,
        )

    # Get statistics
    stats = await image_repo.get_stats_by_user(user_id)

    # Find favorite provider and mode
    favorite_provider = None
    favorite_mode = None
    if stats.get("images_by_mode"):
        favorite_mode = max(stats["images_by_mode"], key=stats["images_by_mode"].get)

    start, end = get_date_range(time_range)

    return OverviewResponse(
        total_generations=stats.get("total_images", 0),
        total_credits_used=0.0,  # TODO: implement cost tracking
        average_duration_ms=stats.get("average_duration", 0) * 1000,
        success_rate=100.0,  # TODO: track failures
        favorite_provider=favorite_provider,
        favorite_mode=favorite_mode,
        period_start=start,
        period_end=end,
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    time_range: TimeRange = Query(default=TimeRange.MONTH),
    user: GitHubUser = Depends(require_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Get detailed usage statistics.

    Includes daily breakdown, usage by mode and resolution.
    """
    if not image_repo:
        return UsageResponse(
            daily_usage=[],
            total_generations=0,
            average_daily=0.0,
            peak_day=None,
            peak_count=0,
            by_mode=[],
            by_resolution=[],
        )

    user_id = await get_db_user_id(user, user_repo)
    if not user_id:
        return UsageResponse(
            daily_usage=[],
            total_generations=0,
            average_daily=0.0,
            peak_day=None,
            peak_count=0,
            by_mode=[],
            by_resolution=[],
        )

    stats = await image_repo.get_stats_by_user(user_id)
    total = stats.get("total_images", 0)

    # Build mode breakdown
    by_mode = []
    for mode, count in stats.get("images_by_mode", {}).items():
        by_mode.append(
            ModeUsage(
                mode=mode,
                count=count,
                percentage=round(count / total * 100, 1) if total > 0 else 0,
            )
        )

    # TODO: Implement daily breakdown and resolution stats
    # This requires additional repository methods

    return UsageResponse(
        daily_usage=[],
        total_generations=total,
        average_daily=total / 30.0,  # Rough estimate
        peak_day=None,
        peak_count=0,
        by_mode=by_mode,
        by_resolution=[],
    )


@router.get("/costs", response_model=CostsResponse)
async def get_costs(
    time_range: TimeRange = Query(default=TimeRange.MONTH),
    user: GitHubUser = Depends(require_current_user),
):
    """
    Get cost analysis.

    Note: Cost tracking not yet implemented.
    """
    return CostsResponse(
        total_cost=0.0,
        currency="credits",
        daily_costs=[],
        by_provider=[],
        by_mode=[],
        by_resolution=[],
    )


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers_analytics(
    time_range: TimeRange = Query(default=TimeRange.MONTH),
    user: GitHubUser = Depends(require_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Get provider usage statistics.

    Shows usage, success rate, and latency by provider.
    """
    if not image_repo:
        return ProvidersResponse(
            providers=[],
            total_requests=0,
            fallback_count=0,
            fallback_rate=0.0,
        )

    await get_db_user_id(user, user_repo)

    # TODO: Implement provider statistics
    # This requires tracking provider usage per image

    return ProvidersResponse(
        providers=[],
        total_requests=0,
        fallback_count=0,
        fallback_rate=0.0,
    )


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    time_range: TimeRange = Query(default=TimeRange.MONTH),
    user: GitHubUser = Depends(require_current_user),
    image_repo: ImageRepository | None = Depends(get_image_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Get trend analysis.

    Analyzes usage patterns and provides insights.
    """
    # TODO: Implement trend analysis
    usage_trend = Trend(
        metric="usage",
        direction="stable",
        change_percentage=0.0,
        data_points=[],
    )

    return TrendsResponse(
        usage_trend=usage_trend,
        cost_trend=None,
        quality_trend=None,
        insights=[],
    )
