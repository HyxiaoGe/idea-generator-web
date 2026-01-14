"""
Unit tests for services module.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestQuotaService:
    """Tests for QuotaService."""

    @pytest.mark.asyncio
    async def test_check_quota_allowed(self, mock_redis):
        """Test quota check when allowed."""
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=mock_redis)
        service._trial_enabled = True

        can_generate, reason, info = await service.check_quota(
            user_id="test_user",
            mode="basic",
            resolution="1K",
            count=1
        )

        assert can_generate is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_check_quota_cooldown(self, mock_redis):
        """Test quota check with active cooldown."""
        import time
        from services.quota_service import QuotaService, GENERATION_COOLDOWN

        # Set last generation to now
        mock_redis._hashes["quota:2024-01-01:user:test_user"] = {
            "last_generation": str(time.time())
        }

        service = QuotaService(redis_client=mock_redis)
        service._trial_enabled = True

        can_generate, reason, info = await service.check_quota(
            user_id="test_user",
            mode="basic",
            resolution="1K",
            count=1
        )

        assert can_generate is False
        assert "wait" in reason.lower()

    @pytest.mark.asyncio
    async def test_consume_quota(self, mock_redis):
        """Test quota consumption."""
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=mock_redis)
        service._trial_enabled = True

        result = await service.consume_quota(
            user_id="test_user",
            mode="basic",
            resolution="1K",
            count=1
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_get_quota_status(self, mock_redis):
        """Test getting quota status."""
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=mock_redis)
        service._trial_enabled = True

        status = await service.get_quota_status("test_user")

        assert status["is_trial_mode"] is True
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

    def test_is_trial_mode(self):
        """Test trial mode detection."""
        from services.quota_service import is_trial_mode

        # With API key, not trial mode
        assert is_trial_mode("valid-api-key") is False

        # Without API key, check env
        with patch.dict("os.environ", {"GOOGLE_API_KEY": ""}, clear=False):
            assert is_trial_mode(None) is True


class TestAuthService:
    """Tests for AuthService."""

    def test_auth_service_not_configured(self):
        """Test auth service when not configured."""
        with patch.dict("os.environ", {
            "GITHUB_CLIENT_ID": "",
            "GITHUB_CLIENT_SECRET": ""
        }, clear=False):
            from services.auth_service import AuthService
            service = AuthService()

            assert service.is_configured is False

    def test_auth_service_configured(self):
        """Test auth service when properly configured."""
        with patch.dict("os.environ", {
            "GITHUB_CLIENT_ID": "test_client_id",
            "GITHUB_CLIENT_SECRET": "test_secret",
            "AUTH_ENABLED": "true"
        }, clear=False):
            from services.auth_service import AuthService
            service = AuthService()

            assert service.is_configured is True

    def test_get_authorization_url(self):
        """Test authorization URL generation."""
        with patch.dict("os.environ", {
            "GITHUB_CLIENT_ID": "test_client_id",
            "GITHUB_CLIENT_SECRET": "test_secret",
            "GITHUB_REDIRECT_URI": "http://localhost:8000/callback"
        }, clear=False):
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
            avatar_url="https://github.com/testuser.png"
        )

        assert user.display_name == "Test User"
        assert user.user_folder_id is not None
        assert len(user.user_folder_id) == 16

    def test_github_user_display_name_fallback(self):
        """Test display name falls back to login."""
        from services.auth_service import GitHubUser

        user = GitHubUser(
            id="12345",
            login="testuser",
            name=None,
            email=None,
            avatar_url=None
        )

        assert user.display_name == "testuser"

    def test_github_user_to_dict(self):
        """Test GitHubUser serialization."""
        from services.auth_service import GitHubUser

        user = GitHubUser(
            id="12345",
            login="testuser",
            name="Test User",
            email="test@example.com",
            avatar_url=None
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

        estimate = estimate_cost(
            mode="basic",
            count=1,
            resolution="1K"
        )

        assert estimate is not None
        assert estimate.count == 1

    def test_estimate_cost_batch(self):
        """Test cost estimation for batch generation."""
        from services.cost_estimator import estimate_cost

        estimate = estimate_cost(
            mode="batch",
            count=5,
            resolution="1K"
        )

        assert estimate.count == 5

    def test_format_cost(self):
        """Test cost formatting."""
        from services.cost_estimator import format_cost

        formatted = format_cost(0.05)

        assert "$" in formatted or "USD" in formatted or "0.05" in formatted


class TestHealthCheck:
    """Tests for health check service."""

    def test_health_status_enum(self):
        """Test HealthStatus enum values."""
        from services.health_check import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"

    def test_health_check_result(self):
        """Test HealthCheckResult dataclass."""
        from services.health_check import HealthCheckResult, HealthStatus

        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            latency_ms=50.5,
            message="All systems operational"
        )

        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms == 50.5
        assert result.message == "All systems operational"


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
