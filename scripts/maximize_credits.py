#!/usr/bin/env python3
"""
Maximize Google API credits before expiration.

Orchestrates 5 phases of image generation to fully utilize remaining
API credits. Reuses existing PreviewGenerator, TemplateGenerator,
GoogleProvider, and StorageManager — no modifications to existing code.

Usage:
    # Dry-run to see what would happen
    python scripts/maximize_credits.py --dry-run

    # Run all phases (挂着跑)
    python scripts/maximize_credits.py --delay 3

    # Run specific phases
    python scripts/maximize_credits.py --phases 1,2 --delay 3
    python scripts/maximize_credits.py --phases 3,4,5 --delay 3

    # Aggressive mode (more images, higher quality)
    python scripts/maximize_credits.py --budget 200 --delay 2

Phases:
    1  LLM template expansion   — generate new prompt data via OpenRouter ($0)
    2  1K preview generation     — fill NULL preview_image_url (reuses PreviewGenerator)
    3  4K high-res upgrade       — re-generate top templates at 4K with Imagen 4
    4  Multi-model comparison    — same prompt across 4 Google models
    5  Style variants            — 2-3 variations per template for library depth
"""

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, update  # noqa: E402

from database import close_database, get_session, init_database  # noqa: E402
from database.models.template import PromptTemplate  # noqa: E402
from database.repositories.template_repo import TemplateRepository  # noqa: E402
from services.preview_generator import (  # noqa: E402
    CATEGORY_ASPECT_RATIOS,
    MAX_RETRIES,
    RETRY_BACKOFF,
    PreviewGenerator,
    _slugify,
    is_retryable,
)
from services.providers.base import GenerationRequest  # noqa: E402
from services.providers.google import GOOGLE_MODELS, GoogleProvider  # noqa: E402
from services.storage import get_storage_manager  # noqa: E402
from services.template_generator import CATEGORY_STYLES, TemplateGenerator  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Cost table (from GoogleProvider._estimate_cost) ────────────────────────
COST_PER_IMAGE = {
    "gemini-3-pro-image-preview": {"1K": 0.04, "2K": 0.06, "4K": 0.08},
    "imagen-4.0-generate-001": {"1K": 0.04, "2K": 0.06, "4K": 0.08},
    "imagen-4.0-ultra-generate-001": {"1K": 0.06, "2K": 0.09, "4K": 0.12},
    "imagen-4.0-fast-generate-001": {"1K": 0.02, "2K": 0.03, "4K": 0.04},
}

# Models for multi-model comparison (Phase 4)
COMPARE_MODELS = [
    "gemini-3-pro-image-preview",
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
]


# ── Result tracking ────────────────────────────────────────────────────────
@dataclass
class PhaseResult:
    phase: int
    name: str
    success: int = 0
    fail: int = 0
    skipped: int = 0
    cost: float = 0.0
    duration: float = 0.0


@dataclass
class RunStats:
    results: list[PhaseResult] = field(default_factory=list)
    total_cost: float = 0.0
    total_images: int = 0
    start_time: float = 0.0

    def summary(self) -> str:
        lines = ["\n" + "=" * 60, "  EXECUTION SUMMARY", "=" * 60]
        for r in self.results:
            lines.append(
                f"  Phase {r.phase} ({r.name}): "
                f"{r.success} ok / {r.fail} fail / {r.skipped} skip  "
                f"${r.cost:.2f}  {r.duration:.0f}s"
            )
        lines.append("-" * 60)
        lines.append(f"  Total images: {self.total_images}")
        lines.append(f"  Total cost:   ${self.total_cost:.2f}")
        elapsed = time.time() - self.start_time if self.start_time else 0
        lines.append(f"  Elapsed:      {elapsed / 60:.1f} min")
        lines.append("=" * 60)
        return "\n".join(lines)


# ── Shared helpers ─────────────────────────────────────────────────────────
async def generate_and_save(
    provider: GoogleProvider,
    storage,
    request: GenerationRequest,
    key: str,
    *,
    delay: float = 3.0,
) -> tuple[bool, float]:
    """Generate one image and save to storage. Returns (success, cost)."""
    model_id = request.preferred_model or provider.get_default_model().id
    cost_table = COST_PER_IMAGE.get(model_id, COST_PER_IMAGE["gemini-3-pro-image-preview"])
    unit_cost = cost_table.get(request.resolution, 0.04)

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await provider.generate(request, model_id=request.preferred_model)

            if result.success and result.image is not None:
                buf = BytesIO()
                result.image.save(buf, format="PNG")
                await storage.provider.save(
                    key=key,
                    data=buf.getvalue(),
                    content_type="image/png",
                )
                return True, unit_cost

            error = result.error or "No image in result"
            if is_retryable(error) and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                logger.warning("  RETRY %d/%d in %ds — %s", attempt + 1, MAX_RETRIES, wait, error)
                await asyncio.sleep(wait)
                continue

            logger.warning("  SKIP: %s", error)
            return False, 0.0

        except Exception as e:
            error_str = str(e)
            if is_retryable(error_str) and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                logger.warning("  RETRY %d/%d in %ds — %s", attempt + 1, MAX_RETRIES, wait, error_str)
                await asyncio.sleep(wait)
                continue
            logger.exception("  FAIL: %s", e)
            return False, 0.0

    return False, 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 1: LLM Template Expansion (uses OpenRouter, essentially $0)
# ═══════════════════════════════════════════════════════════════════════════
async def phase1_expand_templates(
    session,
    *,
    count_per_category: int = 20,
    dry_run: bool = False,
) -> PhaseResult:
    """Generate new prompt templates via LLM to fill coverage gaps."""
    pr = PhaseResult(phase=1, name="LLM template expansion")
    start = time.time()

    # Count existing templates per category
    stmt = (
        select(PromptTemplate.category, func.count())
        .where(PromptTemplate.deleted_at.is_(None))
        .group_by(PromptTemplate.category)
    )
    result = await session.execute(stmt)
    existing: dict[str, int] = {row[0]: row[1] for row in result.all()}

    total_categories = list(CATEGORY_STYLES.keys())
    categories_to_fill: list[tuple[str, int]] = []

    for cat in total_categories:
        current = existing.get(cat, 0)
        # Target: at least count_per_category per category (including AI-generated)
        needed = max(0, count_per_category - current)
        if needed > 0:
            categories_to_fill.append((cat, needed))

    if not categories_to_fill:
        logger.info("Phase 1: All categories have >= %d templates, nothing to do", count_per_category)
        pr.duration = time.time() - start
        return pr

    total_to_generate = sum(n for _, n in categories_to_fill)
    logger.info(
        "Phase 1: Will generate ~%d templates across %d categories",
        total_to_generate,
        len(categories_to_fill),
    )
    for cat, needed in categories_to_fill:
        logger.info("  %s: have %d, need %d more", cat, existing.get(cat, 0), needed)

    if dry_run:
        pr.skipped = total_to_generate
        pr.duration = time.time() - start
        return pr

    repo = TemplateRepository(session)
    generator = TemplateGenerator(repo)

    try:
        for cat, needed in categories_to_fill:
            logger.info("Generating %d templates for [%s] ...", needed, cat)
            try:
                stats = await generator.generate_templates_for_category(
                    category=cat,
                    count=needed,
                )
                pr.success += stats.saved
                pr.fail += stats.generated - stats.saved
                logger.info(
                    "  [%s] generated=%d, quality_passed=%d, saved=%d",
                    cat,
                    stats.generated,
                    stats.passed_quality,
                    stats.saved,
                )
            except Exception:
                logger.exception("  Failed to generate for %s", cat)
                pr.fail += needed
    finally:
        await generator.close()

    pr.duration = time.time() - start
    return pr


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 2: Generate 1K Previews for NULL preview_image_url
# ═══════════════════════════════════════════════════════════════════════════
async def phase2_generate_previews(
    session,
    provider: GoogleProvider | None = None,
    storage=None,
    *,
    delay: float = 5.0,
    batch_size: int = 0,
    dry_run: bool = False,
) -> PhaseResult:
    """Generate 1K previews using generate_and_save (same path as Phase 3)."""
    pr = PhaseResult(phase=2, name="1K preview generation")
    start = time.time()

    # Query templates needing previews
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
        logger.info("Phase 2: All templates already have preview images")
        pr.duration = time.time() - start
        return pr

    estimated_cost = len(templates) * 0.04
    logger.info("Phase 2: %d templates need previews (est. $%.2f)", len(templates), estimated_cost)

    if dry_run:
        pr.skipped = len(templates)
        pr.cost = estimated_cost
        pr.duration = time.time() - start
        return pr

    for i, tpl in enumerate(templates):
        slug = _slugify(tpl.display_name_en)
        category = tpl.category
        key = f"templates/preview/{category}/{slug}.png"
        aspect_ratio = CATEGORY_ASPECT_RATIOS.get(category, "1:1")

        logger.info("[%d/%d] 1K: %s/%s ...", i + 1, len(templates), category, slug)

        request = GenerationRequest(
            prompt=tpl.prompt_text,
            aspect_ratio=aspect_ratio,
            resolution="1K",
            safety_level="moderate",
            preferred_model="gemini-3-pro-image-preview",
        )

        try:
            ok, cost = await asyncio.wait_for(
                generate_and_save(provider, storage, request, key, delay=delay),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.warning("  TIMEOUT after 120s, skipping")
            ok, cost = False, 0.0

        if ok:
            pr.success += 1
            pr.cost += cost
            public_url = storage.provider.get_public_url(key)
            if public_url:
                await session.execute(
                    update(PromptTemplate)
                    .where(PromptTemplate.id == tpl.id)
                    .values(preview_image_url=public_url)
                )
                await session.flush()
        else:
            pr.fail += 1

        await asyncio.sleep(delay)

    pr.duration = time.time() - start
    return pr


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 3: 4K High-Resolution Upgrades
# ═══════════════════════════════════════════════════════════════════════════
async def phase3_highres_upgrades(
    session,
    provider: GoogleProvider,
    storage,
    *,
    max_images: int = 100,
    model_id: str = "imagen-4.0-generate-001",
    delay: float = 5.0,
    dry_run: bool = False,
) -> PhaseResult:
    """Re-generate top templates at 4K resolution with premium model."""
    pr = PhaseResult(phase=3, name="4K high-res upgrade")
    start = time.time()

    # Select top templates by engagement (that already have 1K preview but no 4K)
    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.preview_image_url.isnot(None))
        .where(PromptTemplate.preview_4k_url.is_(None))
        .where(PromptTemplate.deleted_at.is_(None))
        .where(PromptTemplate.media_type == "image")
        .order_by(PromptTemplate.trending_score.desc())
        .limit(max_images)
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    if not templates:
        logger.info("Phase 3: No templates eligible for 4K upgrade")
        pr.duration = time.time() - start
        return pr

    unit_cost = COST_PER_IMAGE.get(model_id, {}).get("4K", 0.08)
    estimated_cost = len(templates) * unit_cost
    logger.info(
        "Phase 3: %d templates for 4K upgrade with %s (est. $%.2f)",
        len(templates),
        model_id,
        estimated_cost,
    )

    if dry_run:
        pr.skipped = len(templates)
        pr.cost = estimated_cost
        pr.duration = time.time() - start
        return pr

    for i, tpl in enumerate(templates):
        slug = _slugify(tpl.display_name_en)
        category = tpl.category
        key = f"templates/preview-4k/{category}/{slug}.png"
        aspect_ratio = CATEGORY_ASPECT_RATIOS.get(category, "1:1")

        logger.info("[%d/%d] 4K: %s/%s ...", i + 1, len(templates), category, slug)

        request = GenerationRequest(
            prompt=tpl.prompt_text,
            aspect_ratio=aspect_ratio,
            resolution="4K",
            safety_level="moderate",
            preferred_model=model_id,
        )

        ok, cost = await generate_and_save(provider, storage, request, key, delay=delay)
        if ok:
            pr.success += 1
            pr.cost += cost
            # Write preview_4k_url back to the template record
            public_url = storage.provider.get_public_url(key)
            if public_url:
                await session.execute(
                    update(PromptTemplate)
                    .where(PromptTemplate.id == tpl.id)
                    .values(preview_4k_url=public_url)
                )
                await session.flush()
        else:
            pr.fail += 1

        await asyncio.sleep(delay)

    pr.duration = time.time() - start
    return pr


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 4: Multi-Model Comparison
# ═══════════════════════════════════════════════════════════════════════════
async def phase4_model_comparison(
    session,
    provider: GoogleProvider,
    storage,
    *,
    max_templates: int = 50,
    delay: float = 5.0,
    dry_run: bool = False,
) -> PhaseResult:
    """Generate the same prompt across all 4 Google models for comparison."""
    pr = PhaseResult(phase=4, name="Multi-model comparison")
    start = time.time()

    # Pick diverse templates (top N spread across categories)
    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.preview_image_url.isnot(None))
        .where(PromptTemplate.deleted_at.is_(None))
        .where(PromptTemplate.media_type == "image")
        .order_by(PromptTemplate.trending_score.desc())
        .limit(max_templates)
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    if not templates:
        logger.info("Phase 4: No templates eligible")
        pr.duration = time.time() - start
        return pr

    total_images = len(templates) * len(COMPARE_MODELS)
    estimated_cost = sum(
        COST_PER_IMAGE.get(m, {}).get("1K", 0.04) * len(templates) for m in COMPARE_MODELS
    )
    logger.info(
        "Phase 4: %d templates × %d models = %d images (est. $%.2f)",
        len(templates),
        len(COMPARE_MODELS),
        total_images,
        estimated_cost,
    )

    if dry_run:
        pr.skipped = total_images
        pr.cost = estimated_cost
        pr.duration = time.time() - start
        return pr

    for i, tpl in enumerate(templates):
        slug = _slugify(tpl.display_name_en)
        category = tpl.category
        aspect_ratio = CATEGORY_ASPECT_RATIOS.get(category, "1:1")

        for model_id in COMPARE_MODELS:
            model_slug = model_id.replace(".", "-")
            key = f"templates/compare/{model_slug}/{category}/{slug}.png"

            logger.info(
                "[%d/%d] Compare %s: %s/%s ...",
                i + 1,
                len(templates),
                model_id.split("-")[0],
                category,
                slug,
            )

            request = GenerationRequest(
                prompt=tpl.prompt_text,
                aspect_ratio=aspect_ratio,
                resolution="1K",
                safety_level="moderate",
                preferred_model=model_id,
            )

            ok, cost = await generate_and_save(provider, storage, request, key, delay=delay)
            if ok:
                pr.success += 1
                pr.cost += cost
            else:
                pr.fail += 1

            await asyncio.sleep(delay)

    pr.duration = time.time() - start
    return pr


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 5: Style Variants
# ═══════════════════════════════════════════════════════════════════════════

# Variant prompt suffixes — lightweight style twists
VARIANT_STYLES = [
    " — reimagined in oil painting style with visible brushstrokes and impasto texture",
    " — reimagined as a pencil sketch with cross-hatching and charcoal shading",
    " — reimagined in watercolor style with soft wet-on-wet washes and paper texture",
]


async def phase5_style_variants(
    session,
    provider: GoogleProvider,
    storage,
    *,
    max_templates: int = 100,
    variants_per_template: int = 2,
    delay: float = 5.0,
    dry_run: bool = False,
) -> PhaseResult:
    """Generate style variants of existing templates."""
    pr = PhaseResult(phase=5, name="Style variants")
    start = time.time()

    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.preview_image_url.isnot(None))
        .where(PromptTemplate.deleted_at.is_(None))
        .where(PromptTemplate.media_type == "image")
        .order_by(PromptTemplate.trending_score.desc())
        .limit(max_templates)
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    if not templates:
        logger.info("Phase 5: No templates eligible")
        pr.duration = time.time() - start
        return pr

    variants_count = min(variants_per_template, len(VARIANT_STYLES))
    total_images = len(templates) * variants_count
    estimated_cost = total_images * 0.04
    logger.info(
        "Phase 5: %d templates × %d variants = %d images (est. $%.2f)",
        len(templates),
        variants_count,
        total_images,
        estimated_cost,
    )

    if dry_run:
        pr.skipped = total_images
        pr.cost = estimated_cost
        pr.duration = time.time() - start
        return pr

    for i, tpl in enumerate(templates):
        slug = _slugify(tpl.display_name_en)
        category = tpl.category
        aspect_ratio = CATEGORY_ASPECT_RATIOS.get(category, "1:1")

        for v_idx in range(variants_count):
            key = f"templates/variants/{category}/{slug}_v{v_idx + 1}.png"
            variant_prompt = tpl.prompt_text + VARIANT_STYLES[v_idx]

            logger.info(
                "[%d/%d] Variant %d: %s/%s ...",
                i + 1,
                len(templates),
                v_idx + 1,
                category,
                slug,
            )

            request = GenerationRequest(
                prompt=variant_prompt,
                aspect_ratio=aspect_ratio,
                resolution="1K",
                safety_level="moderate",
            )

            ok, cost = await generate_and_save(provider, storage, request, key, delay=delay)
            if ok:
                pr.success += 1
                pr.cost += cost
            else:
                pr.fail += 1

            await asyncio.sleep(delay)

    pr.duration = time.time() - start
    return pr


# ═══════════════════════════════════════════════════════════════════════════
#  BACKFILL: Link existing 4K images to template records
# ═══════════════════════════════════════════════════════════════════════════
async def backfill_4k_urls(session, storage) -> int:
    """Scan MinIO templates/preview-4k/ and update preview_4k_url for matching templates.

    Matches files by category/slug pattern against existing templates.
    Returns number of templates updated.
    """
    # List all 4K preview keys
    keys = await storage.provider.list_keys(prefix="templates/preview-4k/", limit=1000)
    if not keys:
        logger.info("Backfill: No 4K preview files found in storage")
        return 0

    logger.info("Backfill: Found %d 4K preview files", len(keys))

    # Load all active image templates with their slugs
    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.deleted_at.is_(None))
        .where(PromptTemplate.media_type == "image")
        .where(PromptTemplate.preview_4k_url.is_(None))
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    # Build lookup: "category/slug" -> template
    slug_map: dict[str, PromptTemplate] = {}
    for tpl in templates:
        slug = _slugify(tpl.display_name_en)
        lookup_key = f"{tpl.category}/{slug}"
        slug_map[lookup_key] = tpl

    updated = 0
    for key in keys:
        # key format: templates/preview-4k/{category}/{slug}.png
        parts = key.replace("templates/preview-4k/", "").replace(".png", "")
        if "/" not in parts:
            continue

        tpl = slug_map.get(parts)
        if not tpl:
            continue

        public_url = storage.provider.get_public_url(key)
        if public_url:
            await session.execute(
                update(PromptTemplate)
                .where(PromptTemplate.id == tpl.id)
                .values(preview_4k_url=public_url)
            )
            updated += 1
            logger.info("  Backfill: %s -> %s", parts, public_url)

    if updated:
        await session.flush()

    logger.info("Backfill: Updated %d / %d templates", updated, len(keys))
    return updated


# ═══════════════════════════════════════════════════════════════════════════
#  DRY-RUN SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
async def dry_run_summary(session, phases: list[int], args) -> None:
    """Print estimated costs and image counts without generating anything."""
    logger.info("=" * 60)
    logger.info("  DRY RUN — estimating what would be generated")
    logger.info("=" * 60)

    total_cost = 0.0
    total_images = 0

    all_results: list[PhaseResult] = []

    if 1 in phases:
        r = await phase1_expand_templates(
            session,
            count_per_category=args.templates_per_category,
            dry_run=True,
        )
        all_results.append(r)

    if 2 in phases:
        r = await phase2_generate_previews(session, dry_run=True)
        all_results.append(r)

    if 3 in phases:
        r = await phase3_highres_upgrades(
            session, None, None,  # type: ignore
            max_images=args.max_4k,
            dry_run=True,
        )
        all_results.append(r)

    if 4 in phases:
        r = await phase4_model_comparison(
            session, None, None,  # type: ignore
            max_templates=args.max_compare,
            dry_run=True,
        )
        all_results.append(r)

    if 5 in phases:
        r = await phase5_style_variants(
            session, None, None,  # type: ignore
            max_templates=args.max_variants,
            variants_per_template=args.variants_count,
            dry_run=True,
        )
        all_results.append(r)

    print("\n" + "=" * 60)
    print("  DRY RUN ESTIMATE")
    print("=" * 60)
    for r in all_results:
        images = r.skipped
        total_images += images
        total_cost += r.cost
        print(f"  Phase {r.phase} ({r.name}): ~{images} images, ~${r.cost:.2f}")

    print("-" * 60)
    print(f"  Total images:     ~{total_images}")
    print(f"  Total cost:       ~${total_cost:.2f}")
    print(f"  Remaining budget: ~${args.budget - total_cost:.2f}")
    est_minutes = total_images * (args.delay + 5) / 60  # ~5s avg generation + delay
    print(f"  Est. runtime:     ~{est_minutes:.0f} min ({est_minutes / 60:.1f} hours)")
    print("=" * 60)
    print("\nRun without --dry-run to execute.")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════
async def main(args) -> None:
    await init_database()

    phases = [int(p) for p in args.phases.split(",")]

    try:
        async for session in get_session():
            if args.dry_run:
                await dry_run_summary(session, phases, args)
                return

            # Backfill mode: link existing 4K images to DB records
            if args.backfill_4k:
                storage = get_storage_manager()
                if not storage.is_available:
                    logger.error("Storage not available — check storage configuration")
                    return
                count = await backfill_4k_urls(session, storage)
                await session.commit()
                logger.info("Backfill complete: %d templates updated", count)
                return

            # Initialize shared resources
            provider = GoogleProvider()
            if not provider.is_available:
                logger.error("Google provider not available — check GOOGLE_API_KEY")
                return

            storage = get_storage_manager()
            if not storage.is_available:
                logger.error("Storage not available — check storage configuration")
                return

            stats = RunStats(start_time=time.time())

            # ── Phase 1 ──
            if 1 in phases:
                logger.info("\n%s PHASE 1: LLM Template Expansion %s", "=" * 10, "=" * 10)
                r = await phase1_expand_templates(
                    session,
                    count_per_category=args.templates_per_category,
                )
                stats.results.append(r)
                stats.total_images += r.success
                await session.commit()
                logger.info("Phase 1 done: %d templates created", r.success)

            # ── Phase 2 ──
            if 2 in phases:
                logger.info("\n%s PHASE 2: 1K Preview Generation %s", "=" * 10, "=" * 10)
                r = await phase2_generate_previews(
                    session,
                    provider,
                    storage,
                    delay=args.delay,
                    batch_size=args.max_previews,
                )
                stats.results.append(r)
                stats.total_images += r.success
                stats.total_cost += r.cost
                await session.commit()
                logger.info("Phase 2 done: %d previews, $%.2f", r.success, r.cost)

            # ── Phase 3 ──
            if 3 in phases:
                logger.info("\n%s PHASE 3: 4K High-Res Upgrade %s", "=" * 10, "=" * 10)
                r = await phase3_highres_upgrades(
                    session,
                    provider,
                    storage,
                    max_images=args.max_4k,
                    model_id=args.model_4k,
                    delay=args.delay,
                )
                stats.results.append(r)
                stats.total_images += r.success
                stats.total_cost += r.cost
                await session.commit()
                logger.info("Phase 3 done: %d 4K images, $%.2f", r.success, r.cost)

            # ── Phase 4 ──
            if 4 in phases:
                logger.info("\n%s PHASE 4: Multi-Model Comparison %s", "=" * 10, "=" * 10)
                r = await phase4_model_comparison(
                    session,
                    provider,
                    storage,
                    max_templates=args.max_compare,
                    delay=args.delay,
                )
                stats.results.append(r)
                stats.total_images += r.success
                stats.total_cost += r.cost
                await session.commit()
                logger.info("Phase 4 done: %d comparison images, $%.2f", r.success, r.cost)

            # ── Phase 5 ──
            if 5 in phases:
                logger.info("\n%s PHASE 5: Style Variants %s", "=" * 10, "=" * 10)
                r = await phase5_style_variants(
                    session,
                    provider,
                    storage,
                    max_templates=args.max_variants,
                    variants_per_template=args.variants_count,
                    delay=args.delay,
                )
                stats.results.append(r)
                stats.total_images += r.success
                stats.total_cost += r.cost
                await session.commit()
                logger.info("Phase 5 done: %d variant images, $%.2f", r.success, r.cost)

            # ── Summary ──
            print(stats.summary())

    finally:
        await close_database()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Maximize Google API credits before expiration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # See what would happen
  %(prog)s --phases 1,2 --delay 3       # LLM + 1K previews
  %(prog)s --phases 3,4,5 --delay 3     # 4K + compare + variants
  %(prog)s --budget 200 --delay 2       # Full run, aggressive
        """,
    )
    parser.add_argument("--dry-run", action="store_true", help="Estimate only, don't generate")
    parser.add_argument("--backfill-4k", action="store_true", help="Backfill preview_4k_url for existing 4K images in storage")
    parser.add_argument("--phases", default="1,2,3,4,5", help="Comma-separated phases to run (default: 1,2,3,4,5)")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between API requests (default: 5)")
    parser.add_argument("--budget", type=float, default=200.0, help="Total budget in $ (for display only)")

    # Phase 1
    parser.add_argument("--templates-per-category", type=int, default=40, help="Target templates per category (default: 40)")

    # Phase 2
    parser.add_argument("--max-previews", type=int, default=0, help="Max 1K previews to generate (0 = all, default: 0)")

    # Phase 3
    parser.add_argument("--max-4k", type=int, default=100, help="Max templates for 4K upgrade (default: 100)")
    parser.add_argument("--model-4k", default="imagen-4.0-generate-001", help="Model for 4K generation (default: imagen-4.0-generate-001)")

    # Phase 4
    parser.add_argument("--max-compare", type=int, default=50, help="Max templates for model comparison (default: 50)")

    # Phase 5
    parser.add_argument("--max-variants", type=int, default=100, help="Max templates for variant generation (default: 100)")
    parser.add_argument("--variants-count", type=int, default=2, help="Variants per template (default: 2, max: 3)")

    args = parser.parse_args()
    args.variants_count = min(args.variants_count, len(VARIANT_STYLES))

    asyncio.run(main(args))
