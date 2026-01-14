"""
Integration tests for quota endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestQuotaEndpoints:
    """Tests for /api/quota endpoints."""

    def test_get_quota_status_with_api_key(self, client):
        """Test quota status when user has API key."""
        response = client.get(
            "/api/quota",
            headers={"X-API-Key": "user-api-key"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_trial_mode"] is False

    def test_get_quota_status_trial_mode(self, client, mock_quota_service, mock_redis_fixture):
        """Test quota status in trial mode."""
        with patch("api.routers.quota.get_quota_service", return_value=mock_quota_service):
            response = client.get("/api/quota")

            assert response.status_code == 200
            data = response.json()
            assert "is_trial_mode" in data

    def test_check_quota_allowed(self, client, mock_quota_service, mock_redis_fixture):
        """Test quota check when allowed."""
        with patch("api.routers.quota.get_quota_service", return_value=mock_quota_service):
            response = client.post("/api/quota/check", json={
                "mode": "basic",
                "resolution": "1K",
                "count": 1
            })

            assert response.status_code == 200
            data = response.json()
            assert data["can_generate"] is True

    def test_check_quota_exceeded(self, client, mock_redis_fixture):
        """Test quota check when exceeded."""
        mock_service = MagicMock()
        mock_service.is_trial_enabled = True
        mock_service.check_quota = AsyncMock(return_value=(
            False,
            "Daily quota exceeded",
            {"global_used": 50, "global_limit": 50}
        ))

        with patch("api.routers.quota.get_quota_service", return_value=mock_service):
            response = client.post("/api/quota/check", json={
                "mode": "basic",
                "resolution": "1K",
                "count": 1
            })

            assert response.status_code == 200
            data = response.json()
            assert data["can_generate"] is False
            assert "exceeded" in data["reason"].lower()

    def test_get_quota_config(self, client):
        """Test getting quota configuration."""
        response = client.get("/api/quota/config")

        assert response.status_code == 200
        data = response.json()
        assert "global_daily_quota" in data
        assert "cooldown_seconds" in data
        assert "modes" in data

    def test_check_quota_with_api_key_bypasses(self, client):
        """Test that users with API key bypass quota check."""
        response = client.post(
            "/api/quota/check",
            json={"mode": "basic", "resolution": "1K", "count": 1},
            headers={"X-API-Key": "user-api-key"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["can_generate"] is True
