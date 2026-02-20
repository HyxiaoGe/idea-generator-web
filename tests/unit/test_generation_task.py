"""
Unit tests for the race-pattern generation task engine.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import MockRedis


@dataclass
class FakeResult:
    success: bool = False
    image: object = None
    error: str | None = None
    error_type: str | None = None
    provider: str = ""
    model: str = ""
    duration: float = 1.0
    cost: float = 0.0
    text_response: str | None = None
    thinking: str | None = None
    search_sources: str | None = None
    retryable: bool = False
    safety_blocked: bool = False


class FakeImage:
    """Minimal image mock."""

    width = 1024
    height = 1024


class FakeProvider:
    """Minimal provider mock."""

    def __init__(self, name, model_id="model-1", delay=0.0, result=None):
        self.name = name
        self.display_name = name
        self.is_available = True
        self._delay = delay
        self._result = result or FakeResult(
            success=True,
            image=FakeImage(),
            provider=name,
            model=model_id,
        )
        self._default_model = MagicMock()
        self._default_model.id = model_id
        self._default_model.name = f"{name} Model"

    async def generate(self, request, model_id=None):
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result

    def get_default_model(self):
        return self._default_model

    def get_model_by_id(self, model_id):
        if model_id == self._default_model.id:
            return self._default_model
        return None

    @property
    def models(self):
        return [self._default_model]


class FakeBreaker:
    def can_execute(self):
        return True

    def record_success(self):
        pass

    def record_failure(self):
        pass


class FakeAdaptive:
    def __init__(self):
        self.latencies = {}
        self.success_rates = {}
        self.costs = {}

    def update(self, provider, success, latency, cost):
        pass

    def score(self, provider, weights=None):
        return 0.5


class FakeRegistry:
    def __init__(self, providers):
        self._providers = {p.name: p for p in providers}

    def get_image_provider(self, name):
        return self._providers.get(name)

    def get_available_image_providers(self):
        return list(self._providers.values())


class FakeRouter:
    def __init__(self, providers):
        self._registry = FakeRegistry(providers)
        self._adaptive = FakeAdaptive()
        self._initialized = True

    def initialize(self):
        pass


def _make_settings(**overrides):
    """Build a fake settings object."""
    defaults = {
        "provider_soft_timeout": 2,
        "provider_stagger_interval": 1,
        "generation_overall_timeout": 10,
        "storage_backend": "local",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


@pytest.fixture
def mock_redis():
    return MockRedis()


# ============ Tests for _race_providers ============


class TestRaceProviders:
    """Tests for the staggered hedged-request race logic."""

    @pytest.mark.asyncio
    async def test_primary_succeeds_within_soft_timeout(self, mock_redis):
        """Primary returns fast — no fallbacks should be started."""
        primary = FakeProvider("google", delay=0.1)
        fallback = FakeProvider("alibaba", delay=0.1)

        router = FakeRouter([primary, fallback])

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch("services.generation_task.get_settings", return_value=_make_settings()),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            mock_ws.return_value = MagicMock(
                send_generate_progress=AsyncMock(return_value=0),
            )
            mock_cb.get.return_value = FakeBreaker()

            from services.generation_task import _race_providers

            # Set up task in Redis
            task_key = "task:gen_test123"
            await mock_redis.hset(task_key, "status", "generating")

            request = MagicMock()
            result = await _race_providers(
                task_id="gen_test123",
                task_key=task_key,
                request=request,
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=["alibaba"],
            )

            assert result is not None
            assert result.success is True
            assert result.provider == "google"

    @pytest.mark.asyncio
    async def test_primary_slow_fallback_wins(self, mock_redis):
        """Primary is slow (exceeds soft timeout), fallback returns faster."""
        primary = FakeProvider("google", delay=5.0)  # slow
        fallback = FakeProvider("alibaba", delay=0.1)  # fast

        router = FakeRouter([primary, fallback])

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch(
                "services.generation_task.get_settings",
                return_value=_make_settings(
                    provider_soft_timeout=1,
                    provider_stagger_interval=1,
                    generation_overall_timeout=10,
                ),
            ),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            mock_ws.return_value = MagicMock(
                send_generate_progress=AsyncMock(return_value=0),
            )
            mock_cb.get.return_value = FakeBreaker()

            from services.generation_task import _race_providers

            task_key = "task:gen_test456"
            await mock_redis.hset(task_key, "status", "generating")

            request = MagicMock()
            result = await _race_providers(
                task_id="gen_test456",
                task_key=task_key,
                request=request,
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=["alibaba"],
            )

            assert result is not None
            assert result.success is True
            assert result.provider == "alibaba"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, mock_redis):
        """All providers return errors — result should be failed."""
        fail_result = FakeResult(success=False, error="Provider error", provider="google")
        primary = FakeProvider("google", delay=0.0, result=fail_result)

        fail_result2 = FakeResult(success=False, error="Provider error", provider="alibaba")
        fallback = FakeProvider("alibaba", delay=0.0, result=fail_result2)

        router = FakeRouter([primary, fallback])

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch(
                "services.generation_task.get_settings",
                return_value=_make_settings(
                    provider_soft_timeout=1,
                    provider_stagger_interval=1,
                    generation_overall_timeout=5,
                ),
            ),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            mock_ws.return_value = MagicMock(
                send_generate_progress=AsyncMock(return_value=0),
            )
            mock_cb.get.return_value = FakeBreaker()

            from services.generation_task import _race_providers

            task_key = "task:gen_fail"
            await mock_redis.hset(task_key, "status", "generating")

            request = MagicMock()
            result = await _race_providers(
                task_id="gen_fail",
                task_key=task_key,
                request=request,
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=["alibaba"],
            )

            assert result is not None
            assert result.success is False
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_cancellation(self, mock_redis):
        """Setting cancelled=1 in Redis should stop the race and return None."""
        primary = FakeProvider("google", delay=5.0)  # slow

        router = FakeRouter([primary])

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch(
                "services.generation_task.get_settings",
                return_value=_make_settings(
                    provider_soft_timeout=1,
                    generation_overall_timeout=10,
                ),
            ),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            mock_ws.return_value = MagicMock(
                send_generate_progress=AsyncMock(return_value=0),
            )
            mock_cb.get.return_value = FakeBreaker()

            from services.generation_task import _race_providers

            task_key = "task:gen_cancel"
            await mock_redis.hset(task_key, "status", "generating")
            # Pre-set cancelled flag
            await mock_redis.hset(task_key, "cancelled", "1")

            request = MagicMock()
            result = await _race_providers(
                task_id="gen_cancel",
                task_key=task_key,
                request=request,
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=[],
            )

            assert result is None
            # Status should be updated to cancelled
            status = await mock_redis.hget(task_key, "status")
            assert status == "cancelled"

    @pytest.mark.asyncio
    async def test_overall_timeout(self, mock_redis):
        """All providers sleep beyond overall_timeout — should fail."""
        primary = FakeProvider("google", delay=20.0)
        fallback = FakeProvider("alibaba", delay=20.0)

        router = FakeRouter([primary, fallback])

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch(
                "services.generation_task.get_settings",
                return_value=_make_settings(
                    provider_soft_timeout=1,
                    provider_stagger_interval=1,
                    generation_overall_timeout=3,
                ),
            ),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            mock_ws.return_value = MagicMock(
                send_generate_progress=AsyncMock(return_value=0),
            )
            mock_cb.get.return_value = FakeBreaker()

            from services.generation_task import _race_providers

            task_key = "task:gen_timeout"
            await mock_redis.hset(task_key, "status", "generating")

            request = MagicMock()
            result = await _race_providers(
                task_id="gen_timeout",
                task_key=task_key,
                request=request,
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=["alibaba"],
            )

            # Should return a failure result (not None)
            assert result is not None
            assert result.success is False


# ============ Tests for execute_generation_race ============


class TestExecuteGenerationRace:
    """Tests for the top-level background task function."""

    @pytest.mark.asyncio
    async def test_success_updates_redis_to_completed(self, mock_redis):
        """On successful generation, Redis status should be 'completed'."""
        primary = FakeProvider("google", delay=0.0)
        router = FakeRouter([primary])

        fake_storage_obj = MagicMock()
        fake_storage_obj.key = "test/img.png"
        fake_storage_obj.filename = "img.png"
        fake_storage_obj.public_url = "http://example.com/img.png"

        fake_storage = MagicMock()
        fake_storage.save_image = AsyncMock(return_value=fake_storage_obj)

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch("services.generation_task.get_settings", return_value=_make_settings()),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task.get_storage_manager", return_value=fake_storage),
            patch("services.generation_task.is_database_available", return_value=False),
            patch("services.generation_task.get_provider_registry") as mock_reg,
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            ws_mock = MagicMock()
            ws_mock.send_generate_progress = AsyncMock(return_value=0)
            ws_mock.send_generate_complete = AsyncMock(return_value=0)
            ws_mock.send_generate_error = AsyncMock(return_value=0)
            mock_ws.return_value = ws_mock
            mock_cb.get.return_value = FakeBreaker()
            mock_reg.return_value = FakeRegistry([primary])

            from services.generation_task import execute_generation_race

            task_id = "gen_success"
            task_key = f"task:{task_id}"
            await mock_redis.hset(
                task_key,
                mapping={
                    "status": "queued",
                    "user_id": "user1",
                },
            )
            await mock_redis.expire(task_key, 86400)

            request = MagicMock()
            await execute_generation_race(
                task_id=task_id,
                request=request,
                original_prompt="test prompt",
                processed_prompt=None,
                negative_prompt=None,
                settings_dict={
                    "aspect_ratio": "16:9",
                    "resolution": "1K",
                    "safety_level": "moderate",
                },
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=[],
                preset_used="balanced",
                template_used=False,
                was_translated=False,
                was_enhanced=False,
                template_name=None,
            )

            status = await mock_redis.hget(task_key, "status")
            assert status == "completed"
            ws_mock.send_generate_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_updates_redis_to_failed(self, mock_redis):
        """On all-providers-fail, Redis status should be 'failed' and quota refunded."""
        fail_result = FakeResult(success=False, error="test error", provider="google")
        primary = FakeProvider("google", delay=0.0, result=fail_result)
        router = FakeRouter([primary])

        mock_quota_svc = MagicMock()
        mock_quota_svc.refund_quota = AsyncMock(return_value=1)

        with (
            patch("services.generation_task.get_redis", AsyncMock(return_value=mock_redis)),
            patch("services.generation_task.get_settings", return_value=_make_settings()),
            patch("services.generation_task.get_provider_router", return_value=router),
            patch("services.generation_task.get_websocket_manager") as mock_ws,
            patch("services.generation_task._get_quota_service", return_value=mock_quota_svc),
            patch("services.generation_task.CircuitBreakerManager") as mock_cb,
        ):
            ws_mock = MagicMock()
            ws_mock.send_generate_progress = AsyncMock(return_value=0)
            ws_mock.send_generate_error = AsyncMock(return_value=0)
            mock_ws.return_value = ws_mock
            mock_cb.get.return_value = FakeBreaker()

            from services.generation_task import execute_generation_race

            task_id = "gen_fail"
            task_key = f"task:{task_id}"
            await mock_redis.hset(
                task_key,
                mapping={
                    "status": "queued",
                    "user_id": "user1",
                },
            )

            request = MagicMock()
            await execute_generation_race(
                task_id=task_id,
                request=request,
                original_prompt="test",
                processed_prompt=None,
                negative_prompt=None,
                settings_dict={
                    "aspect_ratio": "16:9",
                    "resolution": "1K",
                    "safety_level": "moderate",
                },
                user_id="user1",
                primary_provider="google",
                primary_model="model-1",
                fallback_names=[],
                preset_used="balanced",
                template_used=False,
                was_translated=False,
                was_enhanced=False,
                template_name=None,
            )

            status = await mock_redis.hget(task_key, "status")
            assert status == "failed"
            ws_mock.send_generate_error.assert_called_once()
            mock_quota_svc.refund_quota.assert_called_once_with("user1", 1)
