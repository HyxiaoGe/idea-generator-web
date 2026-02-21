"""
Unit tests for POST /api/generate/inpaint endpoint.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


def _make_inpaint_request(
    image_key="source_key",
    prompt="Fill in the gap",
    mask_key=None,
    mask_mode="user_provided",
    mask_dilation=0.03,
    remove_mode=False,
    negative_prompt=None,
    settings=None,
):
    """Build an inpaint request dict."""
    req = {
        "image_key": image_key,
        "prompt": prompt,
        "mask_mode": mask_mode,
        "mask_dilation": mask_dilation,
        "remove_mode": remove_mode,
    }
    if mask_key is not None:
        req["mask_key"] = mask_key
    if negative_prompt is not None:
        req["negative_prompt"] = negative_prompt
    if settings is not None:
        req["settings"] = settings
    return req


def _make_fake_result(success=True, error=None):
    """Build a fake provider result."""
    img = Image.new("RGB", (512, 512), color="magenta") if success else None
    return type(
        "Result",
        (),
        {
            "success": success,
            "image": img,
            "error": error,
            "text_response": "Inpainted image",
            "duration": 3.0,
            "provider": "google",
            "model": "imagen-3.0-capability-001",
        },
    )()


def _make_storage_obj():
    """Build a fake storage object."""
    return type(
        "StorageObj",
        (),
        {
            "key": "inpaint_abc123",
            "filename": "inpaint_abc123.png",
            "public_url": "http://localhost/images/inpaint_abc123.png",
        },
    )()


@contextmanager
def _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
    """Patch all inpaint endpoint dependencies (non-DI ones)."""

    async def get_mock_redis():
        return mock_redis

    with (
        patch("api.routers.generate.get_redis", get_mock_redis),
        patch("core.redis.get_redis", get_mock_redis),
        patch("api.routers.generate.get_quota_service", return_value=mock_quota_service),
        patch("api.routers.generate.get_storage_manager", return_value=storage_mock),
        patch("api.routers.generate.get_provider_router", return_value=router_mock),
    ):
        yield


class TestInpaintValidation:
    """Request validation tests."""

    def test_missing_image_key(self, client):
        """Inpaint without image_key returns 422."""
        response = client.post("/api/generate/inpaint?sync=true", json={"prompt": "test"})
        assert response.status_code == 422

    def test_missing_prompt(self, client):
        """Inpaint without prompt returns 422."""
        response = client.post("/api/generate/inpaint?sync=true", json={"image_key": "key1"})
        assert response.status_code == 422

    def test_invalid_mask_mode(self, client):
        """Inpaint with invalid mask_mode returns 422."""
        response = client.post(
            "/api/generate/inpaint?sync=true",
            json=_make_inpaint_request(mask_mode="invalid"),
        )
        assert response.status_code == 422

    def test_mask_required_for_user_provided_mode(self, client, mock_redis, mock_quota_service):
        """Inpaint with user_provided mode but no mask_key returns 422."""
        storage_mock = MagicMock()
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_mode="user_provided"),
                # No mask_key provided
            )

        assert response.status_code == 422
        assert "mask_key" in response.json()["error"]["message"].lower()


class TestInpaintSuccess:
    """Successful inpaint tests."""

    def test_inpaint_with_mask(self, client, mock_redis, mock_quota_service):
        """Inpaint with user-provided mask succeeds."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key"),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "inpaint"
        assert data["prompt"] == "Fill in the gap"
        assert data["image"]["key"] == "inpaint_abc123"
        assert data["provider"] == "google"

        # Verify load_image called for source and mask
        assert storage_mock.load_image.call_count == 2
        storage_mock.load_image.assert_any_call("source_key")
        storage_mock.load_image.assert_any_call("mask_key")

    def test_inpaint_foreground_mode_no_mask_key(self, client, mock_redis, mock_quota_service):
        """Inpaint with foreground auto-detect mode works without mask_key."""
        source_img = Image.new("RGB", (256, 256), color="green")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_mode="foreground"),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "inpaint"

        # Verify only source image loaded (no mask)
        assert storage_mock.load_image.call_count == 1

    def test_inpaint_remove_mode(self, client, mock_redis, mock_quota_service):
        """Inpaint with remove_mode=True sends inpaint_remove edit_mode."""
        source_img = Image.new("RGB", (256, 256), color="blue")
        mask_img = Image.new("L", (256, 256), color=128)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key", remove_mode=True),
            )

        assert response.status_code == 200

        # Verify the provider request was built with inpaint_remove
        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.edit_mode == "inpaint_remove"

    def test_inpaint_forces_google_provider(self, client, mock_redis, mock_quota_service):
        """Inpaint always routes to google provider."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key"),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.preferred_provider == "google"

    def test_inpaint_passes_mask_dilation(self, client, mock_redis, mock_quota_service):
        """Inpaint passes mask_dilation parameter to the provider request."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key", mask_dilation=0.1),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.mask_dilation == 0.1


class TestInpaintErrors:
    """Error handling tests."""

    def test_image_not_found(self, client, mock_redis, mock_quota_service):
        """Inpaint fails with 422 when source image is not found."""
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        router_mock = MagicMock()

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_mode="foreground"),
            )

        assert response.status_code == 422
        assert "not found" in response.json()["error"]["message"].lower()

    def test_mask_image_not_found(self, client, mock_redis, mock_quota_service):
        """Inpaint fails with 422 when mask image is not found."""
        source_img = Image.new("RGB", (256, 256), color="red")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, None])

        router_mock = MagicMock()

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="missing_mask"),
            )

        assert response.status_code == 422
        assert "mask" in response.json()["error"]["message"].lower()

    def test_quota_exceeded(self, client, mock_redis):
        """Inpaint fails with 429 when quota is exceeded."""
        quota_service = MagicMock()
        quota_service.check_quota = AsyncMock(
            return_value=(False, "Daily limit reached", {"used": 50, "limit": 50})
        )

        storage_mock = MagicMock()
        router_mock = MagicMock()

        with _patch_inpaint_deps(mock_redis, quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key"),
            )

        assert response.status_code == 429

    def test_provider_failure(self, client, mock_redis, mock_quota_service):
        """Inpaint fails with 500 when provider returns error."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(success=False, error="Model overloaded")
        )

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key"),
            )

        assert response.status_code == 500

    def test_no_provider_available(self, client, mock_redis, mock_quota_service):
        """Inpaint fails with 500 when no provider is available."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(side_effect=ValueError("No providers configured"))

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key"),
            )

        assert response.status_code == 500
        assert "inpainting" in response.json()["error"]["message"].lower()

    def test_storage_save_failure(self, client, mock_redis, mock_quota_service):
        """Inpaint fails with 500 when storage save fails."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(side_effect=Exception("Disk full"))

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_inpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/inpaint?sync=true",
                json=_make_inpaint_request(mask_key="mask_key"),
            )

        assert response.status_code == 500
