"""
Cost tracking for generation across providers.
"""

import asyncio
import time
from typing import Any

from .types import CostRecord, MediaType


class CostTracker:
    """Track generation costs across providers."""

    def __init__(self, budget_limit: float | None = None):
        self.budget_limit = budget_limit
        self.records: list[CostRecord] = []
        self._lock = asyncio.Lock()

    async def record(
        self,
        provider: str,
        model: str,
        cost: float,
        media_type: MediaType,
        resolution: str | None = None,
        duration: int | None = None,
    ) -> None:
        """Record a generation cost."""
        async with self._lock:
            self.records.append(
                CostRecord(
                    provider=provider,
                    model=model,
                    cost=cost,
                    timestamp=time.time(),
                    media_type=media_type,
                    resolution=resolution,
                    duration=duration,
                )
            )
            # Keep only last 10000 records
            if len(self.records) > 10000:
                self.records = self.records[-10000:]

    def get_total_cost(self, since: float = 0) -> float:
        """Get total cost since a timestamp."""
        return sum(r.cost for r in self.records if r.timestamp >= since)

    def get_cost_by_provider(self, since: float = 0) -> dict[str, float]:
        """Get costs grouped by provider."""
        costs: dict[str, float] = {}
        for r in self.records:
            if r.timestamp >= since:
                costs[r.provider] = costs.get(r.provider, 0) + r.cost
        return costs

    def get_cost_by_media_type(self, since: float = 0) -> dict[str, float]:
        """Get costs grouped by media type."""
        costs: dict[str, float] = {}
        for r in self.records:
            if r.timestamp >= since:
                key = r.media_type.value
                costs[key] = costs.get(key, 0) + r.cost
        return costs

    def is_within_budget(self, additional_cost: float = 0) -> bool:
        """Check if within budget limit."""
        if self.budget_limit is None:
            return True
        return self.get_total_cost() + additional_cost <= self.budget_limit

    def get_summary(self, since: float = 0) -> dict[str, Any]:
        """Get a summary of costs."""
        return {
            "total_cost": self.get_total_cost(since),
            "by_provider": self.get_cost_by_provider(since),
            "by_media_type": self.get_cost_by_media_type(since),
            "budget_limit": self.budget_limit,
            "within_budget": self.is_within_budget(),
            "record_count": len([r for r in self.records if r.timestamp >= since]),
        }
