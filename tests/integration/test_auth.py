"""
Integration tests for authentication endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch


class TestAuthEndpoints:
    """Tests for /api/auth endpoints."""

    def test_get_auth_status(self, client):
        """Test auth status endpoint."""
        response = client.get("/api/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert "authenticated" in data

    def test_get_login_url_not_configured(self, client):
        """Test login URL when auth not configured."""
        with patch("services.auth_service.get_auth_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.is_available = False
            mock_get_service.return_value = mock_service

            response = client.get("/api/auth/login")

            assert response.status_code == 503

    def test_get_login_url_configured(self, client, mock_auth_service):
        """Test login URL when auth is configured."""
        with patch("api.routers.auth.get_auth_service", return_value=mock_auth_service):
            response = client.get("/api/auth/login")

            assert response.status_code == 200
            data = response.json()
            assert "url" in data
            assert "github.com" in data["url"]

    def test_oauth_callback_missing_code(self, client):
        """Test OAuth callback without code."""
        response = client.post("/api/auth/callback", json={})

        assert response.status_code == 422  # Validation error

    def test_oauth_callback_invalid_code(self, client, mock_auth_service):
        """Test OAuth callback with invalid code."""
        from core.exceptions import AuthenticationError

        mock_auth_service.authenticate = AsyncMock(
            side_effect=AuthenticationError(message="Invalid code")
        )

        with patch("api.routers.auth.get_auth_service", return_value=mock_auth_service):
            response = client.post("/api/auth/callback", json={"code": "invalid"})

            assert response.status_code == 401

    def test_oauth_callback_success(self, client, mock_auth_service):
        """Test successful OAuth callback."""
        with patch("api.routers.auth.get_auth_service", return_value=mock_auth_service):
            response = client.post("/api/auth/callback", json={"code": "valid_code"})

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "user" in data

    def test_get_current_user_unauthenticated(self, client):
        """Test getting current user when not authenticated."""
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_get_current_user_authenticated(self, client, mock_auth_service, auth_headers):
        """Test getting current user when authenticated."""
        with patch("api.routers.auth.get_auth_service", return_value=mock_auth_service):
            response = client.get("/api/auth/me", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "login" in data

    def test_logout(self, client, mock_auth_service, auth_headers):
        """Test logout endpoint."""
        with patch("api.routers.auth.get_auth_service", return_value=mock_auth_service):
            response = client.post("/api/auth/logout", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
