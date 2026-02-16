"""
Unit tests for the prompt processing pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.prompt_pipeline import ProcessedPrompt, PromptPipeline, contains_chinese

# ============ Chinese Detection ============


class TestContainsChinese:
    def test_pure_chinese(self):
        assert contains_chinese("一只可爱的猫咪") is True

    def test_mixed_chinese_english(self):
        assert contains_chinese("画一个beautiful的日落") is True

    def test_pure_english(self):
        assert contains_chinese("A beautiful sunset over the ocean") is False

    def test_numbers_and_symbols(self):
        assert contains_chinese("1234 !@#$") is False

    def test_japanese_kanji_overlap(self):
        # Japanese kanji overlaps with CJK Unified Ideographs range
        assert contains_chinese("日本語") is True

    def test_empty_string(self):
        assert contains_chinese("") is False

    def test_single_chinese_char(self):
        assert contains_chinese("a 猫 b") is True


# ============ ProcessedPrompt Dataclass ============


class TestProcessedPrompt:
    def test_defaults(self):
        p = ProcessedPrompt(original="hello")
        assert p.original == "hello"
        assert p.translated is None
        assert p.enhanced is None
        assert p.negative_prompt is None
        assert p.final == ""
        assert p.language_detected is None
        assert p.pipeline_duration == 0.0


# ============ Pipeline Passthrough ============


class TestPipelinePassthrough:
    @pytest.mark.asyncio
    async def test_passthrough_when_all_disabled(self):
        """Pipeline returns original prompt when no processing is requested."""
        pipeline = PromptPipeline()

        with patch("services.prompt_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            result = await pipeline.process(
                prompt="A beautiful sunset",
                enhance=False,
                generate_negative=False,
            )

        assert result.original == "A beautiful sunset"
        assert result.final == "A beautiful sunset"
        assert result.translated is None
        assert result.enhanced is None
        assert result.negative_prompt is None
        assert result.language_detected == "en"

    @pytest.mark.asyncio
    async def test_passthrough_chinese_no_translate(self):
        """Chinese prompt passes through when auto_translate is off."""
        pipeline = PromptPipeline()

        with patch("services.prompt_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            result = await pipeline.process(
                prompt="一只可爱的猫咪",
                enhance=False,
                generate_negative=False,
            )

        assert result.final == "一只可爱的猫咪"
        assert result.language_detected == "zh"
        assert result.translated is None


# ============ Template Rendering ============


class TestTemplateRendering:
    @pytest.mark.asyncio
    async def test_template_renders_placeholder(self):
        """Template {{placeholder}} is replaced with user prompt."""
        pipeline = PromptPipeline()

        template_id = str(uuid4())
        mock_template = MagicMock()
        mock_template.id = template_id
        mock_template.prompt_template = "A photo of {{subject}} in cyberpunk style"

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = mock_template
        mock_repo.increment_use_count.return_value = None

        with patch("services.prompt_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            result = await pipeline.process(
                prompt="a cat",
                enhance=False,
                generate_negative=False,
                template_id=template_id,
                template_repo=mock_repo,
            )

        assert result.final == "A photo of a cat in cyberpunk style"
        mock_repo.increment_use_count.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_template_not_found(self):
        """Missing template falls back to original prompt."""
        pipeline = PromptPipeline()

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None

        with patch("services.prompt_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            result = await pipeline.process(
                prompt="a cat",
                enhance=False,
                generate_negative=False,
                template_id=str(uuid4()),
                template_repo=mock_repo,
            )

        assert result.final == "a cat"


# ============ Translation ============


class TestTranslation:
    @pytest.mark.asyncio
    async def test_chinese_auto_translated(self):
        """Chinese prompts are auto-translated when enabled."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", return_value="Translate to English"),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = True
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.return_value = "A cute cat"
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="一只可爱的猫咪",
                enhance=False,
                generate_negative=False,
            )

        assert result.translated == "A cute cat"
        assert result.final == "A cute cat"
        assert result.language_detected == "zh"

    @pytest.mark.asyncio
    async def test_translation_fallback_on_failure(self):
        """Translation failure falls back to original prompt."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", side_effect=RuntimeError("PromptHub down")),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = True
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.side_effect = RuntimeError("LLM failed")
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="一只可爱的猫咪",
                enhance=False,
                generate_negative=False,
            )

        assert result.translated is None
        assert result.final == "一只可爱的猫咪"

    @pytest.mark.asyncio
    async def test_translation_uses_fallback_system_message(self):
        """When PromptHub returns None, a fallback system message is used."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", return_value=None),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = True
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.return_value = "A cute kitten"
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="一只可爱的小猫",
                enhance=False,
                generate_negative=False,
            )

        assert result.translated == "A cute kitten"
        # Verify the fallback system message was used
        call_kwargs = mock_llm.generate.call_args
        assert "translator" in call_kwargs.kwargs["system_message"].lower()


# ============ Enhancement ============


class TestEnhancement:
    @pytest.mark.asyncio
    async def test_enhancement_applied(self):
        """Enhancement rewrites the prompt via LLM."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", return_value="Enhance this prompt"),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.return_value = (
                "A breathtaking sunset over a calm ocean, golden hour lighting, "
                "dramatic clouds, photorealistic, 8k"
            )
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="A sunset over the ocean",
                enhance=True,
                generate_negative=False,
            )

        assert result.enhanced is not None
        assert "breathtaking" in result.enhanced
        assert result.final == result.enhanced

    @pytest.mark.asyncio
    async def test_enhancement_failure_keeps_previous(self):
        """Enhancement failure falls back to the pre-enhancement prompt."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", side_effect=RuntimeError("PromptHub down")),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.side_effect = RuntimeError("LLM failed")
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="A sunset",
                enhance=True,
                generate_negative=False,
            )

        assert result.enhanced is None
        assert result.final == "A sunset"


# ============ Negative Prompt ============


class TestNegativePrompt:
    @pytest.mark.asyncio
    async def test_negative_prompt_generated(self):
        """Negative prompt is generated via LLM."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", return_value="Generate negative prompt"),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.return_value = "blurry, low quality, distorted, watermark"
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="A portrait photo",
                enhance=False,
                generate_negative=True,
            )

        assert result.negative_prompt == "blurry, low quality, distorted, watermark"
        assert result.final == "A portrait photo"  # final is not affected

    @pytest.mark.asyncio
    async def test_negative_prompt_failure_returns_none(self):
        """Negative prompt failure results in None, not an exception."""
        pipeline = PromptPipeline()

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", side_effect=RuntimeError("PromptHub down")),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate.side_effect = RuntimeError("LLM failed")
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="A portrait photo",
                enhance=False,
                generate_negative=True,
            )

        assert result.negative_prompt is None
        assert result.final == "A portrait photo"


# ============ Full Pipeline ============


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_translate_then_enhance(self):
        """Full pipeline: translate Chinese -> enhance English."""
        pipeline = PromptPipeline()

        call_count = 0

        async def mock_generate(prompt, system_message=None, temperature=0.7, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "A cute cat"  # translation
            elif call_count == 2:
                return "A fluffy cute cat, studio lighting, sharp focus"  # enhancement
            return "unknown"

        with (
            patch("services.prompt_pipeline.get_settings") as mock_settings,
            patch.object(pipeline, "_render_prompt", return_value="meta prompt"),
            patch("services.llm_client.get_llm_client") as mock_get_llm,
        ):
            settings = MagicMock()
            settings.prompt_auto_translate = True
            mock_settings.return_value = settings

            mock_llm = AsyncMock()
            mock_llm.generate = mock_generate
            mock_get_llm.return_value = mock_llm

            result = await pipeline.process(
                prompt="一只可爱的猫咪",
                enhance=True,
                generate_negative=False,
            )

        assert result.language_detected == "zh"
        assert result.translated == "A cute cat"
        assert result.enhanced == "A fluffy cute cat, studio lighting, sharp focus"
        assert result.final == result.enhanced
        assert result.pipeline_duration > 0

    @pytest.mark.asyncio
    async def test_pipeline_duration_tracked(self):
        """Pipeline duration is recorded."""
        pipeline = PromptPipeline()

        with patch("services.prompt_pipeline.get_settings") as mock_settings:
            settings = MagicMock()
            settings.prompt_auto_translate = False
            mock_settings.return_value = settings

            result = await pipeline.process(
                prompt="test",
                enhance=False,
                generate_negative=False,
            )

        assert result.pipeline_duration >= 0
