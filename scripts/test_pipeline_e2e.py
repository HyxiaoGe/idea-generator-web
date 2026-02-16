#!/usr/bin/env python3
"""
End-to-end test script for the prompt processing pipeline.

Exercises all pipeline stages (translation, enhancement, negative prompt,
template rendering, degradation fallback) using real PromptHub and
OpenRouter calls — without triggering image generation.

Prerequisites:
  - OPENROUTER_API_KEY set in .env or environment
  - Optional: PROMPTHUB_ENABLED=true, PROMPTHUB_API_KEY, PROMPTHUB_PROJECT_ID
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings
from services.prompt_pipeline import PromptPipeline, contains_chinese, get_prompt_pipeline

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    name: str = ""
    passed: bool = False
    original: str = ""
    processed: str = ""
    negative: str = ""
    error: str = ""
    duration_ms: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAVED_ENV: dict[str, str | None] = {}


def reset_singletons() -> None:
    """Reset module-level singletons so the next call re-creates them."""
    import services.prompt_pipeline as _pp
    import services.llm_client as _llm

    _pp._pipeline = None
    _llm._llm_client = None
    get_settings.cache_clear()


def print_result(index: int, total: int, result: TestResult) -> None:
    if result.skipped:
        tag = "[SKIP]"
    elif result.passed:
        tag = "[PASS]"
    else:
        tag = "[FAIL]"

    print(f"Test {index}/{total}: {tag} {result.name}")
    if result.original:
        print(f"   Original:  {result.original}")
    if result.processed:
        print(f"   Processed: {result.processed}")
    if result.negative:
        print(f"   Negative:  {result.negative}")
    if result.error:
        print(f"   Error:     {result.error}")
    if result.skipped and result.skip_reason:
        print(f"   Reason:    {result.skip_reason}")
    print(f"   Duration:  {result.duration_ms:.0f}ms")
    print()


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------


async def test_backward_compatibility() -> TestResult:
    """Test 1: is_prompt_pipeline_configured reflects actual config."""
    start = time.time()
    result = TestResult(name="Backward Compatibility")

    try:
        settings = get_settings()
        configured = settings.is_prompt_pipeline_configured
        # Expected: True if prompthub_enabled + api_key + openrouter_key all set
        expected = (
            settings.prompthub_enabled
            and bool(settings.prompthub_api_key)
            and bool(settings.openrouter_api_key)
        )
        result.passed = configured == expected
        result.original = (
            f"prompthub_enabled={settings.prompthub_enabled}, "
            f"prompthub_api_key={'set' if settings.prompthub_api_key else 'unset'}, "
            f"openrouter_api_key={'set' if settings.openrouter_api_key else 'unset'}"
        )
        result.processed = f"is_prompt_pipeline_configured={configured} (expected={expected})"
        if not result.passed:
            result.error = f"Expected {expected}, got {configured}"
    except Exception as e:
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def test_english_passthrough() -> TestResult:
    """Test 2: English prompt passes through unchanged (no LLM calls)."""
    start = time.time()
    result = TestResult(name="English Passthrough")
    prompt = "A serene mountain landscape at golden hour with mist rolling through the valleys"

    try:
        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(prompt, enhance=False)

        result.original = prompt
        result.processed = processed.final
        result.passed = (
            processed.language_detected == "en"
            and processed.translated is None
            and processed.final == prompt
        )
        if not result.passed:
            result.error = (
                f"language_detected={processed.language_detected}, "
                f"translated={processed.translated}, "
                f"final matches={processed.final == prompt}"
            )
    except Exception as e:
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def test_chinese_translation() -> TestResult:
    """Test 3: Chinese prompt is auto-translated to English."""
    start = time.time()
    result = TestResult(name="Chinese Auto-Translation")
    prompt = "一只在月光下奔跑的银色狼"

    settings = get_settings()
    if not settings.openrouter_api_key:
        return TestResult(
            name="Chinese Auto-Translation",
            skipped=True,
            skip_reason="OPENROUTER_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(prompt)

        result.original = prompt
        result.processed = processed.final
        result.passed = (
            processed.language_detected == "zh"
            and processed.translated is not None
            and not contains_chinese(processed.translated)
        )
        if not result.passed:
            result.error = (
                f"language_detected={processed.language_detected}, "
                f"translated={processed.translated!r}, "
                f"has_chinese={contains_chinese(processed.translated or '')}"
            )
    except Exception as e:
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def test_ai_enhancement() -> TestResult:
    """Test 4: AI enhancement produces richer prompt."""
    start = time.time()
    result = TestResult(name="AI Enhancement")
    prompt = "A cat sitting on a windowsill"

    settings = get_settings()
    if not settings.openrouter_api_key:
        return TestResult(
            name="AI Enhancement",
            skipped=True,
            skip_reason="OPENROUTER_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(prompt, enhance=True)

        result.original = prompt
        result.processed = processed.final
        result.passed = (
            processed.enhanced is not None
            and len(processed.enhanced) > len(prompt)
        )
        if not result.passed:
            result.error = (
                f"enhanced={processed.enhanced!r}, "
                f"len(enhanced)={len(processed.enhanced or '')}, "
                f"len(original)={len(prompt)}"
            )
    except Exception as e:
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def test_negative_prompt() -> TestResult:
    """Test 5: Negative prompt generation."""
    start = time.time()
    result = TestResult(name="Negative Prompt Generation")
    prompt = "A portrait photo, oil painting"

    settings = get_settings()
    if not settings.openrouter_api_key:
        return TestResult(
            name="Negative Prompt Generation",
            skipped=True,
            skip_reason="OPENROUTER_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(prompt, generate_negative=True)

        result.original = prompt
        result.processed = processed.final
        result.negative = processed.negative_prompt or ""
        result.passed = bool(processed.negative_prompt and len(processed.negative_prompt) > 0)
        if not result.passed:
            result.error = f"negative_prompt={processed.negative_prompt!r}"
    except Exception as e:
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def test_template_rendering() -> TestResult:
    """Test 6: Template rendering with DB template (skip if DB unavailable)."""
    start = time.time()
    result = TestResult(name="Template Rendering")

    try:
        from database import init_database, is_database_available

        await init_database()
        if not is_database_available():
            return TestResult(
                name="Template Rendering",
                skipped=True,
                skip_reason="Database not available",
                duration_ms=(time.time() - start) * 1000,
            )

        # If DB is available, we'd need a real template ID — skip for now
        return TestResult(
            name="Template Rendering",
            skipped=True,
            skip_reason="No test template seeded in database",
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as e:
        return TestResult(
            name="Template Rendering",
            skipped=True,
            skip_reason=f"Database init failed: {e}",
            duration_ms=(time.time() - start) * 1000,
        )


async def test_full_combo() -> TestResult:
    """Test 7: Full combo — translation + enhancement + negative prompt."""
    start = time.time()
    result = TestResult(name="Full Combo (ZH + Enhance + Negative)")
    prompt = "一座被雪覆盖的古老城堡"

    settings = get_settings()
    if not settings.openrouter_api_key:
        return TestResult(
            name="Full Combo (ZH + Enhance + Negative)",
            skipped=True,
            skip_reason="OPENROUTER_API_KEY not set",
            duration_ms=(time.time() - start) * 1000,
        )

    try:
        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(prompt, enhance=True, generate_negative=True)

        result.original = prompt
        result.processed = processed.final
        result.negative = processed.negative_prompt or ""
        result.passed = (
            processed.translated is not None
            and processed.enhanced is not None
            and processed.negative_prompt is not None
        )
        if not result.passed:
            result.error = (
                f"translated={processed.translated!r}, "
                f"enhanced={processed.enhanced!r}, "
                f"negative_prompt={processed.negative_prompt!r}"
            )
    except Exception as e:
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def test_degradation_fallback() -> TestResult:
    """Test 8: Pipeline degrades gracefully with broken API keys."""
    start = time.time()
    result = TestResult(name="Degradation Fallback")
    prompt = "A peaceful garden"

    # Save original env vars
    keys_to_save = ["OPENROUTER_API_KEY", "PROMPTHUB_ENABLED", "PROMPTHUB_API_KEY"]
    saved = {k: os.environ.get(k) for k in keys_to_save}

    try:
        # Set broken values
        os.environ["OPENROUTER_API_KEY"] = "sk-broken-key-for-testing"
        os.environ["PROMPTHUB_ENABLED"] = "false"
        os.environ.pop("PROMPTHUB_API_KEY", None)
        reset_singletons()

        pipeline = get_prompt_pipeline()
        processed = await pipeline.process(prompt, enhance=True, generate_negative=True)

        result.original = prompt
        result.processed = processed.final
        # Pipeline should not raise — it should degrade and return the original
        result.passed = processed.final == prompt
        if not result.passed:
            result.error = f"Expected final==original, got final={processed.final!r}"
    except Exception as e:
        # If the pipeline raises, that's a failure — it should degrade gracefully
        result.error = f"Pipeline raised instead of degrading: {e}"
    finally:
        # Restore original env vars
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reset_singletons()

    result.duration_ms = (time.time() - start) * 1000
    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_all_tests() -> list[TestResult]:
    tests = [
        test_backward_compatibility,
        test_english_passthrough,
        test_chinese_translation,
        test_ai_enhancement,
        test_negative_prompt,
        test_template_rendering,
        test_full_combo,
        test_degradation_fallback,
    ]

    results: list[TestResult] = []
    total = len(tests)

    for i, test_fn in enumerate(tests, 1):
        r = await test_fn()
        print_result(i, total, r)
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  Prompt Pipeline E2E Tests")
    print("=" * 60)
    print()

    settings = get_settings()
    print(f"  OpenRouter API key: {'set' if settings.openrouter_api_key else 'NOT SET'}")
    print(f"  OpenRouter model:   {settings.openrouter_model}")
    print(f"  PromptHub enabled:  {settings.prompthub_enabled}")
    print(f"  Auto-translate:     {settings.prompt_auto_translate}")
    print()

    results = asyncio.run(run_all_tests())

    # Summary
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print()

    for r in results:
        if r.skipped:
            tag = "[SKIP]"
        elif r.passed:
            tag = "[PASS]"
        else:
            tag = "[FAIL]"
        print(f"  {tag} {r.name}")

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    total = len(results)

    print()
    print(f"  Total: {total}  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
    print()

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
