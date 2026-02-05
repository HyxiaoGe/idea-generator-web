"""
Audit repository for audit logs and provider health tracking.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog, ProviderHealthLog


class AuditRepository:
    """Repository for AuditLog and ProviderHealthLog model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Audit Log Operations ============

    async def create_audit_log(
        self,
        action: str,
        user_id: UUID | None = None,
        endpoint: str | None = None,
        method: str | None = None,
        prompt: str | None = None,
        filter_result: str | None = None,
        blocked_reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        image_id: UUID | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        log = AuditLog(
            action=action,
            user_id=user_id,
            endpoint=endpoint,
            method=method,
            prompt=prompt,
            filter_result=filter_result,
            blocked_reason=blocked_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            image_id=image_id,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_audit_logs(
        self,
        user_id: UUID | None = None,
        action: str | None = None,
        filter_result: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """List audit logs with filtering."""
        query = select(AuditLog)

        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if filter_result:
            query = query.where(AuditLog.filter_result == filter_result)

        query = query.order_by(desc(AuditLog.created_at))
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_blocked(
        self,
        since: datetime | None = None,
    ) -> int:
        """Count blocked requests."""
        query = select(func.count()).select_from(AuditLog)
        query = query.where(AuditLog.filter_result == "blocked")

        if since:
            query = query.where(AuditLog.created_at >= since)

        result = await self.session.execute(query)
        return result.scalar_one()

    # ============ Provider Health Operations ============

    async def log_provider_request(
        self,
        provider: str,
        success: bool,
        model: str | None = None,
        latency_ms: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> ProviderHealthLog:
        """Log a provider request result."""
        log = ProviderHealthLog(
            provider=provider,
            model=model,
            success=success,
            latency_ms=latency_ms,
            error_type=error_type,
            error_message=error_message,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_provider_stats(
        self,
        provider: str,
        hours: int = 24,
    ) -> dict:
        """
        Get provider health statistics for the past N hours.

        Returns:
            Dict with total_requests, successful, success_rate, avg_latency_ms
        """
        since = datetime.now() - timedelta(hours=hours)

        query = select(
            func.count().label("total"),
            func.sum(func.cast(ProviderHealthLog.success, type_=func.text)).label("successful"),
            func.avg(
                func.nullif(
                    func.cast(ProviderHealthLog.success, type_=func.text)
                    * ProviderHealthLog.latency_ms,
                    0,
                )
            ).label("avg_latency"),
        ).where(
            and_(
                ProviderHealthLog.provider == provider,
                ProviderHealthLog.created_at >= since,
            )
        )

        result = await self.session.execute(query)
        row = result.first()

        total = row.total or 0
        successful = int(row.successful or 0)
        avg_latency = row.avg_latency

        return {
            "provider": provider,
            "period_hours": hours,
            "total_requests": total,
            "successful": successful,
            "success_rate": round(successful / total * 100, 2) if total > 0 else 0,
            "avg_latency_ms": round(avg_latency) if avg_latency else None,
        }

    async def get_all_provider_stats(
        self,
        hours: int = 24,
    ) -> list[dict]:
        """Get health statistics for all providers."""
        since = datetime.now() - timedelta(hours=hours)

        # Get unique providers
        providers_query = (
            select(ProviderHealthLog.provider)
            .where(ProviderHealthLog.created_at >= since)
            .distinct()
        )
        providers_result = await self.session.execute(providers_query)
        providers = [row[0] for row in providers_result]

        # Get stats for each
        stats = []
        for provider in providers:
            provider_stats = await self.get_provider_stats(provider, hours)
            stats.append(provider_stats)

        # Sort by success rate descending
        stats.sort(key=lambda x: x["success_rate"], reverse=True)
        return stats

    async def get_recent_errors(
        self,
        provider: str | None = None,
        limit: int = 10,
    ) -> list[ProviderHealthLog]:
        """Get recent provider errors."""
        query = select(ProviderHealthLog).where(ProviderHealthLog.success.is_(False))

        if provider:
            query = query.where(ProviderHealthLog.provider == provider)

        query = query.order_by(desc(ProviderHealthLog.created_at))
        query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())
