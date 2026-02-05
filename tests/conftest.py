"""
Pytest configuration and fixtures.
"""

import os
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"


# ============ App Fixtures ============


@pytest.fixture
def client() -> TestClient:
    """Synchronous test client."""
    from api.main import app

    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous test client."""
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ============ Mock Redis ============


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._sets: dict[str, set] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._expiry: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> bool:
        self._data[key] = value
        if ex:
            self._expiry[key] = ex
        return True

    async def delete(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    async def exists(self, key: str) -> int:
        return 1 if key in self._data else 0

    async def expire(self, key: str, seconds: int) -> bool:
        self._expiry[key] = seconds
        return True

    async def hset(
        self, key: str, field: str = None, value: str = None, mapping: dict = None
    ) -> int:
        if key not in self._hashes:
            self._hashes[key] = {}
        if mapping:
            self._hashes[key].update({str(k): str(v) for k, v in mapping.items()})
            return len(mapping)
        if field and value is not None:
            self._hashes[key][field] = str(value)
            return 1
        return 0

    async def hget(self, key: str, field: str) -> str | None:
        if key in self._hashes:
            return self._hashes[key].get(field)
        return None

    async def hgetall(self, key: str) -> dict[str, str]:
        return self._hashes.get(key, {})

    async def hdel(self, key: str, *fields: str) -> int:
        if key not in self._hashes:
            return 0
        count = 0
        for field in fields:
            if field in self._hashes[key]:
                del self._hashes[key][field]
                count += 1
        return count

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        if key not in self._hashes:
            self._hashes[key] = {}
        current = int(self._hashes[key].get(field, 0))
        new_value = current + amount
        self._hashes[key][field] = str(new_value)
        return new_value

    async def incrby(self, key: str, amount: int = 1) -> int:
        current = int(self._data.get(key, 0))
        new_value = current + amount
        self._data[key] = str(new_value)
        return new_value

    async def sadd(self, key: str, *values: str) -> int:
        if key not in self._sets:
            self._sets[key] = set()
        count = 0
        for v in values:
            if v not in self._sets[key]:
                self._sets[key].add(v)
                count += 1
        return count

    async def srem(self, key: str, *values: str) -> int:
        if key not in self._sets:
            return 0
        count = 0
        for v in values:
            if v in self._sets[key]:
                self._sets[key].remove(v)
                count += 1
        return count

    async def smembers(self, key: str) -> set:
        return self._sets.get(key, set())

    def pipeline(self):
        return MockPipeline(self)

    async def close(self):
        pass


class MockPipeline:
    """Mock Redis pipeline."""

    def __init__(self, redis: MockRedis):
        self._redis = redis
        self._commands = []

    def incrby(self, key: str, amount: int):
        self._commands.append(("incrby", key, amount))
        return self

    def hincrby(self, key: str, field: str, amount: int):
        self._commands.append(("hincrby", key, field, amount))
        return self

    def hset(self, key: str, field: str, value: str):
        self._commands.append(("hset", key, field, value))
        return self

    def expire(self, key: str, seconds: int):
        self._commands.append(("expire", key, seconds))
        return self

    async def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == "incrby":
                results.append(await self._redis.incrby(cmd[1], cmd[2]))
            elif cmd[0] == "hincrby":
                results.append(await self._redis.hincrby(cmd[1], cmd[2], cmd[3]))
            elif cmd[0] == "hset":
                results.append(await self._redis.hset(cmd[1], cmd[2], cmd[3]))
            elif cmd[0] == "expire":
                results.append(await self._redis.expire(cmd[1], cmd[2]))
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_redis():
    """Create a mock Redis instance."""
    return MockRedis()


@pytest.fixture
def mock_redis_fixture(mock_redis):
    """Fixture that patches get_redis to return mock."""

    async def get_mock_redis():
        return mock_redis

    with patch("core.redis.get_redis", get_mock_redis):
        with patch("api.routers.generate.get_redis", get_mock_redis):
            with patch("api.routers.chat.get_redis", get_mock_redis):
                with patch("api.routers.quota.get_redis", get_mock_redis):
                    yield mock_redis


# ============ Mock Services ============


@pytest.fixture
def mock_image_generator():
    """Mock ImageGenerator service."""
    from PIL import Image

    from services.generator import GenerationResult

    mock = MagicMock()
    mock.generate.return_value = GenerationResult(
        image=Image.new("RGB", (100, 100), color="red"),
        text="Generated image description",
        thinking=None,
        duration=1.5,
        error=None,
        safety_blocked=False,
    )
    return mock


@pytest.fixture
def mock_r2_storage():
    """Mock R2Storage service."""
    mock = MagicMock()
    mock.is_available = True
    mock.save_image.return_value = "2024/01/01/test_image.png"
    mock.get_public_url.return_value = "https://example.com/images/test_image.png"
    mock.get_history.return_value = [
        {
            "key": "2024/01/01/test_image.png",
            "filename": "test_image.png",
            "prompt": "test prompt",
            "mode": "basic",
            "settings": {"aspect_ratio": "16:9"},
            "duration": 1.5,
            "created_at": datetime.now().isoformat(),
        }
    ]
    return mock


@pytest.fixture
def mock_quota_service():
    """Mock QuotaService."""
    mock = MagicMock()
    mock.is_trial_enabled = True
    mock.check_quota = AsyncMock(return_value=(True, "OK", {"cost": 1, "global_remaining": 49}))
    mock.consume_quota = AsyncMock(return_value=True)
    mock.get_quota_status = AsyncMock(
        return_value={
            "is_trial_mode": True,
            "date": "2024-01-01",
            "global_used": 1,
            "global_limit": 50,
            "global_remaining": 49,
            "modes": {},
            "cooldown_active": False,
            "cooldown_remaining": 0,
        }
    )
    return mock


@pytest.fixture
def mock_auth_service():
    """Mock AuthService."""
    from services.auth_service import GitHubUser

    mock = MagicMock()
    mock.is_available = True
    mock.is_configured = True
    mock.get_authorization_url.return_value = (
        "https://github.com/login/oauth/authorize?client_id=test"
    )
    mock.authenticate = AsyncMock(
        return_value={
            "access_token": "test_jwt_token",
            "token_type": "bearer",
            "user": {
                "id": "12345",
                "login": "testuser",
                "name": "Test User",
                "email": "test@example.com",
                "avatar_url": "https://github.com/testuser.png",
                "user_folder_id": "abc123",
            },
        }
    )
    mock.get_user_from_token.return_value = GitHubUser(
        id="12345",
        login="testuser",
        name="Test User",
        email="test@example.com",
        avatar_url=None,
    )
    return mock


# ============ Test Settings ============


@pytest.fixture
def test_settings(monkeypatch):
    """Override settings for testing."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")
    monkeypatch.setenv("TRIAL_ENABLED", "true")

    # Clear cached settings
    from core.config import get_settings

    get_settings.cache_clear()

    yield

    # Restore cached settings
    get_settings.cache_clear()


# ============ Test Data Fixtures ============


@pytest.fixture
def sample_generate_request():
    """Sample image generation request."""
    return {
        "prompt": "A beautiful sunset over the ocean",
        "settings": {"aspect_ratio": "16:9", "resolution": "1K", "safety_level": "moderate"},
        "include_thinking": False,
    }


@pytest.fixture
def sample_batch_request():
    """Sample batch generation request."""
    return {
        "prompts": ["A red apple on a table", "A blue sky with clouds", "A green forest path"],
        "settings": {"aspect_ratio": "1:1", "resolution": "1K", "safety_level": "moderate"},
    }


@pytest.fixture
def sample_chat_request():
    """Sample chat message request."""
    return {
        "message": "Create an image of a cat",
        "aspect_ratio": "16:9",
        "safety_level": "moderate",
    }


@pytest.fixture
def auth_headers():
    """Sample authentication headers."""
    return {"Authorization": "Bearer test_jwt_token"}
