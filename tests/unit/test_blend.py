"""
Unit tests for POST /api/generate/blend endpoint.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


def _make_blend_request(image_keys=None, blend_prompt=None, settings=None):
    """Build a blend request dict."""
    req = {"image_keys": image_keys or ["key1", "key2"]}
    if blend_prompt is not None:
        req["blend_prompt"] = blend_prompt
    if settings is not None:
        req["settings"] = settings
    return req


def _make_fake_result(success=True, error=None):
    """Build a fake provider result."""
    img = Image.new("RGB", (512, 512), color="blue") if success else None
    return type(
        "Result",
        (),
        {
            "success": success,
            "image": img,
            "error": error,
            "text_response": "Blended image",
            "duration": 2.5,
            "provider": "google",
            "model": "gemini-2.0-flash-preview-image-generation",
        },
    )()


def _make_storage_obj():
    """Build a fake storage object."""
    return type(
        "StorageObj",
        (),
        {
            "key": "blend_abc123",
            "filename": "blend_abc123.png",
            "public_url": "http://localhost/images/blend_abc123.png",
        },
    )()


@contextmanager
def _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
    """Patch all blend endpoint dependencies (non-DI ones)."""

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


class TestBlendValidation:
    """Request validation tests."""

    def test_missing_image_keys(self, client):
        """Blend request without image_keys returns 422."""
        response = client.post("/api/generate/blend", json={})
        assert response.status_code == 422

    def test_too_few_image_keys(self, client):
        """Blend request with only 1 image key returns 422."""
        response = client.post(
            "/api/generate/blend",
            json={"image_keys": ["only_one"]},
        )
        assert response.status_code == 422

    def test_too_many_image_keys(self, client):
        """Blend request with more than 4 image keys returns 422."""
        response = client.post(
            "/api/generate/blend",
            json={"image_keys": ["k1", "k2", "k3", "k4", "k5"]},
        )
        assert response.status_code == 422


class TestBlendSuccess:
    """Successful blend tests."""

    def test_blend_two_images_default_prompt(self, client, mock_redis, mock_quota_service):
        """Blend 2 images with default prompt returns blended image."""
        fake_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "blend"
        assert data["prompt"] == "Blend these images together creatively"
        assert data["image"]["key"] == "blend_abc123"
        assert data["provider"] == "google"

        # Verify load_image called for each key
        assert storage_mock.load_image.call_count == 2
        storage_mock.load_image.assert_any_call("key1")
        storage_mock.load_image.assert_any_call("key2")

    def test_blend_with_custom_prompt(self, client, mock_redis, mock_quota_service):
        """Blend with custom blend_prompt uses that prompt."""
        fake_img = Image.new("RGB", (256, 256), color="green")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(blend_prompt="Merge into a sunset scene"),
            )

        assert response.status_code == 200
        assert response.json()["prompt"] == "Merge into a sunset scene"

    def test_blend_four_images(self, client, mock_redis, mock_quota_service):
        """Blend with 4 images (max allowed) succeeds."""
        fake_img = Image.new("RGB", (256, 256), color="blue")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(image_keys=["a", "b", "c", "d"]),
            )

        assert response.status_code == 200
        assert storage_mock.load_image.call_count == 4

    def test_blend_forces_google_provider(self, client, mock_redis, mock_quota_service):
        """Blend always routes to google provider."""
        fake_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)
        storage_mock.save_image = AsyncMock(return_value=_make_storage_obj())

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(),
            )

        assert response.status_code == 200

        # Verify the provider request was built with google
        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.preferred_provider == "google"

    def test_blend_saves_to_database(self, client, mock_redis, mock_quota_service):
        """Blend saves record to PostgreSQL when repos are available."""
        from api.dependencies import get_image_repository, get_quota_repository
        from api.main import app

        fake_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)
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
            with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
                response = client.post(
                    "/api/generate/blend",
                    json=_make_blend_request(),
                )

            assert response.status_code == 200
            image_repo.create.assert_called_once()
            create_kwargs = image_repo.create.call_args.kwargs
            assert create_kwargs["mode"] == "blend"
            assert create_kwargs["storage_key"] == "blend_abc123"

            quota_repo.record_usage.assert_called_once()
            usage_kwargs = quota_repo.record_usage.call_args.kwargs
            assert usage_kwargs["mode"] == "blend"
        finally:
            app.dependency_overrides.pop(get_image_repository, None)
            app.dependency_overrides.pop(get_quota_repository, None)


class TestBlendErrors:
    """Error handling tests."""

    def test_image_key_not_found(self, client, mock_redis, mock_quota_service):
        """Blend fails with 422 when an image key is not found in storage."""
        storage_mock = MagicMock()
        # First image loads OK, second returns None
        storage_mock.load_image = AsyncMock(side_effect=[Image.new("RGB", (100, 100), "red"), None])

        router_mock = MagicMock()

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(image_keys=["exists", "missing"]),
            )

        assert response.status_code == 422
        assert "missing" in response.json()["error"]["message"].lower()

    def test_quota_exceeded(self, client, mock_redis):
        """Blend fails with 429 when quota is exceeded."""
        quota_service = MagicMock()
        quota_service.check_quota = AsyncMock(
            return_value=(False, "Daily limit reached", {"used": 50, "limit": 50})
        )

        storage_mock = MagicMock()
        router_mock = MagicMock()

        with _patch_blend_deps(mock_redis, quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(),
            )

        assert response.status_code == 429

    def test_provider_failure(self, client, mock_redis, mock_quota_service):
        """Blend fails with 500 when provider returns error."""
        fake_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(success=False, error="Model overloaded")
        )

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(),
            )

        assert response.status_code == 500

    def test_no_provider_available(self, client, mock_redis, mock_quota_service):
        """Blend fails with 500 when no provider is available."""
        fake_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(side_effect=ValueError("No providers configured"))

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(),
            )

        assert response.status_code == 500
        assert "blending" in response.json()["error"]["message"].lower()

    def test_storage_save_failure(self, client, mock_redis, mock_quota_service):
        """Blend fails with 500 when storage save fails."""
        fake_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=fake_img)
        storage_mock.save_image = AsyncMock(side_effect=Exception("Disk full"))

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_blend_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/blend",
                json=_make_blend_request(),
            )

        assert response.status_code == 500
