"""
Integration tests for task cancel endpoint.
"""

import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import MockRedis


@pytest.fixture
def task_redis():
    """Create a fresh MockRedis for task tests."""
    return MockRedis()


@pytest.fixture
def task_client(task_redis):
    """Create a test client with mocked Redis and dependency overrides."""
    from api.main import app
    from core.auth import AppUser, get_current_user

    async def get_mock_redis():
        return task_redis

    mock_user = AppUser(
        id="test-uuid-12345",
        email="test@example.com",
        name="Test User",
        avatar_url=None,
        scopes=["user"],
        raw_payload={},
    )

    # Use FastAPI dependency_overrides for proper injection
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with (
        patch("core.redis.get_redis", get_mock_redis),
        patch("api.routers.tasks.get_redis", get_mock_redis),
    ):
        yield app, task_redis, mock_user

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
class TestCancelBatchTask:
    """Tests for cancelling batch tasks."""

    async def test_cancel_batch_task_mid_progress(self, task_client):
        """Cancel a batch task mid-progress and verify refund."""
        app, redis, user = task_client

        # Set up a batch task in Redis
        task_id = "batch_test123"
        await redis.hset(
            f"task:{task_id}",
            mapping={
                "status": "processing",
                "progress": "2",
                "total": "5",
                "user_id": user.user_folder_id,
                "created_at": "2024-01-01T00:00:00",
            },
        )

        # Consume 5 quota points first
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=redis)
        await service.consume_quota(user_id=user.user_folder_id, count=5)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tasks/{task_id}/cancel")

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_type"] == "batch"
        assert body["previous_status"] == "processing"
        assert body["refunded_count"] == 3  # 5 total - 2 done = 3 pending

        # Verify cancelled flag was set
        cancelled = await redis.hget(f"task:{task_id}", "cancelled")
        assert cancelled == "1"

    async def test_cancel_completed_task(self, task_client):
        """Cancelling a completed task should fail with validation error."""
        app, redis, user = task_client

        task_id = "batch_done456"
        await redis.hset(
            f"task:{task_id}",
            mapping={
                "status": "completed",
                "progress": "5",
                "total": "5",
                "user_id": user.user_folder_id,
            },
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tasks/{task_id}/cancel")

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        assert "already completed" in body["error"]["message"]

    async def test_cancel_nonexistent_task(self, task_client):
        """Cancelling a non-existent task should return 404."""
        app, redis, user = task_client

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tasks/nonexistent_task/cancel")

        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "task_not_found"

    async def test_cancel_other_users_task(self, task_client):
        """Cancelling another user's task should fail."""
        app, redis, user = task_client

        task_id = "batch_other789"
        await redis.hset(
            f"task:{task_id}",
            mapping={
                "status": "processing",
                "progress": "1",
                "total": "3",
                "user_id": "different_user",
            },
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tasks/{task_id}/cancel")

        assert resp.status_code == 422
        body = resp.json()
        assert "own tasks" in body["error"]["message"]


@pytest.mark.asyncio
class TestCancelVideoTask:
    """Tests for cancelling video tasks."""

    async def test_cancel_video_task(self, task_client):
        """Cancel a queued video task and verify refund."""
        app, redis, user = task_client

        task_id = "video_test123"
        video_data = {
            "task_id": task_id,
            "status": "queued",
            "user_id": user.user_folder_id,
            "provider": "runway",
        }
        await redis.setex(f"video_task:{task_id}", 86400, json.dumps(video_data))

        # Consume 1 quota point
        from services.quota_service import QuotaService

        service = QuotaService(redis_client=redis)
        await service.consume_quota(user_id=user.user_folder_id, count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tasks/{task_id}/cancel")

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_type"] == "video"
        assert body["previous_status"] == "queued"
        assert body["refunded_count"] == 1

    async def test_cancel_completed_video_task(self, task_client):
        """Cancelling a completed video task should fail."""
        app, redis, user = task_client

        task_id = "video_done456"
        video_data = {
            "task_id": task_id,
            "status": "completed",
            "user_id": user.user_folder_id,
        }
        await redis.setex(f"video_task:{task_id}", 86400, json.dumps(video_data))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tasks/{task_id}/cancel")

        assert resp.status_code == 422
        body = resp.json()
        assert "already completed" in body["error"]["message"]
