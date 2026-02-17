"""AI batch template generation script.

Generates templates across all categories using the OpenRouter LLM pipeline.
Requires OPENROUTER_API_KEY and DATABASE_URL to be configured.

Usage:
    .venv/bin/python scripts/generate_ai_templates.py
    .venv/bin/python scripts/generate_ai_templates.py --categories portrait,landscape --count 5
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_session, init_database  # noqa: E402
from database.repositories.template_repo import TemplateRepository  # noqa: E402
from services.template_generator import CATEGORY_STYLES, TemplateGenerator  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main(categories: list[str] | None, count_per_category: int) -> None:
    await init_database()

    async for session in get_session():
        repo = TemplateRepository(session)
        generator = TemplateGenerator(repo)

        try:
            result = await generator.batch_generate(
                categories=categories,
                count_per_category=count_per_category,
            )
            logger.info(
                "Batch generation complete: generated=%d, saved=%d",
                result.total_generated,
                result.total_saved,
            )
            for stat in result.stats:
                logger.info(
                    "  %s: generated=%d, quality_passed=%d, saved=%d",
                    stat.category,
                    stat.generated,
                    stat.passed_quality,
                    stat.saved,
                )
        finally:
            await generator.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate AI prompt templates")
    parser.add_argument(
        "--categories",
        type=str,
        default=None,
        help=f"Comma-separated categories (default: all). Available: {', '.join(CATEGORY_STYLES.keys())}",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Templates per category (default: 10)",
    )
    args = parser.parse_args()

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None

    asyncio.run(main(categories=cats, count_per_category=args.count))
