"""
Pytest configuration and fixtures.
"""

import pytest
from typing import AsyncGenerator

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from api.main import app


@pytest.fixture
def client() -> TestClient:
    """Synchronous test client."""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def test_settings(monkeypatch):
    """Override settings for testing."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing-only")

    # Clear cached settings
    from core.config import get_settings
    get_settings.cache_clear()

    yield

    # Restore cached settings
    get_settings.cache_clear()
