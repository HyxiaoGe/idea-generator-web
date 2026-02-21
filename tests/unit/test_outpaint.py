"""
Unit tests for POST /api/generate/outpaint endpoint.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


def _make_outpaint_request(
    image_key="source_key",
    mask_key="mask_key",
    prompt="Extend this image naturally",
    negative_prompt=None,
    settings=None,
):
    """Build an outpaint request dict."""
    req = {
        "image_key": image_key,
        "mask_key": mask_key,
        "prompt": prompt,
    }
    if negative_prompt is not None:
        req["negative_prompt"] = negative_prompt
    if settings is not None:
        req["settings"] = settings
    return req


def _make_fake_result(success=True, error=None):
    """Build a fake provider result."""
    img = Image.new("RGB", (768, 512), color="cyan") if success else None
    return type(
        "Result",
        (),
        {
            "success": success,
            "image": img,
            "error": error,
            "text_response": "Outpainted image",
            "duration": 4.0,
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
            "key": "outpaint_abc123",
            "filename": "outpaint_abc123.png",
            "public_url": "http://localhost/images/outpaint_abc123.png",
        },
    )()


@contextmanager
def _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
    """Patch all outpaint endpoint dependencies (non-DI ones)."""

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


class TestOutpaintValidation:
    """Request validation tests."""

    def test_missing_image_key(self, client):
        """Outpaint without image_key returns 422."""
        response = client.post(
            "/api/generate/outpaint?sync=true",
            json={"mask_key": "mask_key"},
        )
        assert response.status_code == 422

    def test_missing_mask_key(self, client):
        """Outpaint without mask_key returns 422."""
        response = client.post(
            "/api/generate/outpaint?sync=true",
            json={"image_key": "key1"},
        )
        assert response.status_code == 422


class TestOutpaintSuccess:
    """Successful outpaint tests."""

    def test_outpaint_basic(self, client, mock_redis, mock_quota_service):
        """Outpaint with source and mask succeeds."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (512, 256), color=128)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "outpaint"
        assert data["image"]["key"] == "outpaint_abc123"
        assert data["provider"] == "google"

        # Verify load_image called for source and mask
        assert storage_mock.load_image.call_count == 2
        storage_mock.load_image.assert_any_call("source_key")
        storage_mock.load_image.assert_any_call("mask_key")

    def test_outpaint_with_custom_prompt(self, client, mock_redis, mock_quota_service):
        """Outpaint with custom prompt uses that prompt."""
        source_img = Image.new("RGB", (256, 256), color="green")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(prompt="Extend with a beach scene"),
            )

        assert response.status_code == 200
        assert response.json()["prompt"] == "Extend with a beach scene"

    def test_outpaint_forces_google_provider(self, client, mock_redis, mock_quota_service):
        """Outpaint always routes to google provider."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.preferred_provider == "google"
        assert provider_request.edit_mode == "outpaint"

    def test_outpaint_passes_mask_image(self, client, mock_redis, mock_quota_service):
        """Outpaint passes the mask image in the provider request."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=200)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.mask_image is not None
        assert provider_request.reference_images is not None
        assert len(provider_request.reference_images) == 1

    def test_outpaint_saves_to_database(self, client, mock_redis, mock_quota_service):
        """Outpaint saves record to PostgreSQL when repos are available."""
        from api.dependencies import get_image_repository, get_quota_repository
        from api.main import app

        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        image_repo = MagicMock()
        image_repo.create = AsyncMock(return_value=None)

        quota_repo = MagicMock()
        quota_repo.record_usage = AsyncMock(return_value=None)

        app.dependency_overrides[get_image_repository] = lambda: image_repo
        app.dependency_overrides[get_quota_repository] = lambda: quota_repo

        try:
            with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
                response = client.post(
                    "/api/generate/outpaint?sync=true",
                    json=_make_outpaint_request(),
                )

            assert response.status_code == 200
            image_repo.create.assert_called_once()
            create_kwargs = image_repo.create.call_args.kwargs
            assert create_kwargs["mode"] == "outpaint"
            assert create_kwargs["storage_key"] == "outpaint_abc123"

            quota_repo.record_usage.assert_called_once()
            usage_kwargs = quota_repo.record_usage.call_args.kwargs
            assert usage_kwargs["mode"] == "outpaint"
        finally:
            app.dependency_overrides.pop(get_image_repository, None)
            app.dependency_overrides.pop(get_quota_repository, None)


class TestOutpaintErrors:
    """Error handling tests."""

    def test_source_image_not_found(self, client, mock_redis, mock_quota_service):
        """Outpaint fails with 422 when source image is not found."""
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        router_mock = MagicMock()

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 422
        assert "not found" in response.json()["error"]["message"].lower()

    def test_mask_image_not_found(self, client, mock_redis, mock_quota_service):
        """Outpaint fails with 422 when mask image is not found."""
        source_img = Image.new("RGB", (256, 256), color="red")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, None])

        router_mock = MagicMock()

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 422
        assert "mask" in response.json()["error"]["message"].lower()

    def test_quota_exceeded(self, client, mock_redis):
        """Outpaint fails with 429 when quota is exceeded."""
        quota_service = MagicMock()
        quota_service.check_quota = AsyncMock(
            return_value=(False, "Daily limit reached", {"used": 50, "limit": 50})
        )

        storage_mock = MagicMock()
        router_mock = MagicMock()

        with _patch_outpaint_deps(mock_redis, quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 429

    def test_provider_failure(self, client, mock_redis, mock_quota_service):
        """Outpaint fails with 500 when provider returns error."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(success=False, error="Model overloaded")
        )

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 500

    def test_no_provider_available(self, client, mock_redis, mock_quota_service):
        """Outpaint fails with 500 when no provider is available."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(side_effect=ValueError("No providers configured"))

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 500
        assert "outpainting" in response.json()["error"]["message"].lower()

    def test_storage_save_failure(self, client, mock_redis, mock_quota_service):
        """Outpaint fails with 500 when storage save fails."""
        source_img = Image.new("RGB", (256, 256), color="red")
        mask_img = Image.new("L", (256, 256), color=255)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=[source_img, mask_img])
        storage_mock.save_image = AsyncMock(side_effect=Exception("Disk full"))

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_outpaint_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/outpaint?sync=true",
                json=_make_outpaint_request(),
            )

        assert response.status_code == 500
