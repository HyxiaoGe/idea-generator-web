"""
Trial quota management service using Redis storage.
Manages shared daily quota for trial users without API keys.
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from environment variables."""
    return os.getenv(key, default)


@dataclass
class QuotaConfig:
    """Configuration for quota limits per generation mode."""

    cost: int  # Cost in quota points (1 point = 1 standard 1K/2K image)
    daily_limit: int  # Maximum count per day for this specific mode
    display_name: str  # Display name for UI


# ============ Load Configuration from Environment ============
GLOBAL_DAILY_QUOTA = int(get_config_value("TRIAL_GLOBAL_QUOTA", "50"))
QUOTA_CONFIG_MODE = get_config_value("TRIAL_QUOTA_MODE", "manual")
GENERATION_COOLDOWN = int(get_config_value("TRIAL_COOLDOWN_SECONDS", "3"))

# Base ratios for auto-scaling
BASE_QUOTA_RATIOS = {
    "basic_1k": 0.60,
    "basic_4k": 0.20,
    "chat": 0.40,
    "batch_1k": 0.30,
    "batch_4k": 0.10,
    "search": 0.30,
    "blend": 0.20,
}

# Manual configuration
MANUAL_QUOTA_CONFIGS = {
    "basic_1k": QuotaConfig(
        cost=int(get_config_value("TRIAL_BASIC_1K_COST", "1")),
        daily_limit=int(get_config_value("TRIAL_BASIC_1K_LIMIT", "30")),
        display_name="Basic (1K/2K)",
    ),
    "basic_4k": QuotaConfig(
        cost=int(get_config_value("TRIAL_BASIC_4K_COST", "3")),
        daily_limit=int(get_config_value("TRIAL_BASIC_4K_LIMIT", "10")),
        display_name="Basic (4K)",
    ),
    "chat": QuotaConfig(
        cost=int(get_config_value("TRIAL_CHAT_COST", "1")),
        daily_limit=int(get_config_value("TRIAL_CHAT_LIMIT", "20")),
        display_name="Chat",
    ),
    "batch_1k": QuotaConfig(
        cost=int(get_config_value("TRIAL_BATCH_1K_COST", "1")),
        daily_limit=int(get_config_value("TRIAL_BATCH_1K_LIMIT", "15")),
        display_name="Batch (1K/2K)",
    ),
    "batch_4k": QuotaConfig(
        cost=int(get_config_value("TRIAL_BATCH_4K_COST", "3")),
        daily_limit=int(get_config_value("TRIAL_BATCH_4K_LIMIT", "5")),
        display_name="Batch (4K)",
    ),
    "search": QuotaConfig(
        cost=int(get_config_value("TRIAL_SEARCH_COST", "2")),
        daily_limit=int(get_config_value("TRIAL_SEARCH_LIMIT", "15")),
        display_name="Search",
    ),
    "blend": QuotaConfig(
        cost=int(get_config_value("TRIAL_BLEND_COST", "2")),
        daily_limit=int(get_config_value("TRIAL_BLEND_LIMIT", "10")),
        display_name="Blend/Style",
    ),
}


def _calculate_auto_quota_configs() -> dict[str, QuotaConfig]:
    """Calculate quota configs automatically based on global quota and ratios."""
    configs = {}
    costs = {
        "basic_1k": 1,
        "basic_4k": 3,
        "chat": 1,
        "batch_1k": 1,
        "batch_4k": 3,
        "search": 2,
        "blend": 2,
    }
    display_names = {
        "basic_1k": "Basic (1K/2K)",
        "basic_4k": "Basic (4K)",
        "chat": "Chat",
        "batch_1k": "Batch (1K/2K)",
        "batch_4k": "Batch (4K)",
        "search": "Search",
        "blend": "Blend/Style",
    }

    for mode_key, ratio in BASE_QUOTA_RATIOS.items():
        cost = costs[mode_key]
        allocated_points = GLOBAL_DAILY_QUOTA * ratio
        daily_limit = int(allocated_points / cost)
        configs[mode_key] = QuotaConfig(
            cost=cost, daily_limit=max(1, daily_limit), display_name=display_names[mode_key]
        )
    return configs


# Select configuration based on mode
if QUOTA_CONFIG_MODE == "auto":
    QUOTA_CONFIGS = _calculate_auto_quota_configs()
else:
    QUOTA_CONFIGS = MANUAL_QUOTA_CONFIGS


class QuotaService:
    """
    Service for managing trial user quotas using Redis.

    Redis keys:
    - quota:{date}:global -> int (total points used today)
    - quota:{date}:user:{user_id} -> hash {global_used, mode_usage, last_generation}
    """

    def __init__(self, redis_client=None):
        """
        Initialize the quota service.

        Args:
            redis_client: Async Redis client instance
        """
        self._redis = redis_client
        self._trial_enabled = get_config_value("TRIAL_ENABLED", "false").lower() == "true"

    @property
    def is_trial_enabled(self) -> bool:
        """Check if trial mode is enabled."""
        return self._trial_enabled

    def _get_current_date(self) -> str:
        """Get current date in UTC as string (YYYY-MM-DD)."""
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _get_global_key(self) -> str:
        """Get Redis key for global quota."""
        return f"quota:{self._get_current_date()}:global"

    def _get_user_key(self, user_id: str) -> str:
        """Get Redis key for user quota."""
        return f"quota:{self._get_current_date()}:user:{user_id}"

    def get_mode_key(self, mode: str, resolution: str = "1K") -> str:
        """Get the quota config key for a generation mode."""
        if mode == "basic":
            return "basic_4k" if resolution == "4K" else "basic_1k"
        elif mode == "batch":
            return "batch_4k" if resolution == "4K" else "batch_1k"
        elif mode in ["blend", "style"]:
            return "blend"
        else:
            return mode  # chat, search

    async def check_quota(
        self, user_id: str, mode: str, resolution: str = "1K", count: int = 1
    ) -> tuple[bool, str, dict]:
        """
        Check if quota is available for a generation request.

        Args:
            user_id: User identifier (or "anonymous" for trial users)
            mode: Generation mode
            resolution: Image resolution
            count: Number of images to generate

        Returns:
            Tuple of (can_generate, reason, quota_info)
        """
        if not self._redis:
            return True, "OK", {}  # No Redis = no quota enforcement

        mode_key = self.get_mode_key(mode, resolution)
        config = QUOTA_CONFIGS.get(mode_key)

        if not config:
            return False, "Invalid generation mode", {}

        # Calculate cost
        total_cost = config.cost * count

        # Get user data
        user_key = self._get_user_key(user_id)
        user_data = await self._redis.hgetall(user_key)

        # Check cooldown
        current_time = time.time()
        last_gen = float(user_data.get("last_generation", 0))
        if current_time - last_gen < GENERATION_COOLDOWN:
            remaining = int(GENERATION_COOLDOWN - (current_time - last_gen))
            return (
                False,
                f"Please wait {remaining}s before next generation",
                {"cooldown_remaining": remaining},
            )

        # Check global quota
        global_key = self._get_global_key()
        global_used = int(await self._redis.get(global_key) or 0)
        global_remaining = GLOBAL_DAILY_QUOTA - global_used

        if total_cost > global_remaining:
            return (
                False,
                f"Daily global quota exceeded ({global_used}/{GLOBAL_DAILY_QUOTA} used)",
                {
                    "global_used": global_used,
                    "global_limit": GLOBAL_DAILY_QUOTA,
                    "global_remaining": global_remaining,
                },
            )

        # Check mode-specific quota
        mode_used = int(user_data.get(f"mode:{mode_key}", 0))
        mode_remaining = config.daily_limit - mode_used

        if count > mode_remaining:
            return (
                False,
                f"{config.display_name} daily limit exceeded ({mode_used}/{config.daily_limit} used)",
                {
                    "mode": config.display_name,
                    "mode_used": mode_used,
                    "mode_limit": config.daily_limit,
                    "mode_remaining": mode_remaining,
                },
            )

        # All checks passed
        quota_info = {
            "global_used": global_used,
            "global_limit": GLOBAL_DAILY_QUOTA,
            "global_remaining": global_remaining,
            "mode": config.display_name,
            "mode_used": mode_used,
            "mode_limit": config.daily_limit,
            "mode_remaining": mode_remaining,
            "cost": total_cost,
        }

        return True, "OK", quota_info

    async def consume_quota(
        self, user_id: str, mode: str, resolution: str = "1K", count: int = 1
    ) -> bool:
        """
        Consume quota for a generation.

        Args:
            user_id: User identifier
            mode: Generation mode
            resolution: Image resolution
            count: Number of images generated

        Returns:
            True if quota was consumed successfully
        """
        if not self._redis:
            return True

        mode_key = self.get_mode_key(mode, resolution)
        config = QUOTA_CONFIGS.get(mode_key)

        if not config:
            return False

        total_cost = config.cost * count
        global_key = self._get_global_key()
        user_key = self._get_user_key(user_id)

        # Atomic update with pipeline
        async with self._redis.pipeline() as pipe:
            # Increment global quota
            pipe.incrby(global_key, total_cost)
            # Update user data
            pipe.hincrby(user_key, "global_used", total_cost)
            pipe.hincrby(user_key, f"mode:{mode_key}", count)
            pipe.hset(user_key, "last_generation", str(time.time()))
            # Set TTL (2 days)
            pipe.expire(global_key, 86400 * 2)
            pipe.expire(user_key, 86400 * 2)
            await pipe.execute()

        logger.debug(f"Consumed quota: user={user_id}, mode={mode_key}, cost={total_cost}")
        return True

    async def get_quota_status(self, user_id: str) -> dict:
        """
        Get current quota status for display.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with quota information
        """
        if not self._redis:
            return {"is_trial_mode": False, "message": "Quota tracking not available"}

        global_key = self._get_global_key()
        user_key = self._get_user_key(user_id)

        global_used = int(await self._redis.get(global_key) or 0)
        user_data = await self._redis.hgetall(user_key)

        global_remaining = GLOBAL_DAILY_QUOTA - global_used

        # Build mode status
        mode_status = {}
        for mode_key, config in QUOTA_CONFIGS.items():
            used = int(user_data.get(f"mode:{mode_key}", 0))
            mode_status[mode_key] = {
                "name": config.display_name,
                "used": used,
                "limit": config.daily_limit,
                "remaining": config.daily_limit - used,
                "cost": config.cost,
            }

        # Check cooldown
        current_time = time.time()
        last_gen = float(user_data.get("last_generation", 0))
        cooldown_remaining = max(0, int(GENERATION_COOLDOWN - (current_time - last_gen)))

        return {
            "is_trial_mode": True,
            "date": self._get_current_date(),
            "global_used": global_used,
            "global_limit": GLOBAL_DAILY_QUOTA,
            "global_remaining": global_remaining,
            "modes": mode_status,
            "cooldown_active": cooldown_remaining > 0,
            "cooldown_remaining": cooldown_remaining,
            "resets_at": f"{self._get_current_date()}T00:00:00Z",
        }

    async def reset_user_quota(self, user_id: str) -> bool:
        """
        Reset quota for a specific user (admin function).

        Args:
            user_id: User identifier

        Returns:
            True if reset successful
        """
        if not self._redis:
            return False

        user_key = self._get_user_key(user_id)
        await self._redis.delete(user_key)
        logger.info(f"Reset quota for user: {user_id}")
        return True


# Singleton instance
_quota_service: QuotaService | None = None


def get_quota_service(redis_client=None) -> QuotaService:
    """Get or create the quota service instance."""
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService(redis_client=redis_client)
    elif redis_client and _quota_service._redis is None:
        _quota_service._redis = redis_client
    return _quota_service


def is_trial_mode(user_api_key: str | None = None) -> bool:
    """
    Check if current user is in trial mode.

    Args:
        user_api_key: User's API key (if any)

    Returns:
        True if user is using trial mode
    """
    force_trial = get_config_value("FORCE_TRIAL_MODE", "false").lower() == "true"
    if force_trial:
        return True

    env_api_key = get_config_value("GOOGLE_API_KEY", "")
    return not (user_api_key or env_api_key)
