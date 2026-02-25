"""
Unit tests for Alibaba (Wanxiang) image editing capabilities.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from services.providers.alibaba import AlibabaProvider
from services.providers.types import (
    GenerationRequest,
    ProviderCapability,
    ProviderConfig,
    TaskInfo,
)


def _make_test_image(width=256, height=256, color="red"):
    return Image.new("RGB", (width, height), color=color)


def _mock_submit_response(task_id="task-abc"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "output": {"task_id": task_id, "task_status": "PENDING"},
        "request_id": "req-123",
    }
    return resp


class TestImageEditModelDefinition:
    """Test wanx2.1-imageedit model definition."""

    def test_model_exists(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        model = provider.get_model_by_id("wanx2.1-imageedit")
        assert model is not None
        assert model.id == "wanx2.1-imageedit"

    def test_has_inpainting(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        model = provider.get_model_by_id("wanx2.1-imageedit")
        assert ProviderCapability.INPAINTING in model.capabilities

    def test_has_outpainting(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        model = provider.get_model_by_id("wanx2.1-imageedit")
        assert ProviderCapability.OUTPAINTING in model.capabilities

    def test_has_style_transfer(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        model = provider.get_model_by_id("wanx2.1-imageedit")
        assert ProviderCapability.STYLE_TRANSFER in model.capabilities

    def test_text_to_image_models_unchanged(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        for mid in ["qwen-image", "wan2.6-t2i"]:
            model = provider.get_model_by_id(mid)
            assert model is not None
            assert ProviderCapability.TEXT_TO_IMAGE in model.capabilities


class TestAlibabaInpaint:
    """Test inpainting via wanx2.1-imageedit."""

    @pytest.mark.asyncio
    async def test_inpaint_submits_to_image2image_endpoint(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_submit_response())

        with (
            patch.object(provider, "_get_client", return_value=mock_client),
            patch.object(
                provider,
                "wait_for_completion",
                return_value=TaskInfo(
                    task_id="task-abc",
                    status="completed",
                    result_url="https://example.com/result.png",
                ),
            ),
            patch.object(provider, "download_result", return_value=b"fake-image-data"),
            patch("services.providers.china_base.Image.open") as mock_open,
        ):
            mock_open.return_value = _make_test_image(color="green")
            request = GenerationRequest(
                prompt="Remove the tree",
                reference_images=[_make_test_image()],
                mask_image=_make_test_image(color="white"),
                edit_mode="inpaint_remove",
            )
            result = await provider.generate(request, model_id="wanx2.1-imageedit")

        assert result.success
        call_args = mock_client.post.call_args
        assert "/services/aigc/image2image/image-synthesis" in call_args[0][0]

        payload = call_args.kwargs.get("json", call_args[1].get("json", {}))
        assert payload["parameters"]["function"] == "inpainting"
        assert "image_url" in payload["input"]
        assert "mask_url" in payload["input"]

    @pytest.mark.asyncio
    async def test_inpaint_without_mask(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_submit_response())

        with (
            patch.object(provider, "_get_client", return_value=mock_client),
            patch.object(
                provider,
                "wait_for_completion",
                return_value=TaskInfo(
                    task_id="task-abc",
                    status="completed",
                    result_url="https://example.com/result.png",
                ),
            ),
            patch.object(provider, "download_result", return_value=b"fake-image-data"),
            patch("services.providers.china_base.Image.open") as mock_open,
        ):
            mock_open.return_value = _make_test_image(color="green")
            request = GenerationRequest(
                prompt="Remove object",
                reference_images=[_make_test_image()],
                edit_mode="inpaint_insert",
            )
            result = await provider.generate(request, model_id="wanx2.1-imageedit")

        assert result.success
        payload = mock_client.post.call_args.kwargs.get(
            "json", mock_client.post.call_args[1].get("json", {})
        )
        assert "mask_url" not in payload["input"]

    @pytest.mark.asyncio
    async def test_edit_requires_reference_image(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_submit_response())

        with patch.object(provider, "_get_client", return_value=mock_client):
            request = GenerationRequest(
                prompt="Edit something",
                edit_mode="inpaint_insert",
                # no reference_images
            )
            result = await provider.generate(request, model_id="wanx2.1-imageedit")

        assert not result.success
        assert "reference image" in result.error.lower()


class TestAlibabaOutpaint:
    """Test outpainting via wanx2.1-imageedit."""

    @pytest.mark.asyncio
    async def test_outpaint_uses_outpainting_function(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_submit_response())

        with (
            patch.object(provider, "_get_client", return_value=mock_client),
            patch.object(
                provider,
                "wait_for_completion",
                return_value=TaskInfo(
                    task_id="task-abc",
                    status="completed",
                    result_url="https://example.com/result.png",
                ),
            ),
            patch.object(provider, "download_result", return_value=b"fake-image-data"),
            patch("services.providers.china_base.Image.open") as mock_open,
        ):
            mock_open.return_value = _make_test_image(color="green")
            request = GenerationRequest(
                prompt="Extend the landscape",
                reference_images=[_make_test_image()],
                edit_mode="outpaint",
            )
            result = await provider.generate(request, model_id="wanx2.1-imageedit")

        assert result.success
        payload = mock_client.post.call_args.kwargs.get(
            "json", mock_client.post.call_args[1].get("json", {})
        )
        assert payload["parameters"]["function"] == "outpainting"


class TestAlibabaStyleEdit:
    """Test style/description editing (default edit mode)."""

    @pytest.mark.asyncio
    async def test_style_edit_uses_description_edit_function(self):
        provider = AlibabaProvider(ProviderConfig(api_key="test-key"))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_submit_response())

        with (
            patch.object(provider, "_get_client", return_value=mock_client),
            patch.object(
                provider,
                "wait_for_completion",
                return_value=TaskInfo(
                    task_id="task-abc",
                    status="completed",
                    result_url="https://example.com/result.png",
                ),
            ),
            patch.object(provider, "download_result", return_value=b"fake-image-data"),
            patch("services.providers.china_base.Image.open") as mock_open,
        ):
            mock_open.return_value = _make_test_image(color="green")
            request = GenerationRequest(
                prompt="Make it look like watercolor",
                reference_images=[_make_test_image()],
                # no explicit edit_mode → defaults to description_edit
            )
            result = await provider.generate(request, model_id="wanx2.1-imageedit")

        assert result.success
        payload = mock_client.post.call_args.kwargs.get(
            "json", mock_client.post.call_args[1].get("json", {})
        )
        assert payload["parameters"]["function"] == "description_edit"


class TestAlibabaImageToDataUrl:
    """Test the _image_to_data_url helper."""

    def test_produces_valid_data_url(self):
        img = _make_test_image()
        data_url = AlibabaProvider._image_to_data_url(img)
        assert data_url.startswith("data:image/png;base64,")
        # Verify the base64 portion is decodable
        import base64

        b64_part = data_url.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert len(decoded) > 0
