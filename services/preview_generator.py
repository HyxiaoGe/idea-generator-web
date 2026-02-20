"""
Preview image generator for prompt templates.

Generates preview images for templates with NULL preview_image_url using the
Google Gemini provider, with retry + exponential backoff for transient errors
(503, rate limit, high demand).

Used by both `scripts/seed_templates.py` and `api/workers.py` (ARQ worker).
"""

import asyncio
import logging
import re
from io import BytesIO

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.template import PromptTemplate
from services.providers.base import GenerationRequest
from services.providers.google import GoogleProvider
from services.storage import get_storage_manager

logger = logging.getLogger(__name__)

# ── Retry constants ──────────────────────────────────────────────────────────

MAX_RETRIES = 5
RETRY_BACKOFF = [30, 60, 120, 240, 480]  # seconds — escalating cooldown
RETRYABLE_KEYWORDS = ["high demand", "rate limit", "overloaded", "quota", "503", "429"]

# ── Category → aspect ratio mapping ─────────────────────────────────────────

CATEGORY_ASPECT_RATIOS: dict[str, str] = {
    "portrait": "3:4",
    "landscape": "16:9",
    "illustration": "1:1",
    "product": "1:1",
    "architecture": "16:9",
    "anime": "3:4",
    "fantasy": "16:9",
    "graphic-design": "1:1",
    "food": "1:1",
    "abstract": "1:1",
}


def _slugify(name: str) -> str:
    """Convert display_name_en to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def is_retryable(error_msg: str) -> bool:
    """Check if an error message indicates a transient / rate-limit failure."""
    lower = error_msg.lower()
    return any(kw in lower for kw in RETRYABLE_KEYWORDS)


class PreviewGenerator:
    """Generate preview images for templates with NULL preview_image_url.

    Encapsulates the retry logic, storage upload, and DB update in a single
    reusable class so that both the seed script and the ARQ worker share the
    exact same behaviour.
    """

    def __init__(
        self,
        provider: GoogleProvider | None = None,
    ):
        self._provider = provider or GoogleProvider()

    async def run(
        self,
        session: AsyncSession,
        *,
        delay: float = 5.0,
        batch_size: int = 0,
    ) -> tuple[int, int]:
        """Generate missing preview images.

        Args:
            session: Async DB session (caller manages commit/rollback).
            delay: Seconds between API requests (default 5).
            batch_size: Max templates to process (0 = all).

        Returns:
            (success_count, fail_count)
        """
        # Check provider
        if not self._provider.is_available:
            logger.error("Google provider not available — check GOOGLE_API_KEY")
            return 0, 0

        # Check storage
        storage = get_storage_manager()
        if not storage.is_available:
            logger.error("Storage not available — check storage configuration")
            return 0, 0

        # Query templates needing images
        stmt = (
            select(PromptTemplate)
            .where(PromptTemplate.preview_image_url.is_(None))
            .where(PromptTemplate.deleted_at.is_(None))
            .order_by(PromptTemplate.created_at)
        )
        if batch_size > 0:
            stmt = stmt.limit(batch_size)

        result = await session.execute(stmt)
        templates = list(result.scalars().all())

        if not templates:
            logger.info("All templates already have preview images")
            return 0, 0

        total = len(templates)
        success = 0
        fail = 0

        for i, tpl in enumerate(templates):
            slug = _slugify(tpl.display_name_en)
            category = tpl.category
            key = f"templates/preview/{category}/{slug}.png"

            logger.info("[%d/%d] Generating: %s/%s ...", i + 1, total, category, slug)

            aspect_ratio = CATEGORY_ASPECT_RATIOS.get(category, "1:1")
            request = GenerationRequest(
                prompt=tpl.prompt_text,
                aspect_ratio=aspect_ratio,
                resolution="1K",
                safety_level="moderate",
            )

            generated = await self._generate_single(session, tpl, request, key, storage)

            if generated:
                success += 1
            else:
                fail += 1

            # Base delay between requests to avoid hammering
            await asyncio.sleep(delay)

        logger.info(
            "Preview generation complete: %d success, %d failed out of %d",
            success,
            fail,
            total,
        )
        return success, fail

    async def _generate_single(
        self,
        session: AsyncSession,
        tpl: PromptTemplate,
        request: GenerationRequest,
        key: str,
        storage,
    ) -> bool:
        """Generate a single preview image with retry logic.

        Returns True on success, False on failure.
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                gen_result = await self._provider.generate(request)

                if gen_result.success and gen_result.image is not None:
                    buf = BytesIO()
                    gen_result.image.save(buf, format="PNG")
                    await storage.provider.save(
                        key=key,
                        data=buf.getvalue(),
                        content_type="image/png",
                    )
                    public_url = storage.provider.get_public_url(key)

                    await session.execute(
                        update(PromptTemplate)
                        .where(PromptTemplate.id == tpl.id)
                        .values(preview_image_url=public_url)
                    )
                    await session.flush()

                    logger.info("  OK -> %s", public_url)
                    return True

                # Generation returned but failed — check if retryable
                error = gen_result.error or "No image in result"
                if is_retryable(error) and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                    logger.warning(
                        "  RETRY %d/%d in %ds — %s", attempt + 1, MAX_RETRIES, wait, error
                    )
                    await asyncio.sleep(wait)
                    continue

                # Non-retryable or retries exhausted
                logger.warning("  SKIP [%s]: %s", tpl.display_name_en, error)
                return False

            except Exception as e:
                error_str = str(e)
                if is_retryable(error_str) and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                    logger.warning(
                        "  RETRY %d/%d in %ds — %s", attempt + 1, MAX_RETRIES, wait, error_str
                    )
                    await asyncio.sleep(wait)
                    continue

                logger.exception("  FAIL [%s]: %s", tpl.display_name_en, e)
                return False

        return False
