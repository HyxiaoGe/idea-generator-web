"""
Unit tests for FLUX provider Fill (inpaint/outpaint) and Kontext (image-to-image).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from services.providers.flux import FluxProvider
from services.providers.types import (
    GenerationRequest,
    ProviderCapability,
    ProviderConfig,
)


def _make_test_image(width=256, height=256, color="red"):
    return Image.new("RGB", (width, height), color=color)


def _mock_submit_response(task_id="task-123"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": task_id}
    resp.headers = {"content-type": "application/json"}
    return resp


def _mock_poll_ready():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "Ready",
        "result": {"sample": "https://example.com/img.png"},
    }
    return resp


def _mock_image_download():
    """Create a mock image download response."""
    img = _make_test_image(color="green")
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="PNG")
    resp = MagicMock()
    resp.status_code = 200
    resp.content = buf.getvalue()
    return resp


class TestFluxModelCapabilities:
    """Test new model definitions."""

    def test_fill_has_inpainting(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        model = provider.get_model_by_id("flux-fill")
        assert model is not None
        assert ProviderCapability.INPAINTING in model.capabilities
        assert ProviderCapability.OUTPAINTING in model.capabilities

    def test_kontext_has_image_to_image(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        model = provider.get_model_by_id("flux-kontext")
        assert model is not None
        assert ProviderCapability.IMAGE_TO_IMAGE in model.capabilities

    def test_text_to_image_models_unchanged(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        for mid in ["flux-2-pro", "flux-1.1-pro", "flux-dev", "flux-schnell"]:
            model = provider.get_model_by_id(mid)
            assert model is not None
            assert ProviderCapability.TEXT_TO_IMAGE in model.capabilities


class TestFluxFill:
    """Test FLUX Fill (inpaint/outpaint)."""

    @pytest.mark.asyncio
    async def test_fill_submits_to_correct_endpoint(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()

        submit_resp = _mock_submit_response()
        poll_resp = _mock_poll_ready()
        download_resp = _mock_image_download()

        mock_client.post = AsyncMock(return_value=submit_resp)
        mock_client.get = AsyncMock(side_effect=[poll_resp, download_resp])

        with patch.object(provider, "_get_client", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                request = GenerationRequest(
                    prompt="Fill this area",
                    reference_images=[_make_test_image()],
                    mask_image=_make_test_image(color="white"),
                )
                result = await provider.generate(request, model_id="flux-fill")

        assert result.success
        # Verify POST was to fill endpoint
        call_args = mock_client.post.call_args
        assert "flux-pro-1.0-fill" in call_args[0][0]

        # Verify payload has image and mask
        payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert "image" in payload
        assert "mask" in payload

    @pytest.mark.asyncio
    async def test_fill_without_mask(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()

        submit_resp = _mock_submit_response()
        poll_resp = _mock_poll_ready()
        download_resp = _mock_image_download()

        mock_client.post = AsyncMock(return_value=submit_resp)
        mock_client.get = AsyncMock(side_effect=[poll_resp, download_resp])

        with patch.object(provider, "_get_client", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                request = GenerationRequest(
                    prompt="Fill area",
                    reference_images=[_make_test_image()],
                    # no mask
                )
                result = await provider.generate(request, model_id="flux-fill")

        assert result.success
        payload = mock_client.post.call_args.kwargs.get(
            "json", mock_client.post.call_args[1].get("json", {})
        )
        assert "mask" not in payload


class TestFluxKontext:
    """Test FLUX Kontext (image-to-image)."""

    @pytest.mark.asyncio
    async def test_kontext_submits_to_correct_endpoint(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()

        submit_resp = _mock_submit_response()
        poll_resp = _mock_poll_ready()
        download_resp = _mock_image_download()

        mock_client.post = AsyncMock(return_value=submit_resp)
        mock_client.get = AsyncMock(side_effect=[poll_resp, download_resp])

        with patch.object(provider, "_get_client", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                request = GenerationRequest(
                    prompt="Make the sky blue",
                    reference_images=[_make_test_image()],
                )
                result = await provider.generate(request, model_id="flux-kontext")

        assert result.success
        call_args = mock_client.post.call_args
        assert "flux-kontext-pro" in call_args[0][0]

        payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert "image" in payload
        assert "prompt" in payload


class TestFluxApiModelNames:
    """Test API model name mapping."""

    def test_fill_api_name(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        assert provider._get_api_model_name("flux-fill") == "flux-pro-1.0-fill"

    def test_kontext_api_name(self):
        provider = FluxProvider(ProviderConfig(api_key="test-key"))
        assert provider._get_api_model_name("flux-kontext") == "flux-kontext-pro"
