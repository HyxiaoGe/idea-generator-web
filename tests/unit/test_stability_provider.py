"""
Unit tests for Stability AI provider.
"""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from services.providers.stability import StabilityProvider
from services.providers.types import (
    GenerationRequest,
    ProviderCapability,
    ProviderConfig,
)


def _make_test_image(width=256, height=256, color="red"):
    return Image.new("RGB", (width, height), color=color)


def _make_b64_image(width=256, height=256, color="blue"):
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = {"content-type": "application/json"}
    return resp


class TestStabilityModels:
    """Test model definitions and capabilities."""

    def test_has_text_to_image(self):
        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        model = provider.get_model_by_id("sd3.5-large")
        assert model is not None
        assert ProviderCapability.TEXT_TO_IMAGE in model.capabilities

    def test_has_inpainting(self):
        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        model = provider.get_model_by_id("stability-inpaint")
        assert model is not None
        assert ProviderCapability.INPAINTING in model.capabilities

    def test_has_outpainting(self):
        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        model = provider.get_model_by_id("stability-outpaint")
        assert model is not None
        assert ProviderCapability.OUTPAINTING in model.capabilities

    def test_has_upscaling(self):
        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        model = provider.get_model_by_id("stability-upscale")
        assert model is not None
        assert ProviderCapability.UPSCALING in model.capabilities

    def test_default_model_is_sd35(self):
        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        default = provider.get_default_model()
        assert default is not None
        assert default.id == "sd3.5-large"


class TestStabilityTextToImage:
    """Test text-to-image generation."""

    @pytest.mark.asyncio
    async def test_text_to_image_success(self):
        b64_img = _make_b64_image()
        success_response = _mock_response(200, {"image": b64_img})

        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(prompt="A beautiful sunset")
            result = await provider.generate(request, model_id="sd3.5-large")

        assert result.success
        assert result.image is not None
        assert result.provider == "stability"

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/generate/sd3"

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        provider = StabilityProvider(ProviderConfig())
        request = GenerationRequest(prompt="test")
        result = await provider.generate(request)
        assert not result.success
        assert "not configured" in result.error


class TestStabilityInpaint:
    """Test inpainting functionality."""

    @pytest.mark.asyncio
    async def test_inpaint_success(self):
        b64_img = _make_b64_image()
        success_response = _mock_response(200, {"image": b64_img})

        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Add a tree",
                reference_images=[_make_test_image()],
                mask_image=_make_test_image(color="white"),
            )
            result = await provider.generate(request, model_id="stability-inpaint")

        assert result.success
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/edit/inpaint"

    @pytest.mark.asyncio
    async def test_inpaint_no_reference(self):
        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        request = GenerationRequest(prompt="Add tree")
        result = await provider.generate(request, model_id="stability-inpaint")
        assert not result.success
        assert "reference image" in result.error


class TestStabilityOutpaint:
    """Test outpainting functionality."""

    @pytest.mark.asyncio
    async def test_outpaint_success(self):
        b64_img = _make_b64_image()
        success_response = _mock_response(200, {"image": b64_img})

        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Extend the landscape",
                reference_images=[_make_test_image()],
            )
            result = await provider.generate(request, model_id="stability-outpaint")

        assert result.success
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/edit/outpaint"


class TestStabilityUpscale:
    """Test upscaling functionality."""

    @pytest.mark.asyncio
    async def test_upscale_success(self):
        b64_img = _make_b64_image()
        success_response = _mock_response(200, {"image": b64_img})

        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=success_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Enhance",
                reference_images=[_make_test_image()],
            )
            result = await provider.generate(request, model_id="stability-upscale")

        assert result.success
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/upscale/conservative"


class TestStabilitySafetyFilter:
    """Test safety filter handling."""

    @pytest.mark.asyncio
    async def test_content_filtered(self):
        """Artifacts with CONTENT_FILTERED should flag safety."""
        filtered_response = _mock_response(
            200,
            {"artifacts": [{"finishReason": "CONTENT_FILTERED"}]},
        )

        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=filtered_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(prompt="bad content")
            result = await provider.generate(request, model_id="sd3.5-large")

        assert not result.success
        assert result.safety_blocked

    @pytest.mark.asyncio
    async def test_error_response(self):
        error_response = _mock_response(400, {"message": "Invalid prompt"})

        provider = StabilityProvider(ProviderConfig(api_key="sk-test"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=error_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(prompt="test")
            result = await provider.generate(request, model_id="sd3.5-large")

        assert not result.success
        assert "Invalid prompt" in result.error
