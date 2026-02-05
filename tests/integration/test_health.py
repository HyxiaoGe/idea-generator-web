"""
Integration tests for health check endpoints.
"""

from unittest.mock import AsyncMock, patch


class TestHealthEndpoints:
    """Tests for /api/health endpoints."""

    def test_health_check_basic(self, client):
        """Test basic health check endpoint."""
        with patch("core.redis.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            mock_redis.return_value.ping = AsyncMock(return_value=True)

            response = client.get("/api/health")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data

    def test_health_check_live(self, client):
        """Test liveness probe endpoint."""
        response = client.get("/api/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_check_ready(self, client):
        """Test readiness probe endpoint."""
        with patch("core.redis.get_redis", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = AsyncMock()
            mock_redis.return_value.ping = AsyncMock(return_value=True)

            response = client.get("/api/health/ready")

            assert response.status_code == 200

    def test_root_endpoint(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
