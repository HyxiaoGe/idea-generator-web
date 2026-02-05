"""
Quota repository for quota usage tracking.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import QuotaUsage


class QuotaRepository:
    """Repository for QuotaUsage model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_usage(
        self,
        mode: str,
        points_used: int,
        user_id: UUID | None = None,
        image_id: UUID | None = None,
    ) -> QuotaUsage:
        """Record a quota usage event."""
        usage = QuotaUsage(
            user_id=user_id,
            mode=mode,
            points_used=points_used,
            image_id=image_id,
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def get_daily_usage(
        self,
        user_id: UUID | None,
        date: datetime | None = None,
    ) -> int:
        """Get total points used on a specific date."""
        if date is None:
            date = datetime.now()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        query = select(func.coalesce(func.sum(QuotaUsage.points_used), 0))
        query = query.where(
            and_(
                QuotaUsage.user_id == user_id,
                QuotaUsage.created_at >= start_of_day,
                QuotaUsage.created_at < end_of_day,
            )
        )

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_usage_by_mode(
        self,
        user_id: UUID | None,
        mode: str,
        date: datetime | None = None,
    ) -> int:
        """Get usage count for a specific mode on a date."""
        if date is None:
            date = datetime.now()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        query = select(func.count()).select_from(QuotaUsage)
        query = query.where(
            and_(
                QuotaUsage.user_id == user_id,
                QuotaUsage.mode == mode,
                QuotaUsage.created_at >= start_of_day,
                QuotaUsage.created_at < end_of_day,
            )
        )

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_daily_stats(
        self,
        user_id: UUID | None,
        date: datetime | None = None,
    ) -> dict:
        """
        Get daily usage statistics.

        Returns:
            Dict with total_points, request_count, and usage_by_mode
        """
        if date is None:
            date = datetime.now()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Get totals
        total_query = select(
            func.coalesce(func.sum(QuotaUsage.points_used), 0).label("total_points"),
            func.count().label("request_count"),
        ).where(
            and_(
                QuotaUsage.user_id == user_id,
                QuotaUsage.created_at >= start_of_day,
                QuotaUsage.created_at < end_of_day,
            )
        )
        total_result = await self.session.execute(total_query)
        total_row = total_result.first()

        # Get by mode
        mode_query = (
            select(
                QuotaUsage.mode,
                func.sum(QuotaUsage.points_used).label("points"),
                func.count().label("count"),
            )
            .where(
                and_(
                    QuotaUsage.user_id == user_id,
                    QuotaUsage.created_at >= start_of_day,
                    QuotaUsage.created_at < end_of_day,
                )
            )
            .group_by(QuotaUsage.mode)
        )

        mode_result = await self.session.execute(mode_query)
        usage_by_mode = {
            row.mode: {"points": row.points, "count": row.count} for row in mode_result
        }

        return {
            "date": start_of_day.date().isoformat(),
            "total_points": total_row.total_points,
            "request_count": total_row.request_count,
            "usage_by_mode": usage_by_mode,
        }

    async def get_usage_history(
        self,
        user_id: UUID | None,
        days: int = 7,
    ) -> list[dict]:
        """Get daily usage history for past N days."""
        history = []
        today = datetime.now()

        for i in range(days):
            date = today - timedelta(days=i)
            stats = await self.get_daily_stats(user_id, date)
            history.append(stats)

        return history
