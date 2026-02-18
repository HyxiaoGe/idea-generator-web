"""
Integration tests for authentication endpoints.
"""


class TestAuthEndpoints:
    """Tests for /api/auth endpoints."""

    def test_get_auth_status(self, client):
        """Test auth status endpoint."""
        response = client.get("/api/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert "authenticated" in data

    def test_get_current_user_unauthenticated(self, client):
        """Test getting current user when not authenticated."""
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_get_current_user_authenticated(self, client, mock_app_user):
        """Test getting current user when authenticated."""
        from api.main import app
        from core.auth import require_current_user

        app.dependency_overrides[require_current_user] = lambda: mock_app_user
        try:
            response = client.get("/api/auth/me")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "test-uuid-12345"
            assert data["email"] == "test@example.com"
            assert data["name"] == "Test User"
            assert data["user_folder_id"] == "test-uuid-12345"
        finally:
            app.dependency_overrides.pop(require_current_user, None)

    def test_logout(self, client, mock_app_user):
        """Test logout endpoint."""
        from api.main import app
        from core.auth import require_current_user

        app.dependency_overrides[require_current_user] = lambda: mock_app_user
        try:
            response = client.post("/api/auth/logout")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
        finally:
            app.dependency_overrides.pop(require_current_user, None)
