"""
Unit tests for POST /api/generate/describe endpoint.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


def _make_describe_request(
    image_key="source_key",
    detail_level="standard",
    include_tags=True,
    language="en",
):
    """Build a describe request dict."""
    return {
        "image_key": image_key,
        "detail_level": detail_level,
        "include_tags": include_tags,
        "language": language,
    }


_SENTINEL = object()


def _make_fake_result(success=True, error=None, text_response=_SENTINEL):
    """Build a fake provider result."""
    if text_response is _SENTINEL:
        text_response = (
            (
                "A beautiful sunset over the ocean with warm orange and purple colors. "
                "Tags: sunset, ocean, sky, orange, purple, landscape"
            )
            if success
            else None
        )
    return type(
        "Result",
        (),
        {
            "success": success,
            "image": None,  # describe returns no image
            "error": error,
            "text_response": text_response,
            "duration": 1.5,
            "provider": "google",
            "model": "gemini-3-pro-image-preview",
        },
    )()


@contextmanager
def _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
    """Patch all describe endpoint dependencies (non-DI ones)."""

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


class TestDescribeValidation:
    """Request validation tests."""

    def test_missing_image_key(self, client):
        """Describe without image_key returns 422."""
        response = client.post("/api/generate/describe", json={})
        assert response.status_code == 422

    def test_invalid_detail_level(self, client):
        """Describe with invalid detail_level returns 422."""
        response = client.post(
            "/api/generate/describe",
            json=_make_describe_request(detail_level="ultra"),
        )
        assert response.status_code == 422

    def test_invalid_language(self, client):
        """Describe with invalid language returns 422."""
        response = client.post(
            "/api/generate/describe",
            json=_make_describe_request(language="fr"),
        )
        assert response.status_code == 422


class TestDescribeSuccess:
    """Successful describe tests."""

    def test_describe_standard(self, client, mock_redis, mock_quota_service):
        """Describe with standard detail level succeeds."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert "description" in data
        assert "sunset" in data["description"].lower()
        assert data["provider"] == "google"
        assert data["duration"] > 0

    def test_describe_with_tags(self, client, mock_redis, mock_quota_service):
        """Describe with include_tags=True parses tags from response."""
        source_img = Image.new("RGB", (256, 256), color="blue")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result())

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(include_tags=True),
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tags"]) > 0
        assert "sunset" in data["tags"]
        # Description should not contain the "Tags:" prefix
        assert "Tags:" not in data["description"]

    def test_describe_without_tags(self, client, mock_redis, mock_quota_service):
        """Describe with include_tags=False returns empty tags."""
        source_img = Image.new("RGB", (256, 256), color="green")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        text = "A green field with mountains in the background."
        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result(text_response=text))

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(include_tags=False),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == []
        assert data["description"] == text

    def test_describe_brief(self, client, mock_redis, mock_quota_service):
        """Describe with brief detail level uses brief prompt."""
        source_img = Image.new("RGB", (256, 256), color="yellow")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(text_response="A yellow image.")
        )

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(detail_level="brief", include_tags=False),
            )

        assert response.status_code == 200

        # Verify the prompt contains "brief" style instruction
        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert "1-2 sentences" in provider_request.prompt

    def test_describe_detailed(self, client, mock_redis, mock_quota_service):
        """Describe with detailed level uses comprehensive prompt."""
        source_img = Image.new("RGB", (256, 256), color="purple")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(text_response="A detailed description.")
        )

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(detail_level="detailed", include_tags=False),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert "comprehensive" in provider_request.prompt

    def test_describe_chinese(self, client, mock_redis, mock_quota_service):
        """Describe with language=zh includes Chinese instruction."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(text_response="一幅美丽的日落图片。")
        )

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(language="zh", include_tags=False),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert "中文" in provider_request.prompt

    def test_describe_forces_google_provider(self, client, mock_redis, mock_quota_service):
        """Describe always routes to google provider."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(text_response="Test description.")
        )

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(include_tags=False),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.preferred_provider == "google"
        assert provider_request.edit_mode == "describe"

    def test_describe_passes_image_as_reference(self, client, mock_redis, mock_quota_service):
        """Describe passes the image in reference_images for generate_content."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(return_value=_make_fake_result(text_response="An image."))

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(include_tags=False),
            )

        assert response.status_code == 200

        call_args = router_mock.execute.call_args
        provider_request = call_args.kwargs.get("request") or call_args[0][0]
        assert provider_request.reference_images is not None
        assert len(provider_request.reference_images) == 1


class TestDescribeErrors:
    """Error handling tests."""

    def test_image_not_found(self, client, mock_redis, mock_quota_service):
        """Describe fails with 422 when image is not found."""
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        router_mock = MagicMock()

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(),
            )

        assert response.status_code == 422
        assert "not found" in response.json()["error"]["message"].lower()

    def test_quota_exceeded(self, client, mock_redis):
        """Describe fails with 429 when quota is exceeded."""
        quota_service = MagicMock()
        quota_service.check_quota = AsyncMock(
            return_value=(False, "Daily limit reached", {"used": 50, "limit": 50})
        )

        storage_mock = MagicMock()
        router_mock = MagicMock()

        with _patch_describe_deps(mock_redis, quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(),
            )

        assert response.status_code == 429

    def test_provider_failure(self, client, mock_redis, mock_quota_service):
        """Describe fails with 500 when provider returns error."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(success=False, error="Model overloaded")
        )

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(),
            )

        assert response.status_code == 500

    def test_no_text_response(self, client, mock_redis, mock_quota_service):
        """Describe fails with 500 when provider returns no text."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(
            return_value=_make_fake_result(success=True, text_response=None)
        )

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(),
            )

        assert response.status_code == 500

    def test_no_provider_available(self, client, mock_redis, mock_quota_service):
        """Describe fails with 500 when no provider is available."""
        source_img = Image.new("RGB", (256, 256), color="red")
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=source_img)

        router_mock = MagicMock()
        router_mock.execute = AsyncMock(side_effect=ValueError("No providers configured"))

        with _patch_describe_deps(mock_redis, mock_quota_service, storage_mock, router_mock):
            response = client.post(
                "/api/generate/describe",
                json=_make_describe_request(),
            )

        assert response.status_code == 500
        assert "description" in response.json()["error"]["message"].lower()
