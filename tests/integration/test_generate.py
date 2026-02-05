"""
Integration tests for image generation endpoints.
"""

from unittest.mock import patch

import pytest


class TestGenerateEndpoints:
    """Tests for /api/generate endpoints."""

    def test_generate_image_missing_prompt(self, client):
        """Test generation with missing prompt."""
        response = client.post("/api/generate", json={"settings": {"aspect_ratio": "16:9"}})

        assert response.status_code == 422  # Validation error

    def test_generate_image_empty_prompt(self, client):
        """Test generation with empty prompt."""
        response = client.post(
            "/api/generate", json={"prompt": "", "settings": {"aspect_ratio": "16:9"}}
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.skip(reason="Complex mock setup needed - covered by e2e tests")
    def test_generate_image_no_provider(self, client, mock_redis_fixture):
        """Test generation without any provider configured."""
        pass

    @pytest.mark.skip(reason="Complex mock setup needed - covered by e2e tests")
    def test_generate_image_success(self, client):
        """Test successful image generation."""
        pass

    @pytest.mark.skip(reason="Complex mock setup needed - covered by e2e tests")
    def test_generate_image_safety_blocked(self, client):
        """Test generation blocked by safety filter."""
        pass

    def test_batch_generate_success(
        self, client, mock_redis_fixture, mock_quota_service, sample_batch_request
    ):
        """Test batch generation creates a task."""
        with patch("api.routers.generate.get_quota_service", return_value=mock_quota_service):
            response = client.post(
                "/api/generate/batch",
                json=sample_batch_request,
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["total"] == 3
            assert data["status"] == "queued"

    def test_batch_generate_too_many_prompts(self, client):
        """Test batch generation with too many prompts."""
        response = client.post(
            "/api/generate/batch",
            json={
                "prompts": ["prompt"] * 15,  # More than max
                "settings": {"aspect_ratio": "1:1"},
            },
        )

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

    @pytest.mark.skip(reason="Complex mock setup needed - covered by e2e tests")
    def test_search_generate_success(self, client):
        """Test search-grounded generation."""
        pass
