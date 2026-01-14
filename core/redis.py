"""
Redis connection management.

Provides async Redis client with connection pooling.
"""

import logging
from typing import Optional
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis, ConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None


async def init_redis() -> Redis:
    """
    Initialize Redis connection pool and client.

    Should be called during application startup.
    """
    global _pool, _client

    settings = get_settings()

    _pool = ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )

    _client = Redis(connection_pool=_pool)

    # Test connection
    try:
        await _client.ping()
        logger.info("Redis connection established successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    return _client


async def close_redis() -> None:
    """
    Close Redis connection pool.

    Should be called during application shutdown.
    """
    global _pool, _client

    if _client:
        await _client.close()
        _client = None
        logger.info("Redis connection closed")

    if _pool:
        await _pool.disconnect()
        _pool = None


async def get_redis() -> Redis:
    """
    Get Redis client instance.

    Returns:
        Redis client instance

    Raises:
        RuntimeError: If Redis is not initialized
    """
    if _client is None:
        raise RuntimeError("Redis is not initialized. Call init_redis() first.")
    return _client


@asynccontextmanager
async def redis_connection():
    """
    Context manager for Redis connection.

    Useful for scripts or testing where you need a standalone connection.

    Usage:
        async with redis_connection() as redis:
            await redis.set("key", "value")
    """
    settings = get_settings()
    client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    try:
        yield client
    finally:
        await client.close()


class RedisHealthCheck:
    """Redis health check utility."""

    @staticmethod
    async def check() -> dict:
        """
        Check Redis health status.

        Returns:
            Dictionary with health status and latency
        """
        import time

        try:
            client = await get_redis()
            start = time.perf_counter()
            await client.ping()
            latency_ms = (time.perf_counter() - start) * 1000

            # Get some basic info
            info = await client.info("server")

            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "version": info.get("redis_version", "unknown"),
            }
        except RuntimeError:
            return {
                "status": "not_initialized",
                "latency_ms": None,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "latency_ms": None,
            }
