"""
Integration tests for quota endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch


class TestQuotaEndpoints:
    """Tests for /api/quota endpoints."""

    def test_get_quota_status(self, client, mock_quota_service, mock_redis_fixture):
        """Test quota status returns simple daily limit info."""
        with patch("api.routers.quota.get_quota_service", return_value=mock_quota_service):
            response = client.get("/api/quota")

            assert response.status_code == 200
            data = response.json()
            assert "used" in data
            assert "limit" in data
            assert "remaining" in data
            assert "cooldown_active" in data

    def test_check_quota_allowed(self, client, mock_quota_service, mock_redis_fixture):
        """Test quota check when allowed."""
        with patch("api.routers.quota.get_quota_service", return_value=mock_quota_service):
            response = client.post(
                "/api/quota/check",
                json={"count": 1},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["can_generate"] is True

    def test_check_quota_exceeded(self, client, mock_redis_fixture):
        """Test quota check when exceeded."""
        mock_service = MagicMock()
        mock_service.check_quota = AsyncMock(
            return_value=(
                False,
                "Daily limit reached (50/50)",
                {
                    "used": 50,
                    "limit": 50,
                    "remaining": 0,
                },
            )
        )

        with patch("api.routers.quota.get_quota_service", return_value=mock_service):
            response = client.post(
                "/api/quota/check",
                json={"count": 1},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["can_generate"] is False
            assert "limit" in data["reason"].lower() or "daily" in data["reason"].lower()

    def test_get_quota_config(self, client):
        """Test getting quota configuration."""
        response = client.get("/api/quota/config")

        assert response.status_code == 200
        data = response.json()
        assert "daily_limit" in data
        assert "cooldown_seconds" in data
        assert "max_batch_size" in data
        assert data["daily_limit"] == 50
        assert data["cooldown_seconds"] == 3
        assert data["max_batch_size"] == 5
