"""
ARQ background worker for Nano Banana Lab.

Run with:
    arq api.workers.WorkerSettings

Tasks:
    - generate_template_previews: Generate missing preview images for templates.
      Runs as a daily cron (03:00) and can be triggered manually via the admin API.
"""

import logging
from urllib.parse import urlparse

from arq import cron
from arq.connections import RedisSettings

from core.config import get_settings
from database import close_database, get_session, init_database
from services.preview_generator import PreviewGenerator

logger = logging.getLogger(__name__)

# Configure logging for the worker process
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


# ── Lifecycle hooks ──────────────────────────────────────────────────────────


async def startup(ctx: dict) -> None:
    """Initialise DB, storage, and Google provider for the worker."""
    logger.info("ARQ worker starting up...")

    await init_database()
    logger.info("Database initialized")

    # Pre-create the preview generator so it's reused across invocations
    ctx["preview_generator"] = PreviewGenerator()
    logger.info("PreviewGenerator ready")


async def shutdown(ctx: dict) -> None:
    """Clean up resources on worker shutdown."""
    logger.info("ARQ worker shutting down...")
    await close_database()
    logger.info("Database connection closed")


# ── Tasks ────────────────────────────────────────────────────────────────────


async def generate_template_previews(
    ctx: dict,
    delay: float = 5.0,
    batch_size: int = 0,
) -> dict:
    """Generate preview images for templates with NULL preview_image_url.

    Args:
        ctx: ARQ context (contains preview_generator from startup).
        delay: Seconds between API requests (default 5).
        batch_size: Max templates to process per run (0 = all).

    Returns:
        Dict with success/fail counts.
    """
    generator: PreviewGenerator = ctx["preview_generator"]

    logger.info(
        "Starting preview generation (delay=%.1fs, batch_size=%d)",
        delay,
        batch_size,
    )

    async for session in get_session():
        success, fail = await generator.run(
            session,
            delay=delay,
            batch_size=batch_size,
        )

    logger.info("Preview generation finished: %d success, %d failed", success, fail)
    return {"success": success, "fail": fail}


# ── ARQ configuration ───────────────────────────────────────────────────────


def _parse_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    url = get_settings().redis_url
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [generate_template_previews]

    cron_jobs = [
        cron(
            generate_template_previews,
            hour=3,
            minute=0,
            run_at_startup=False,
        ),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = _parse_redis_settings()

    # Allow long-running preview generation (up to 4 hours)
    max_jobs = 2
    job_timeout = 14400  # 4 hours
