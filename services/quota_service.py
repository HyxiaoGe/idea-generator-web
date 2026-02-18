"""
Simple per-user daily quota service using Redis.

Tracks usage count per user per day with cooldown for abuse prevention.

Redis keys:
- usage:{user_id}:{YYYY-MM-DD}  → int (generation count today)
- usage:{user_id}:last_gen      → float (timestamp of last generation)
"""

import logging
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# ============ Configuration ============

DAILY_LIMIT = 50  # Max generations per user per day
COOLDOWN_SECONDS = 3  # Min seconds between generations
MAX_BATCH_SIZE = 5  # Max images per batch request


class QuotaService:
    """
    Simple per-user daily quota with cooldown.

    Each generation (image, video, chat) costs 1 point.
    Batch generation costs N points (one per image).
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _usage_key(self, user_id: str) -> str:
        return f"usage:{user_id}:{self._today()}"

    @staticmethod
    def _cooldown_key(user_id: str) -> str:
        return f"usage:{user_id}:last_gen"

    async def check_quota(
        self,
        user_id: str,
        count: int = 1,
    ) -> tuple[bool, str, dict]:
        """
        Check if user can generate.

        Args:
            user_id: User identifier
            count: Number of generations (batch size)

        Returns:
            Tuple of (allowed, reason, info)
        """
        if not self._redis:
            return True, "OK", {}

        # Check batch size
        if count > MAX_BATCH_SIZE:
            return (
                False,
                f"Batch size exceeds limit ({count}/{MAX_BATCH_SIZE})",
                {"max_batch_size": MAX_BATCH_SIZE},
            )

        # Check cooldown
        cooldown_key = self._cooldown_key(user_id)
        last_gen = await self._redis.hget(cooldown_key, "ts")
        if last_gen:
            elapsed = time.time() - float(last_gen)
            if elapsed < COOLDOWN_SECONDS:
                remaining = int(COOLDOWN_SECONDS - elapsed) + 1
                return (
                    False,
                    f"Please wait {remaining}s before next generation",
                    {"cooldown_remaining": remaining},
                )

        # Check daily limit
        usage_key = self._usage_key(user_id)
        used = int(await self._redis.get(usage_key) or 0)
        remaining = DAILY_LIMIT - used

        if count > remaining:
            return (
                False,
                f"Daily limit reached ({used}/{DAILY_LIMIT})",
                {
                    "used": used,
                    "limit": DAILY_LIMIT,
                    "remaining": remaining,
                },
            )

        return (
            True,
            "OK",
            {
                "used": used,
                "limit": DAILY_LIMIT,
                "remaining": remaining,
                "cost": count,
            },
        )

    async def consume_quota(
        self,
        user_id: str,
        count: int = 1,
    ) -> bool:
        """
        Record a generation against the user's daily limit.

        Args:
            user_id: User identifier
            count: Number of generations

        Returns:
            True if recorded successfully
        """
        if not self._redis:
            return True

        usage_key = self._usage_key(user_id)
        cooldown_key = self._cooldown_key(user_id)

        async with self._redis.pipeline() as pipe:
            pipe.incrby(usage_key, count)
            pipe.expire(usage_key, 86400 * 2)  # 48h TTL
            pipe.hset(cooldown_key, "ts", str(time.time()))
            pipe.expire(cooldown_key, COOLDOWN_SECONDS + 10)
            await pipe.execute()

        logger.debug(f"Quota consumed: user={user_id}, count={count}")
        return True

    async def refund_quota(self, user_id: str, count: int = 1) -> int:
        """
        Refund quota points (e.g. when a task is cancelled).

        Args:
            user_id: User identifier
            count: Number of points to refund

        Returns:
            Actual number of points refunded (capped at current usage to avoid going negative)
        """
        if not self._redis or count <= 0:
            return 0

        usage_key = self._usage_key(user_id)
        current_usage = int(await self._redis.get(usage_key) or 0)

        # Cap refund at current usage to avoid going negative
        actual_refund = min(count, current_usage)
        if actual_refund <= 0:
            return 0

        await self._redis.incrby(usage_key, -actual_refund)
        logger.info(f"Quota refunded: user={user_id}, refunded={actual_refund}")
        return actual_refund

    async def get_quota_status(self, user_id: str) -> dict:
        """
        Get current quota status for display.

        Returns:
            Dict with used/limit/remaining and cooldown info
        """
        if not self._redis:
            return {"message": "Quota tracking not available"}

        usage_key = self._usage_key(user_id)
        used = int(await self._redis.get(usage_key) or 0)
        remaining = max(0, DAILY_LIMIT - used)

        # Check cooldown
        cooldown_remaining = 0
        cooldown_key = self._cooldown_key(user_id)
        last_gen_str = await self._redis.hget(cooldown_key, "ts")
        if last_gen_str:
            elapsed = time.time() - float(last_gen_str)
            cooldown_remaining = max(0, int(COOLDOWN_SECONDS - elapsed))

        return {
            "date": self._today(),
            "used": used,
            "limit": DAILY_LIMIT,
            "remaining": remaining,
            "cooldown_active": cooldown_remaining > 0,
            "cooldown_remaining": cooldown_remaining,
            "resets_at": f"{self._today()}T00:00:00Z",
        }

    async def reset_user_quota(self, user_id: str) -> bool:
        """Reset quota for a specific user (admin function)."""
        if not self._redis:
            return False

        usage_key = self._usage_key(user_id)
        await self._redis.delete(usage_key)
        logger.info(f"Reset quota for user: {user_id}")
        return True


# Singleton
_quota_service: QuotaService | None = None


def get_quota_service(redis_client=None) -> QuotaService:
    """Get or create the quota service instance."""
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService(redis_client=redis_client)
    elif redis_client and _quota_service._redis is None:
        _quota_service._redis = redis_client
    return _quota_service
