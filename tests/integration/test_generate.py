"""
Integration tests for image generation endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from PIL import Image


class TestGenerateEndpoints:
    """Tests for /api/generate endpoints."""

    def test_generate_image_missing_prompt(self, client):
        """Test generation with missing prompt."""
        response = client.post("/api/generate", json={
            "settings": {"aspect_ratio": "16:9"}
        })

        assert response.status_code == 422  # Validation error

    def test_generate_image_empty_prompt(self, client):
        """Test generation with empty prompt."""
        response = client.post("/api/generate", json={
            "prompt": "",
            "settings": {"aspect_ratio": "16:9"}
        })

        assert response.status_code == 422  # Validation error

    def test_generate_image_no_api_key(self, client, mock_redis_fixture):
        """Test generation without API key configured."""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": ""}, clear=False):
            with patch("api.routers.generate.get_settings") as mock_settings:
                mock_settings.return_value.google_api_key = None

                response = client.post("/api/generate", json={
                    "prompt": "A beautiful sunset",
                    "settings": {"aspect_ratio": "16:9", "resolution": "1K"}
                })

                assert response.status_code == 400

    def test_generate_image_success(
        self, client, mock_image_generator, mock_r2_storage,
        mock_quota_service, mock_redis_fixture, sample_generate_request
    ):
        """Test successful image generation."""
        with patch("api.routers.generate.create_generator", return_value=mock_image_generator):
            with patch("api.routers.generate.get_r2_storage", return_value=mock_r2_storage):
                with patch("api.routers.generate.get_quota_service", return_value=mock_quota_service):
                    response = client.post(
                        "/api/generate",
                        json=sample_generate_request,
                        headers={"X-API-Key": "test-api-key"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert "image" in data
                    assert "prompt" in data
                    assert "duration" in data

    def test_generate_image_safety_blocked(
        self, client, mock_r2_storage, mock_redis_fixture
    ):
        """Test generation blocked by safety filter."""
        from services.generator import GenerationResult

        mock_generator = MagicMock()
        mock_generator.generate.return_value = GenerationResult(
            image=None,
            error="Content blocked by safety filter",
            safety_blocked=True,
            duration=0.5
        )

        with patch("api.routers.generate.create_generator", return_value=mock_generator):
            with patch("api.routers.generate.get_r2_storage", return_value=mock_r2_storage):
                response = client.post(
                    "/api/generate",
                    json={"prompt": "inappropriate content"},
                    headers={"X-API-Key": "test-api-key"}
                )

                assert response.status_code == 400
                assert "blocked" in response.json()["detail"].lower() or "safety" in response.json()["detail"].lower()

    def test_batch_generate_success(
        self, client, mock_redis_fixture, mock_quota_service, sample_batch_request
    ):
        """Test batch generation creates a task."""
        with patch("api.routers.generate.get_quota_service", return_value=mock_quota_service):
            response = client.post(
                "/api/generate/batch",
                json=sample_batch_request,
                headers={"X-API-Key": "test-api-key"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["total"] == 3
            assert data["status"] == "queued"

    def test_batch_generate_too_many_prompts(self, client):
        """Test batch generation with too many prompts."""
        response = client.post("/api/generate/batch", json={
            "prompts": ["prompt"] * 15,  # More than max
            "settings": {"aspect_ratio": "1:1"}
        })

        assert response.status_code == 422

    def test_get_task_progress_not_found(self, client, mock_redis_fixture):
        """Test getting progress for non-existent task."""
        response = client.get("/api/generate/task/nonexistent_task_id")

        assert response.status_code == 404

    def test_get_task_progress_success(self, client, mock_redis):
        """Test getting task progress."""
        import json

        # Set up task in mock redis
        task_data = {
            "status": "processing",
            "progress": "2",
            "total": "5",
            "current_prompt": "test prompt",
            "results": json.dumps([]),
            "errors": json.dumps([]),
            "started_at": "2024-01-01T12:00:00",
        }
        mock_redis._hashes["task:test_task_id"] = task_data

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.generate.get_redis", mock_get_redis):
            response = client.get("/api/generate/task/test_task_id")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "processing"
            assert data["progress"] == 2
            assert data["total"] == 5

    def test_search_generate_success(
        self, client, mock_image_generator, mock_r2_storage,
        mock_quota_service, mock_redis_fixture
    ):
        """Test search-grounded generation."""
        with patch("api.routers.generate.create_generator", return_value=mock_image_generator):
            with patch("api.routers.generate.get_r2_storage", return_value=mock_r2_storage):
                with patch("api.routers.generate.get_quota_service", return_value=mock_quota_service):
                    response = client.post(
                        "/api/generate/search",
                        json={
                            "prompt": "Latest iPhone design",
                            "settings": {"aspect_ratio": "16:9"}
                        },
                        headers={"X-API-Key": "test-api-key"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert "image" in data
                    assert data["mode"] == "search"
