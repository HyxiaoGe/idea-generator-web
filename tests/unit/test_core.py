"""
Unit tests for core module.
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


class TestSettings:
    """Tests for core.config settings."""

    def test_settings_defaults(self):
        """Test default settings values."""
        with patch.dict(os.environ, {"SECRET_KEY": "test-key-32-characters-long!!!!!"}, clear=False):
            from core.config import Settings
            settings = Settings()

            assert settings.app_name == "Nano Banana Lab"
            assert settings.environment == "development"
            assert settings.debug is True

    def test_settings_from_env(self, monkeypatch):
        """Test settings loaded from environment."""
        monkeypatch.setenv("APP_NAME", "Test App")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DEBUG", "false")
        monkeypatch.setenv("SECRET_KEY", "production-secret-key-32chars!!")

        from core.config import Settings
        settings = Settings()

        assert settings.app_name == "Test App"
        assert settings.environment == "production"
        assert settings.debug is False

    def test_is_production(self, monkeypatch):
        """Test is_production property."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "test-key-32-characters-long!!!!!")

        from core.config import Settings
        settings = Settings()

        assert settings.is_production is True

    def test_cors_origins_parsing(self, monkeypatch):
        """Test CORS origins are parsed correctly."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
        monkeypatch.setenv("SECRET_KEY", "test-key-32-characters-long!!!!!")

        from core.config import Settings
        settings = Settings()

        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:8080" in settings.cors_origins


class TestSecurity:
    """Tests for core.security module."""

    def test_create_access_token(self):
        """Test JWT token creation."""
        from core.security import create_access_token

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-32-characters!!!!"}, clear=False):
            token = create_access_token(data={"sub": "user123", "login": "testuser"})

            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 0

    def test_verify_token_valid(self):
        """Test JWT token verification with valid token."""
        from core.security import create_access_token, verify_token

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-32-characters!!!!"}, clear=False):
            token = create_access_token(data={"sub": "user123", "login": "testuser"})
            payload = verify_token(token)

            assert payload["sub"] == "user123"
            assert payload["login"] == "testuser"

    def test_verify_token_expired(self):
        """Test JWT token verification with expired token."""
        from core.security import create_access_token, verify_token
        from core.exceptions import AuthenticationError

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-32-characters!!!!"}, clear=False):
            # Create token with negative expiry
            token = create_access_token(
                data={"sub": "user123"},
                expires_delta=timedelta(seconds=-100)
            )

            with pytest.raises(AuthenticationError):
                verify_token(token)

    def test_verify_token_invalid(self):
        """Test JWT token verification with invalid token."""
        from core.security import verify_token
        from core.exceptions import AuthenticationError

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-32-characters!!!!"}, clear=False):
            with pytest.raises(AuthenticationError):
                verify_token("invalid.token.here")

    def test_generate_user_folder_id(self):
        """Test user folder ID generation."""
        from core.security import generate_user_folder_id

        folder_id = generate_user_folder_id("12345", "github")

        assert folder_id is not None
        assert isinstance(folder_id, str)
        assert len(folder_id) == 16  # First 16 chars of hash

    def test_generate_user_folder_id_consistency(self):
        """Test that same input produces same folder ID."""
        from core.security import generate_user_folder_id

        id1 = generate_user_folder_id("12345", "github")
        id2 = generate_user_folder_id("12345", "github")

        assert id1 == id2

    def test_generate_user_folder_id_uniqueness(self):
        """Test that different inputs produce different folder IDs."""
        from core.security import generate_user_folder_id

        id1 = generate_user_folder_id("12345", "github")
        id2 = generate_user_folder_id("67890", "github")

        assert id1 != id2


class TestExceptions:
    """Tests for core.exceptions module."""

    def test_app_exception(self):
        """Test AppException creation."""
        from core.exceptions import AppException

        exc = AppException(
            message="Test error",
            error_code="TEST_ERROR",
            status_code=400,
            details={"field": "value"}
        )

        assert exc.message == "Test error"
        assert exc.error_code == "TEST_ERROR"
        assert exc.status_code == 400
        assert exc.details == {"field": "value"}

    def test_authentication_error(self):
        """Test AuthenticationError creation."""
        from core.exceptions import AuthenticationError

        exc = AuthenticationError(message="Invalid token")

        assert exc.message == "Invalid token"
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_quota_exceeded_error(self):
        """Test QuotaExceededError creation."""
        from core.exceptions import QuotaExceededError

        exc = QuotaExceededError(
            message="Daily quota exceeded",
            details={"used": 50, "limit": 50}
        )

        assert exc.message == "Daily quota exceeded"
        assert exc.status_code == 429
        assert exc.details["used"] == 50

    def test_generation_error(self):
        """Test GenerationError creation."""
        from core.exceptions import GenerationError

        exc = GenerationError(message="Generation failed")

        assert exc.message == "Generation failed"
        assert exc.status_code == 500
        assert exc.error_code == "GENERATION_ERROR"

    def test_not_found_error(self):
        """Test NotFoundError creation."""
        from core.exceptions import NotFoundError

        exc = NotFoundError(message="Resource not found")

        assert exc.message == "Resource not found"
        assert exc.status_code == 404
