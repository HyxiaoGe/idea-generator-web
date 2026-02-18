"""
Unit tests for core.auth module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.auth import AppUser, _to_app_user, get_current_user, require_admin, require_current_user


class TestToAppUser:
    """Tests for _to_app_user conversion."""

    def test_converts_authenticated_user(self):
        """Test conversion from AuthenticatedUser to AppUser."""
        mock_auth_user = MagicMock()
        mock_auth_user.sub = "test-uuid-123"
        mock_auth_user.email = "test@example.com"
        mock_auth_user.scopes = ["user"]
        mock_auth_user.raw_payload = {
            "name": "Test User",
            "avatar_url": "https://example.com/avatar.png",
        }

        user = _to_app_user(mock_auth_user)

        assert isinstance(user, AppUser)
        assert user.id == "test-uuid-123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.avatar_url == "https://example.com/avatar.png"
        assert user.scopes == ["user"]

    def test_handles_missing_optional_fields(self):
        """Test conversion with missing name/avatar_url."""
        mock_auth_user = MagicMock()
        mock_auth_user.sub = "test-uuid-456"
        mock_auth_user.email = "user@example.com"
        mock_auth_user.scopes = []
        mock_auth_user.raw_payload = {}

        user = _to_app_user(mock_auth_user)

        assert user.name is None
        assert user.avatar_url is None


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_returns_none_without_header(self):
        """Test that no Authorization header returns None."""
        result = await get_current_user(authorization=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_with_invalid_format(self):
        """Test that malformed header returns None."""
        result = await get_current_user(authorization="InvalidFormat")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_with_non_bearer(self):
        """Test that non-Bearer scheme returns None."""
        result = await get_current_user(authorization="Basic abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_user_with_valid_token(self):
        """Test successful token verification."""
        mock_validator = MagicMock()
        mock_auth_user = MagicMock()
        mock_auth_user.sub = "test-uuid"
        mock_auth_user.email = "test@example.com"
        mock_auth_user.scopes = ["user"]
        mock_auth_user.raw_payload = {"name": "Test"}
        mock_validator.verify_async = AsyncMock(return_value=mock_auth_user)

        with patch("core.auth.get_validator", return_value=mock_validator):
            result = await get_current_user(authorization="Bearer valid-token")

        assert result is not None
        assert result.id == "test-uuid"

    @pytest.mark.asyncio
    async def test_returns_none_on_verification_failure(self):
        """Test that verification failure returns None."""
        mock_validator = MagicMock()
        mock_validator.verify_async = AsyncMock(side_effect=Exception("Invalid token"))

        with patch("core.auth.get_validator", return_value=mock_validator):
            result = await get_current_user(authorization="Bearer invalid-token")

        assert result is None


class TestRequireCurrentUser:
    """Tests for require_current_user dependency."""

    @pytest.mark.asyncio
    async def test_raises_401_without_auth(self):
        """Test that missing auth raises AuthenticationError."""
        from core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            await require_current_user(authorization=None)

    @pytest.mark.asyncio
    async def test_returns_user_with_valid_auth(self):
        """Test successful auth returns user."""
        mock_validator = MagicMock()
        mock_auth_user = MagicMock()
        mock_auth_user.sub = "test-uuid"
        mock_auth_user.email = "test@example.com"
        mock_auth_user.scopes = ["user"]
        mock_auth_user.raw_payload = {"name": "Test"}
        mock_validator.verify_async = AsyncMock(return_value=mock_auth_user)

        with patch("core.auth.get_validator", return_value=mock_validator):
            result = await require_current_user(authorization="Bearer valid-token")

        assert result.id == "test-uuid"


class TestRequireAdmin:
    """Tests for require_admin dependency."""

    @pytest.mark.asyncio
    async def test_raises_403_for_non_admin(self):
        """Test that non-admin user gets 403."""
        from core.exceptions import AuthorizationError

        mock_validator = MagicMock()
        mock_auth_user = MagicMock()
        mock_auth_user.sub = "user-uuid"
        mock_auth_user.email = "user@example.com"
        mock_auth_user.scopes = ["user"]  # No admin scope
        mock_auth_user.raw_payload = {}
        mock_validator.verify_async = AsyncMock(return_value=mock_auth_user)

        with patch("core.auth.get_validator", return_value=mock_validator):
            with pytest.raises(AuthorizationError):
                await require_admin(authorization="Bearer valid-token")

    @pytest.mark.asyncio
    async def test_returns_admin_user(self):
        """Test that admin user passes through."""
        mock_validator = MagicMock()
        mock_auth_user = MagicMock()
        mock_auth_user.sub = "admin-uuid"
        mock_auth_user.email = "admin@example.com"
        mock_auth_user.scopes = ["user", "admin"]
        mock_auth_user.raw_payload = {"name": "Admin"}
        mock_validator.verify_async = AsyncMock(return_value=mock_auth_user)

        with patch("core.auth.get_validator", return_value=mock_validator):
            result = await require_admin(authorization="Bearer admin-token")

        assert result.is_admin is True
        assert result.id == "admin-uuid"
