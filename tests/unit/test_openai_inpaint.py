"""
Unit tests for OpenAI provider inpainting via /v1/images/edits.
"""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from services.providers.openai import OpenAIProvider
from services.providers.types import (
    GenerationRequest,
    ProviderCapability,
    ProviderConfig,
)


def _make_test_image(width=256, height=256, color="red"):
    """Create a simple test image."""
    return Image.new("RGB", (width, height), color=color)


def _make_b64_image(width=256, height=256, color="blue"):
    """Create a base64 encoded image string."""
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _mock_response(status_code=200, json_data=None):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = {"content-type": "application/json"}
    return resp


class TestOpenAIInpaintCapability:
    """Test that gpt-image-1 declares inpainting capability."""

    def test_gpt_image_1_has_inpainting(self):
        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        model = provider.get_model_by_id("gpt-image-1")
        assert model is not None
        assert ProviderCapability.INPAINTING in model.capabilities
        assert ProviderCapability.IMAGE_TO_IMAGE in model.capabilities

    def test_dalle3_no_inpainting(self):
        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        model = provider.get_model_by_id("dall-e-3")
        assert model is not None
        assert ProviderCapability.INPAINTING not in model.capabilities


class TestOpenAIInpaintGenerate:
    """Test inpaint generation dispatching."""

    @pytest.mark.asyncio
    async def test_inpaint_calls_edit_endpoint(self):
        """Inpaint request should call /images/edits instead of /images/generations."""
        b64_img = _make_b64_image()
        success_response = _mock_response(
            200,
            {"data": [{"b64_json": b64_img}]},
        )

        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Add a cat here",
                edit_mode="inpaint_insert",
                reference_images=[_make_test_image()],
                mask_image=_make_test_image(color="white"),
            )
            result = await provider.generate(request, model_id="gpt-image-1")

        assert result.success
        assert result.image is not None

        # Verify called /images/edits (not /images/generations)
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/images/edits"

    @pytest.mark.asyncio
    async def test_inpaint_without_mask(self):
        """Inpaint without mask should still work (OpenAI allows it)."""
        b64_img = _make_b64_image()
        success_response = _mock_response(
            200,
            {"data": [{"b64_json": b64_img}]},
        )

        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Remove object",
                edit_mode="inpaint_remove",
                reference_images=[_make_test_image()],
                # No mask_image
            )
            result = await provider.generate(request, model_id="gpt-image-1")

        assert result.success

        # Should not have mask in files
        call_kwargs = mock_client.post.call_args
        files = call_kwargs.kwargs.get("files", {})
        assert "mask" not in files

    @pytest.mark.asyncio
    async def test_inpaint_with_mask(self):
        """Inpaint with mask should include mask file."""
        b64_img = _make_b64_image()
        success_response = _mock_response(
            200,
            {"data": [{"b64_json": b64_img}]},
        )

        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Add flowers",
                edit_mode="inpaint_insert",
                reference_images=[_make_test_image()],
                mask_image=_make_test_image(color="white"),
            )
            result = await provider.generate(request, model_id="gpt-image-1")

        assert result.success

        # Should have mask in files
        call_kwargs = mock_client.post.call_args
        files = call_kwargs.kwargs.get("files", {})
        assert "mask" in files

    @pytest.mark.asyncio
    async def test_regular_generate_still_works(self):
        """Non-edit request should still use /images/generations."""
        b64_img = _make_b64_image()
        success_response = _mock_response(
            200,
            {"data": [{"b64_json": b64_img}]},
        )

        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(prompt="A beautiful sunset")
            result = await provider.generate(request, model_id="gpt-image-1")

        assert result.success
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/images/generations"

    @pytest.mark.asyncio
    async def test_inpaint_safety_error(self):
        """Safety error during inpaint should be handled properly."""
        error_response = _mock_response(
            400,
            {"error": {"message": "Content blocked by safety filter"}},
        )

        provider = OpenAIProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=error_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="bad content",
                edit_mode="inpaint_insert",
                reference_images=[_make_test_image()],
            )
            result = await provider.generate(request, model_id="gpt-image-1")

        assert not result.success
        assert result.safety_blocked


class TestMaskConversion:
    """Test OpenAI mask format conversion."""

    def test_mask_white_becomes_transparent(self):
        """White areas in input mask should become transparent in output."""
        # White mask (edit area)
        mask = Image.new("L", (100, 100), color=255)
        mask_bytes = OpenAIProvider._prepare_mask_for_openai(mask)

        # Load result and check alpha
        result = Image.open(BytesIO(mask_bytes))
        assert result.mode == "RGBA"
        # All pixels should be transparent (alpha = 0)
        alpha = result.split()[3]
        assert alpha.getextrema() == (0, 0)

    def test_mask_black_becomes_opaque(self):
        """Black areas in input mask should become opaque in output."""
        # Black mask (keep area)
        mask = Image.new("L", (100, 100), color=0)
        mask_bytes = OpenAIProvider._prepare_mask_for_openai(mask)

        result = Image.open(BytesIO(mask_bytes))
        assert result.mode == "RGBA"
        # All pixels should be opaque (alpha = 255)
        alpha = result.split()[3]
        assert alpha.getextrema() == (255, 255)
