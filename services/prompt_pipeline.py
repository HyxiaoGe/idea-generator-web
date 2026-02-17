"""
Prompt processing pipeline with PromptHub integration.

Provides auto-translation (Chinese -> English), AI enhancement,
and negative prompt generation using PromptHub meta prompts and
an OpenRouter LLM backend.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import httpx

from core.config import get_settings

if TYPE_CHECKING:
    from database.repositories.template_repo import TemplateRepository

logger = logging.getLogger(__name__)

# Regex for detecting Chinese characters (CJK Unified Ideographs)
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def contains_chinese(text: str) -> bool:
    """Return True if text contains Chinese characters."""
    return bool(_CHINESE_RE.search(text))


@dataclass
class ProcessedPrompt:
    """Result of running a prompt through the pipeline."""

    original: str
    translated: str | None = None
    enhanced: str | None = None
    negative_prompt: str | None = None
    final: str = ""
    language_detected: str | None = None
    pipeline_duration: float = 0.0
    template_used: bool = False
    was_translated: bool = False
    was_enhanced: bool = False
    template_name: str | None = None


class PromptPipeline:
    """
    Multi-step prompt processing pipeline.

    Steps (all optional, executed in order):
    1. Template rendering — apply a local DB template
    2. Language detection — simple regex-based Chinese detection
    3. Translation — Chinese -> English via PromptHub meta prompt + LLM
    4. Enhancement — optimize prompt for image generation
    5. Negative prompt — generate a negative prompt
    """

    # Mapping: pipeline step -> PromptHub prompt slug
    _PROMPT_SLUGS = {
        "translate_zh": "translate-optimize-zh",
        "enhance_en": "desc-enhance-en",
        "enhance_zh": "desc-enhance-zh",
        "negative_en": "negative-generate-en",
        "negative_zh": "negative-generate-zh",
    }

    def __init__(self):
        self._http_client: httpx.AsyncClient | None = None
        # slug -> prompt ID cache (populated on first list call)
        self._slug_to_id: dict[str, str] = {}

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Lazy-init an httpx client for the self-hosted PromptHub API."""
        if self._http_client is None:
            settings = get_settings()
            if not settings.prompthub_api_key:
                raise RuntimeError("PromptHub API key not configured")
            self._http_client = httpx.AsyncClient(
                base_url=settings.prompthub_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {settings.prompthub_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
        return self._http_client

    async def _ensure_slug_map(self) -> None:
        """Fetch project prompts once and cache slug -> ID mapping."""
        if self._slug_to_id:
            return
        settings = get_settings()
        client = await self._get_http_client()
        resp = await client.get(
            f"/api/v1/projects/{settings.prompthub_project_id}/prompts",
            params={"page_size": 50},
        )
        resp.raise_for_status()
        for p in resp.json().get("data", []):
            self._slug_to_id[p["slug"]] = p["id"]

    async def _render_prompt(
        self,
        slug: str,
        variables: dict[str, str],
    ) -> str | None:
        """Render a PromptHub prompt by slug with variables."""
        try:
            await self._ensure_slug_map()
            prompt_id = self._slug_to_id.get(slug)
            if not prompt_id:
                logger.warning(f"PromptHub prompt slug '{slug}' not found")
                return None
            client = await self._get_http_client()
            resp = await client.post(
                f"/api/v1/prompts/{prompt_id}/render",
                json={"variables": variables},
            )
            resp.raise_for_status()
            return resp.json()["data"]["rendered_content"]
        except Exception as e:
            logger.warning(f"Failed to render PromptHub prompt '{slug}': {e}")
            return None

    async def process(
        self,
        prompt: str,
        enhance: bool = False,
        generate_negative: bool = False,
        template_id: str | None = None,
        template_repo: TemplateRepository | None = None,
    ) -> ProcessedPrompt:
        """
        Run the prompt through the processing pipeline.

        Two paths:
        - Path A (template): If template_id is provided, use the template's
          pre-optimized prompt_text directly, skipping translation/enhancement.
        - Path B (manual): Run full pipeline (detect → translate → enhance).

        Both paths share negative prompt generation at the end.

        Args:
            prompt: Raw user prompt
            enhance: Whether to AI-enhance the prompt
            generate_negative: Whether to auto-generate a negative prompt
            template_id: Optional local template ID to apply first
            template_repo: TemplateRepository instance (required if template_id given)

        Returns:
            ProcessedPrompt with all processing results
        """
        start = time.time()
        settings = get_settings()
        result = ProcessedPrompt(original=prompt, final=prompt)
        current = prompt

        # === Path A: Template path ===
        if template_id and template_repo:
            try:
                template = await template_repo.get_by_id(UUID(template_id))
                if template:
                    result.template_used = True
                    result.template_name = template.display_name_en
                    current = template.prompt_text
                    result.final = current
                    result.language_detected = "en"

                    # Record usage (fire-and-forget)
                    try:
                        await template_repo.record_usage(template.id)
                    except Exception as e:
                        logger.debug(f"Failed to record template usage: {e}")
                else:
                    logger.warning(f"Template {template_id} not found, falling back to manual path")
            except Exception as e:
                logger.warning(f"Template lookup failed, falling back to manual path: {e}")

        # === Path B: Manual input path ===
        if not result.template_used:
            # Language detection
            if contains_chinese(current):
                result.language_detected = "zh"
            else:
                result.language_detected = "en"

            # Auto-translation (Chinese -> English)
            if result.language_detected == "zh" and settings.prompt_auto_translate:
                try:
                    translated = await self._translate(current)
                    if translated:
                        result.translated = translated
                        result.was_translated = True
                        current = translated
                        result.final = current
                except Exception as e:
                    logger.warning(f"Translation failed, using original: {e}")

            # Enhancement
            if enhance:
                try:
                    enhanced = await self._enhance(current)
                    if enhanced:
                        result.enhanced = enhanced
                        result.was_enhanced = True
                        current = enhanced
                        result.final = current
                except Exception as e:
                    logger.warning(f"Enhancement failed, using previous: {e}")

        # === Shared: Negative prompt generation ===
        if generate_negative:
            try:
                negative = await self._generate_negative(current)
                if negative:
                    result.negative_prompt = negative
            except Exception as e:
                logger.warning(f"Negative prompt generation failed: {e}")

        result.pipeline_duration = time.time() - start
        return result

    async def _translate(self, text: str) -> str | None:
        """Translate Chinese prompt to English via PromptHub meta prompt + LLM."""
        from services.llm_client import get_llm_client

        meta = await self._render_prompt(
            self._PROMPT_SLUGS["translate_zh"],
            {"chinese_prompt": text, "target_model": "flux", "optimize_for": "quality"},
        )
        if not meta:
            # Fallback system message
            meta = (
                "You are a translator. Translate the following Chinese text to English. "
                "Output ONLY the English translation, nothing else."
            )

        llm = get_llm_client()
        return await llm.generate(prompt=text, system_message=meta, temperature=0.3)

    async def _enhance(self, text: str) -> str | None:
        """Enhance prompt for image generation via PromptHub meta prompt + LLM."""
        from services.llm_client import get_llm_client

        slug = self._PROMPT_SLUGS["enhance_zh" if contains_chinese(text) else "enhance_en"]
        meta = await self._render_prompt(
            slug,
            {"original_prompt": text, "focus_areas": "detail,atmosphere", "preserve_style": "true"},
        )
        if not meta:
            meta = (
                "You are an expert at writing prompts for AI image generation. "
                "Rewrite the following prompt to be more detailed and effective "
                "for image generation. Output ONLY the improved prompt, nothing else."
            )

        llm = get_llm_client()
        return await llm.generate(prompt=text, system_message=meta, temperature=0.7)

    async def _generate_negative(self, text: str) -> str | None:
        """Generate a negative prompt via PromptHub meta prompt + LLM."""
        from services.llm_client import get_llm_client

        slug = self._PROMPT_SLUGS["negative_zh" if contains_chinese(text) else "negative_en"]
        meta = await self._render_prompt(
            slug,
            {"positive_prompt": text, "target_model": "flux", "quality_priority": "balanced"},
        )
        if not meta:
            meta = (
                "You are an expert at AI image generation. Given the following image "
                "generation prompt, generate a negative prompt that describes what should "
                "NOT appear in the image. Output ONLY the negative prompt, nothing else."
            )

        llm = get_llm_client()
        return await llm.generate(prompt=text, system_message=meta, temperature=0.5)


# Singleton
_pipeline: PromptPipeline | None = None


def get_prompt_pipeline() -> PromptPipeline:
    """Get or create the singleton PromptPipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PromptPipeline()
    return _pipeline
