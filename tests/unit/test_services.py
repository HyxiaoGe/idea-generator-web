"""
Unit tests for services module.
"""

from unittest.mock import patch

import pytest


class TestQuotaService:
    """Tests for QuotaService."""

    @pytest.mark.asyncio
    async def test_check_quota_allowed(self, mock_redis):
        """Test quota check when allowed."""
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=mock_redis)

        can_generate, reason, info = await service.check_quota(
            user_id="test_user", mode="basic", resolution="1K", count=1
        )

        assert can_generate is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_consume_quota(self, mock_redis):
        """Test quota consumption."""
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=mock_redis)

        result = await service.consume_quota(
            user_id="test_user", mode="basic", resolution="1K", count=1
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_get_quota_status(self, mock_redis):
        """Test getting quota status."""
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=mock_redis)

        status = await service.get_quota_status("test_user")

        assert "global_limit" in status
        assert "modes" in status

    def test_get_mode_key_basic(self):
        """Test mode key for basic generation."""
        from services.quota_service import QuotaService

        service = QuotaService()

        assert service.get_mode_key("basic", "1K") == "basic_1k"
        assert service.get_mode_key("basic", "4K") == "basic_4k"

    def test_get_mode_key_batch(self):
        """Test mode key for batch generation."""
        from services.quota_service import QuotaService

        service = QuotaService()

        assert service.get_mode_key("batch", "1K") == "batch_1k"
        assert service.get_mode_key("batch", "4K") == "batch_4k"


class TestAuthService:
    """Tests for AuthService."""

    def test_auth_service_not_configured(self):
        """Test auth service when not configured."""
        with patch.dict(
            "os.environ", {"GITHUB_CLIENT_ID": "", "GITHUB_CLIENT_SECRET": ""}, clear=False
        ):
            from services.auth_service import AuthService

            service = AuthService()

            assert service.is_configured is False

    def test_auth_service_configured(self):
        """Test auth service when properly configured."""
        with patch.dict(
            "os.environ",
            {
                "GITHUB_CLIENT_ID": "test_client_id",
                "GITHUB_CLIENT_SECRET": "test_secret",
                "AUTH_ENABLED": "true",
            },
            clear=False,
        ):
            from services.auth_service import AuthService

            service = AuthService()

            assert service.is_configured is True

    def test_get_authorization_url(self):
        """Test authorization URL generation."""
        with patch.dict(
            "os.environ",
            {
                "GITHUB_CLIENT_ID": "test_client_id",
                "GITHUB_CLIENT_SECRET": "test_secret",
                "GITHUB_REDIRECT_URI": "http://localhost:8000/callback",
            },
            clear=False,
        ):
            from services.auth_service import AuthService

            service = AuthService()

            url = service.get_authorization_url(state="test_state")

            assert "github.com" in url
            assert "client_id=test_client_id" in url
            assert "state=test_state" in url

    def test_github_user_properties(self):
        """Test GitHubUser properties."""
        from services.auth_service import GitHubUser

        user = GitHubUser(
            id="12345",
            login="testuser",
            name="Test User",
            email="test@example.com",
            avatar_url="https://github.com/testuser.png",
        )

        assert user.display_name == "Test User"
        assert user.user_folder_id is not None
        assert len(user.user_folder_id) == 16

    def test_github_user_display_name_fallback(self):
        """Test display name falls back to login."""
        from services.auth_service import GitHubUser

        user = GitHubUser(id="12345", login="testuser", name=None, email=None, avatar_url=None)

        assert user.display_name == "testuser"

    def test_github_user_to_dict(self):
        """Test GitHubUser serialization."""
        from services.auth_service import GitHubUser

        user = GitHubUser(
            id="12345",
            login="testuser",
            name="Test User",
            email="test@example.com",
            avatar_url=None,
        )

        data = user.to_dict()

        assert data["id"] == "12345"
        assert data["login"] == "testuser"
        assert data["name"] == "Test User"
        assert "user_folder_id" in data


class TestCostEstimator:
    """Tests for cost_estimator service."""

    def test_estimate_cost_basic(self):
        """Test cost estimation for basic generation."""
        from services.cost_estimator import estimate_cost

        estimate = estimate_cost(resolution="1K", count=1)

        assert estimate is not None
        assert estimate.count == 1
        assert estimate.resolution == "1K"

    def test_estimate_cost_multiple(self):
        """Test cost estimation for multiple images."""
        from services.cost_estimator import estimate_cost

        estimate = estimate_cost(resolution="1K", count=5)

        assert estimate.count == 5
        assert estimate.total_cost == estimate.unit_cost * 5

    def test_format_cost(self):
        """Test cost formatting."""
        from services.cost_estimator import estimate_cost, format_cost

        estimate = estimate_cost(resolution="1K", count=1)
        formatted = format_cost(estimate)

        assert "$" in formatted
        assert "0.04" in formatted or "Est" in formatted


class TestHealthCheck:
    """Tests for health check service."""

    def test_health_status_enum(self):
        """Test HealthStatus enum values."""
        from services.health_check import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"

    def test_health_check_result(self):
        """Test HealthCheckResult dataclass."""
        from services.health_check import HealthCheckResult, HealthStatus

        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="All systems operational",
            response_time=50.5,
        )

        assert result.status == HealthStatus.HEALTHY
        assert result.response_time == 50.5
        assert result.message == "All systems operational"

    def test_health_check_result_to_dict(self):
        """Test HealthCheckResult serialization."""
        from services.health_check import HealthCheckResult, HealthStatus

        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="OK",
            response_time=25.0,
            timestamp=1234567890.0,
        )

        data = result.to_dict()

        assert data["status"] == "healthy"
        assert data["message"] == "OK"
        assert data["response_time"] == 25.0


class TestGeneratorHelpers:
    """Tests for generator helper functions."""

    def test_is_retryable_error_true(self):
        """Test retryable error detection."""
        from services.generator import is_retryable_error

        assert is_retryable_error("server disconnected") is True
        assert is_retryable_error("Connection timeout") is True
        assert is_retryable_error("503 Service Unavailable") is True

    def test_is_retryable_error_false(self):
        """Test non-retryable error detection."""
        from services.generator import is_retryable_error

        assert is_retryable_error("Invalid API key") is False
        assert is_retryable_error("Content blocked") is False

    def test_classify_error(self):
        """Test error classification."""
        from services.generator import classify_error

        assert classify_error("503 Service Unavailable overloaded") == "overloaded"
        assert classify_error("Request timeout") == "timeout"
        assert classify_error("API_KEY_INVALID") == "invalid_key"
        assert classify_error("Content blocked by safety filter") == "safety_blocked"

    def test_get_friendly_error_message(self):
        """Test friendly error message generation."""
        from services.generator import get_friendly_error_message

        msg = get_friendly_error_message("503 Service Unavailable")

        assert msg is not None
        assert len(msg) > 0

    def test_build_safety_settings(self):
        """Test safety settings builder."""
        from services.generator import build_safety_settings

        settings = build_safety_settings("moderate")

        assert settings is not None
        assert len(settings) > 0

    def test_build_safety_settings_all_levels(self):
        """Test all safety level options."""
        from services.generator import build_safety_settings

        for level in ["strict", "moderate", "relaxed", "none"]:
            settings = build_safety_settings(level)
            assert settings is not None
