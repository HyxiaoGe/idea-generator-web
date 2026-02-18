"""
Unit tests for core module.
"""

import os
from unittest.mock import patch


class TestSettings:
    """Tests for core.config settings."""

    def test_settings_defaults(self):
        """Test default settings values."""
        with patch.dict(
            os.environ, {"SECRET_KEY": "test-key-32-characters-long!!!!!"}, clear=False
        ):
            from core.config import Settings

            settings = Settings()

            assert settings.app_name == "Nano Banana Lab"
            # Environment may vary based on test setup
            assert settings.environment in ["development", "testing", "production"]

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

    def test_cors_origins_default(self):
        """Test CORS origins has a default value."""
        with patch.dict(
            os.environ,
            {"SECRET_KEY": "test-key-32-characters-long!!!!!"},
            clear=False,
        ):
            from core.config import Settings

            settings = Settings()

            # CORS origins should have a default value
            assert settings.cors_origins is not None


class TestSecurity:
    """Tests for core.security module."""

    def test_extract_token_from_header(self):
        """Test token extraction from Authorization header."""
        from core.security import extract_token_from_header

        assert extract_token_from_header("Bearer abc123") == "abc123"
        assert extract_token_from_header("bearer abc123") == "abc123"
        assert extract_token_from_header(None) is None
        assert extract_token_from_header("") is None
        assert extract_token_from_header("Basic abc123") is None
        assert extract_token_from_header("Bearer") is None


class TestAppUser:
    """Tests for core.auth AppUser."""

    def test_app_user_properties(self):
        """Test AppUser properties."""
        from core.auth import AppUser

        user = AppUser(
            id="test-uuid-12345",
            email="test@example.com",
            name="Test User",
            avatar_url="https://example.com/avatar.png",
            scopes=["user"],
            raw_payload={},
        )

        assert user.display_name == "Test User"
        assert user.user_folder_id == "test-uuid-12345"
        assert user.is_admin is False

    def test_app_user_display_name_fallback(self):
        """Test display name falls back to email."""
        from core.auth import AppUser

        user = AppUser(
            id="test-uuid-12345",
            email="test@example.com",
            name=None,
            avatar_url=None,
            scopes=[],
            raw_payload={},
        )

        assert user.display_name == "test@example.com"

    def test_app_user_admin_scope(self):
        """Test admin scope check."""
        from core.auth import AppUser

        admin = AppUser(
            id="admin-uuid",
            email="admin@example.com",
            name="Admin",
            avatar_url=None,
            scopes=["user", "admin"],
            raw_payload={},
        )

        assert admin.is_admin is True

    def test_app_user_folder_id_is_sub(self):
        """Test that user_folder_id is the auth-service sub (UUID)."""
        from core.auth import AppUser

        user = AppUser(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="test@example.com",
            name=None,
            avatar_url=None,
            scopes=[],
            raw_payload={},
        )

        assert user.user_folder_id == "550e8400-e29b-41d4-a716-446655440000"


class TestExceptions:
    """Tests for core.exceptions module."""

    def test_app_exception(self):
        """Test AppException creation."""
        from core.exceptions import AppException

        exc = AppException(
            message="Test error",
            error_code="test_error",
            details={"field": "value"},
        )

        assert exc.message == "Test error"
        assert exc.error_code == "test_error"
        assert exc.status_code == 500  # default
        assert exc.details == {"field": "value"}

    def test_authentication_error(self):
        """Test AuthenticationError creation."""
        from core.exceptions import AuthenticationError

        exc = AuthenticationError(message="Invalid token")

        assert exc.message == "Invalid token"
        assert exc.status_code == 401
        assert exc.error_code == "authentication_failed"

    def test_quota_exceeded_error(self):
        """Test QuotaExceededError creation."""
        from core.exceptions import QuotaExceededError

        exc = QuotaExceededError(message="Daily quota exceeded", details={"used": 50, "limit": 50})

        assert exc.message == "Daily quota exceeded"
        assert exc.status_code == 429
        assert exc.details["used"] == 50

    def test_generation_error(self):
        """Test GenerationError creation."""
        from core.exceptions import GenerationError

        exc = GenerationError(message="Generation failed")

        assert exc.message == "Generation failed"
        assert exc.status_code == 500
        assert exc.error_code == "generation_failed"

    def test_not_found_error(self):
        """Test NotFoundError creation."""
        from core.exceptions import NotFoundError

        exc = NotFoundError(message="Resource not found")

        assert exc.message == "Resource not found"
        assert exc.status_code == 404

    def test_model_unavailable_error(self):
        """Test ModelUnavailableError creation."""
        from core.exceptions import ModelUnavailableError

        exc = ModelUnavailableError()

        assert exc.error_code == "model_unavailable"
        assert exc.status_code == 503
        assert "unavailable" in exc.message.lower()

    def test_model_unavailable_error_custom_message(self):
        """Test ModelUnavailableError with custom message."""
        from core.exceptions import ModelUnavailableError

        exc = ModelUnavailableError(message="GPT-4 is down")

        assert exc.message == "GPT-4 is down"
        assert exc.status_code == 503

    def test_generation_timeout_error(self):
        """Test GenerationTimeoutError creation."""
        from core.exceptions import GenerationTimeoutError

        exc = GenerationTimeoutError()

        assert exc.error_code == "generation_timeout"
        assert exc.status_code == 504
        assert "timed out" in exc.message.lower()

    def test_generation_timeout_error_custom_message(self):
        """Test GenerationTimeoutError with custom message."""
        from core.exceptions import GenerationTimeoutError

        exc = GenerationTimeoutError(message="Provider took too long")

        assert exc.message == "Provider took too long"
        assert exc.status_code == 504

    def test_exception_to_dict(self):
        """Test exception serialization to dict."""
        from core.exceptions import GenerationError

        exc = GenerationError(
            message="Test failure",
            details={"provider": "google"},
        )

        d = exc.to_dict()

        assert d["code"] == "generation_failed"
        assert d["message"] == "Test failure"
        assert d["details"]["provider"] == "google"

    def test_exception_to_dict_no_details(self):
        """Test exception serialization without details."""
        from core.exceptions import TaskNotFoundError

        exc = TaskNotFoundError()
        d = exc.to_dict()

        assert d["code"] == "task_not_found"
        assert "details" not in d
