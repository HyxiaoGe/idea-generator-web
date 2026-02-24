"""
Unit tests for chat endpoints — focused on POST /api/chat/{session_id}/message (send_message)
and the background task execute_chat_task.

Tests the router layer (async task dispatch) and
the ChatSession class (mock Google SDK with real message processing).
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

# ============ Helpers ============

# Valid UUID for test session IDs (used by background task and router tests)
TEST_SESSION_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _make_send_request(message="Make it more colorful", aspect_ratio=None, safety_level="moderate"):
    """Build a send message request dict."""
    req = {"message": message, "safety_level": safety_level}
    if aspect_ratio:
        req["aspect_ratio"] = aspect_ratio
    return req


def _make_db_session(session_id=TEST_SESSION_UUID, messages=None, aspect_ratio="16:9"):
    """Build a mock DB ChatSession with messages."""
    mock_session = MagicMock()
    mock_session.id = uuid.UUID(session_id)
    mock_session.aspect_ratio = aspect_ratio
    mock_session.created_at = datetime.now()
    mock_session.updated_at = datetime.now()
    mock_session.message_count = len(messages) if messages else 0
    mock_session.messages = messages or []
    return mock_session


def _make_db_message(role, content, image_url=None, thinking=None, thought_signature=None):
    """Build a mock DB ChatMessage."""
    msg = MagicMock()
    msg.role = role
    msg.content = content
    msg.image_url = image_url
    msg.thinking = thinking
    msg.thought_signature = thought_signature
    msg.created_at = datetime.now()
    return msg


def _make_session_data(session_id=TEST_SESSION_UUID, messages=None):
    """Build mock session data dict (used by background task tests)."""
    return {
        "session_id": session_id,
        "aspect_ratio": "16:9",
        "messages": messages or [],
    }


def _make_chat_response(text="Here's the updated image", image=None, thinking=None, error=None):
    """Build a fake ChatResponse."""
    from services.chat_session import ChatResponse

    return ChatResponse(
        text=text,
        image=image,
        thinking=thinking,
        duration=2.5,
        error=error,
        safety_blocked=bool(error and "safety" in error.lower()),
    )


def _make_mock_chat_repo(db_session=None):
    """Build a mock ChatRepository."""
    repo = AsyncMock()
    repo.get_session_with_messages = AsyncMock(return_value=db_session)
    repo.create_session = AsyncMock()
    repo.delete_session = AsyncMock(return_value=db_session is not None)
    repo.list_sessions_by_user = AsyncMock(return_value=[])
    repo.create_message = AsyncMock()
    repo.count_messages_by_session = AsyncMock(return_value=2)
    repo.update_session_latest_image = AsyncMock()
    return repo


@contextmanager
def _patch_send_message_deps(mock_redis, mock_chat_repo):
    """Patch router dependencies for send_message (async mode)."""

    async def get_mock_redis():
        return mock_redis

    with (
        patch("api.routers.chat.get_redis", get_mock_redis),
        patch("core.redis.get_redis", get_mock_redis),
        patch("api.routers.chat.check_quota_and_consume", new_callable=AsyncMock),
        patch("api.routers.chat.execute_chat_task", new_callable=AsyncMock) as mock_task,
    ):
        from api.dependencies import require_chat_repository
        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_chat_repo
        try:
            yield mock_task
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)


# ============ Router Tests: Send Message (Async) ============


class TestSendMessageValidation:
    """Request validation tests for POST /api/chat/{session_id}/message."""

    def _override_chat_repo(self, client):
        """Override require_chat_repository so validation runs first."""
        from api.dependencies import require_chat_repository
        from api.main import app

        mock_repo = _make_mock_chat_repo(db_session=None)
        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        return mock_repo

    def _cleanup(self):
        from api.dependencies import require_chat_repository
        from api.main import app

        app.dependency_overrides.pop(require_chat_repository, None)

    def test_missing_message(self, client, mock_redis):
        """Send without message returns 422."""
        self._override_chat_repo(client)
        try:
            response = client.post("/api/chat/test-session/message", json={})
            assert response.status_code == 422
        finally:
            self._cleanup()

    def test_empty_message(self, client, mock_redis):
        """Send with empty message returns 422."""
        self._override_chat_repo(client)
        try:
            response = client.post(
                "/api/chat/test-session/message",
                json={"message": ""},
            )
            assert response.status_code == 422
        finally:
            self._cleanup()

    def test_message_too_long(self, client, mock_redis):
        """Send with message exceeding max_length returns 422."""
        self._override_chat_repo(client)
        try:
            response = client.post(
                "/api/chat/test-session/message",
                json={"message": "x" * 2001},
            )
            assert response.status_code == 422
        finally:
            self._cleanup()


class TestSendMessageAsync:
    """Tests for the async send_message endpoint."""

    def test_returns_task_id(self, client, mock_redis):
        """Send message returns task_id with queued status."""
        session_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        db_session = _make_db_session(session_id=session_id)
        mock_chat_repo = _make_mock_chat_repo(db_session)

        with _patch_send_message_deps(mock_redis, mock_chat_repo):
            response = client.post(
                f"/api/chat/{session_id}/message",
                json=_make_send_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["task_id"].startswith("chat_")
        assert data["status"] == "queued"

    def test_creates_redis_task(self, client, mock_redis):
        """Send message creates task hash in Redis."""
        session_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        db_session = _make_db_session(session_id=session_id)
        mock_chat_repo = _make_mock_chat_repo(db_session)

        with _patch_send_message_deps(mock_redis, mock_chat_repo):
            response = client.post(
                f"/api/chat/{session_id}/message",
                json=_make_send_request(message="Draw a sunset"),
            )

        task_id = response.json()["task_id"]
        task_data = mock_redis._hashes.get(f"task:{task_id}", {})
        assert task_data["status"] == "queued"
        assert task_data["session_id"] == session_id
        assert task_data["message"] == "Draw a sunset"
        assert task_data["task_type"] == "chat"

    def test_with_aspect_ratio_override(self, client, mock_redis):
        """Send message with aspect_ratio returns task_id."""
        session_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        db_session = _make_db_session(session_id=session_id)
        mock_chat_repo = _make_mock_chat_repo(db_session)

        with _patch_send_message_deps(mock_redis, mock_chat_repo):
            response = client.post(
                f"/api/chat/{session_id}/message",
                json=_make_send_request(aspect_ratio="1:1"),
            )

        assert response.status_code == 200
        assert response.json()["task_id"].startswith("chat_")

    def test_includes_history_in_snapshot(self, client, mock_redis):
        """Send message builds snapshot with existing messages from DB."""
        session_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        messages = [
            _make_db_message("user", "Draw a cat"),
            _make_db_message("assistant", "Here's a cat.", image_url="img/cat.png"),
        ]
        db_session = _make_db_session(session_id=session_id, messages=messages)
        mock_chat_repo = _make_mock_chat_repo(db_session)

        with _patch_send_message_deps(mock_redis, mock_chat_repo) as mock_task:
            response = client.post(
                f"/api/chat/{session_id}/message",
                json=_make_send_request(message="Make it blue"),
            )

        assert response.status_code == 200
        # Verify the background task received session data with history
        call_kwargs = mock_task.call_args.kwargs
        snapshot = json.loads(call_kwargs["session_data_json"])
        assert len(snapshot["messages"]) == 2
        assert snapshot["messages"][0]["role"] == "user"
        assert snapshot["messages"][1]["image_key"] == "img/cat.png"


class TestSendMessageErrors:
    """Error handling tests for send_message."""

    def test_session_not_found(self, client, mock_redis):
        """Send to non-existent session returns 404."""
        mock_chat_repo = _make_mock_chat_repo(db_session=None)

        with _patch_send_message_deps(mock_redis, mock_chat_repo):
            response = client.post(
                "/api/chat/a1b2c3d4-e5f6-7890-abcd-ef1234567890/message",
                json=_make_send_request(),
            )

        assert response.status_code == 404

    def test_quota_exceeded(self, client, mock_redis):
        """Send fails with 429 when quota exceeded."""
        from core.exceptions import QuotaExceededError

        session_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        db_session = _make_db_session(session_id=session_id)
        mock_chat_repo = _make_mock_chat_repo(db_session)

        async def get_mock_redis():
            return mock_redis

        with (
            patch("api.routers.chat.get_redis", get_mock_redis),
            patch("core.redis.get_redis", get_mock_redis),
            patch(
                "api.routers.chat.check_quota_and_consume",
                new_callable=AsyncMock,
                side_effect=QuotaExceededError(
                    message="Daily limit reached",
                    details={"used": 50, "limit": 50},
                ),
            ),
            patch("api.routers.chat.execute_chat_task", new_callable=AsyncMock),
        ):
            from api.dependencies import require_chat_repository
            from api.main import app

            app.dependency_overrides[require_chat_repository] = lambda: mock_chat_repo
            try:
                response = client.post(
                    f"/api/chat/{session_id}/message",
                    json=_make_send_request(),
                )
            finally:
                app.dependency_overrides.pop(require_chat_repository, None)

        assert response.status_code == 429

    def test_no_api_key(self, client, mock_redis):
        """Send fails when no API key is configured."""
        session_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        db_session = _make_db_session(session_id=session_id)
        mock_chat_repo = _make_mock_chat_repo(db_session)

        with _patch_no_api_key(mock_redis, mock_chat_repo):
            response = client.post(
                f"/api/chat/{session_id}/message",
                json=_make_send_request(),
            )

        assert response.status_code == 422


class TestDatabaseRequired:
    """Tests for DB unavailable returning 503."""

    def test_create_session_requires_db(self, client, mock_redis):
        """POST /chat returns 503 when database is unavailable."""

        async def get_mock_redis():
            return mock_redis

        with (
            patch("api.routers.chat.get_redis", get_mock_redis),
            patch("core.redis.get_redis", get_mock_redis),
            patch("api.dependencies.is_database_available", return_value=False),
        ):
            response = client.post(
                "/api/chat",
                json={"aspect_ratio": "16:9"},
            )

        assert response.status_code == 503

    def test_send_message_requires_db(self, client, mock_redis):
        """POST /chat/{id}/message returns 503 when database is unavailable."""

        async def get_mock_redis():
            return mock_redis

        with (
            patch("api.routers.chat.get_redis", get_mock_redis),
            patch("core.redis.get_redis", get_mock_redis),
            patch("api.dependencies.is_database_available", return_value=False),
        ):
            response = client.post(
                "/api/chat/a1b2c3d4-e5f6-7890-abcd-ef1234567890/message",
                json=_make_send_request(),
            )

        assert response.status_code == 503

    def test_list_sessions_requires_db(self, client, mock_redis):
        """GET /chat returns 503 when database is unavailable."""

        async def get_mock_redis():
            return mock_redis

        with (
            patch("api.routers.chat.get_redis", get_mock_redis),
            patch("core.redis.get_redis", get_mock_redis),
            patch("api.dependencies.is_database_available", return_value=False),
        ):
            response = client.get("/api/chat")

        assert response.status_code == 503


@contextmanager
def _patch_no_api_key(mock_redis, mock_chat_repo):
    """Patch for no API key scenario."""

    async def get_mock_redis():
        return mock_redis

    mock_settings = MagicMock()
    mock_settings.get_google_api_key.return_value = None

    with (
        patch("api.routers.chat.get_redis", get_mock_redis),
        patch("core.redis.get_redis", get_mock_redis),
        patch("api.routers.chat.check_quota_and_consume", new_callable=AsyncMock),
        patch("api.routers.chat.get_settings", return_value=mock_settings),
    ):
        from api.dependencies import require_chat_repository
        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_chat_repo
        try:
            yield
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)


# ============ Polling Endpoint Tests ============


class TestGetChatTaskProgress:
    """Tests for GET /api/chat/task/{task_id}."""

    def test_task_not_found(self, client, mock_redis):
        """Polling non-existent task returns 404."""

        async def get_mock_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", get_mock_redis):
            response = client.get("/api/chat/task/chat_nonexistent")

        assert response.status_code == 404

    def test_task_queued(self, client, mock_redis):
        """Polling queued task returns correct status."""
        mock_redis._hashes["task:chat_abc123"] = {
            "status": "queued",
            "stage": "queued",
            "progress": "0.0",
            "user_id": "anonymous",
            "session_id": "test-session",
            "message": "Draw a cat",
            "task_type": "chat",
        }

        async def get_mock_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", get_mock_redis):
            response = client.get("/api/chat/task/chat_abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "chat_abc123"
        assert data["status"] == "queued"
        assert data["progress"] == 0.0
        assert data["result"] is None

    def test_task_completed(self, client, mock_redis):
        """Polling completed task returns result."""
        result_json = json.dumps(
            {
                "text": "Here's your cat!",
                "image": None,
                "thinking": None,
                "duration": 2.5,
                "message_count": 2,
            }
        )
        mock_redis._hashes["task:chat_abc123"] = {
            "status": "completed",
            "stage": "saving",
            "progress": "1.0",
            "result_json": result_json,
            "started_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T00:00:03",
        }

        async def get_mock_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", get_mock_redis):
            response = client.get("/api/chat/task/chat_abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 1.0
        assert data["result"]["text"] == "Here's your cat!"
        assert data["result"]["duration"] == 2.5
        assert data["started_at"] is not None
        assert data["completed_at"] is not None

    def test_task_failed(self, client, mock_redis):
        """Polling failed task returns error."""
        mock_redis._hashes["task:chat_abc123"] = {
            "status": "failed",
            "error": "Model overloaded",
            "error_code": "generation_error",
            "completed_at": "2026-01-01T00:00:03",
        }

        async def get_mock_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", get_mock_redis):
            response = client.get("/api/chat/task/chat_abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Model overloaded"
        assert data["error_code"] == "generation_error"


# ============ Background Task Tests ============


def _make_chat_session_cls_mock(instance_mock):
    """Build a mock ChatSession class with correct class-level constants."""
    from services.chat_session import ChatSession as RealChatSession

    mock_cls = MagicMock(return_value=instance_mock)
    mock_cls.IMAGE_HISTORY_TURNS = RealChatSession.IMAGE_HISTORY_TURNS
    return mock_cls


class TestExecuteChatTask:
    """Tests for execute_chat_task background function."""

    @pytest.fixture
    def mock_redis(self):
        """Fresh mock Redis for background task tests."""
        from tests.conftest import MockRedis

        return MockRedis()

    @pytest.fixture
    def session_data_json(self):
        """Serialized session data."""
        return json.dumps(_make_session_data())

    @pytest.fixture
    def task_redis(self, mock_redis):
        """Set up task hash in Redis (simulates router creating it)."""
        mock_redis._hashes["task:chat_test123"] = {
            "status": "queued",
            "stage": "queued",
            "progress": "0.0",
        }
        return mock_redis

    async def test_success_text_only(self, task_redis, session_data_json):
        """Background task completes with text-only response."""
        from services.chat_task import execute_chat_task

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text="Here's the colorful version."
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        ws_mock = MagicMock()
        ws_mock.send_chat_progress = AsyncMock(return_value=0)
        ws_mock.send_chat_complete = AsyncMock(return_value=0)
        ws_mock.send_chat_error = AsyncMock(return_value=0)

        mock_chat_repo = _make_mock_chat_repo()

        async def get_mock_redis():
            return task_redis

        async def mock_get_session():
            mock_db = MagicMock()
            yield mock_db

        with (
            patch("services.chat_task.get_redis", get_mock_redis),
            patch("services.chat_task.get_websocket_manager", return_value=ws_mock),
            patch("services.chat_task.get_storage_manager", return_value=storage_mock),
            patch(
                "services.chat_task.ChatSession",
                _make_chat_session_cls_mock(chat_mock),
            ),
            patch("services.chat_task.is_database_available", return_value=True),
            patch("services.chat_task.get_session", mock_get_session),
            patch("services.chat_task.ChatRepository", return_value=mock_chat_repo),
            patch("services.chat_task.QuotaRepository"),
        ):
            await execute_chat_task(
                task_id="chat_test123",
                session_id=TEST_SESSION_UUID,
                user_id="anonymous",
                message="Make it colorful",
                aspect_ratio=None,
                safety_level="moderate",
                enable_thinking=False,
                api_key="test-key",
                session_data_json=session_data_json,
            )

        # Verify task completed in Redis
        task_data = task_redis._hashes["task:chat_test123"]
        assert task_data["status"] == "completed"
        assert task_data["progress"] == "1.0"
        assert "result_json" in task_data

        result = json.loads(task_data["result_json"])
        assert result["text"] == "Here's the colorful version."
        assert result["message_count"] == 2

        # Verify DB messages were created
        assert mock_chat_repo.create_message.call_count == 2
        user_call = mock_chat_repo.create_message.call_args_list[0]
        assert user_call.kwargs["role"] == "user"
        assert user_call.kwargs["content"] == "Make it colorful"
        assistant_call = mock_chat_repo.create_message.call_args_list[1]
        assert assistant_call.kwargs["role"] == "assistant"

        # Verify WS complete was called
        ws_mock.send_chat_complete.assert_called_once()

    async def test_success_with_image(self, task_redis, session_data_json):
        """Background task saves image and completes."""
        from services.chat_task import execute_chat_task

        img = Image.new("RGB", (512, 512), color="blue")
        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text="Here's the image.", image=img
        )

        save_result = MagicMock()
        save_result.key = "images/chat/test.png"
        save_result.filename = "test.png"
        save_result.public_url = "https://cdn.example.com/images/chat/test.png"

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)
        storage_mock.save_image = AsyncMock(return_value=save_result)

        ws_mock = MagicMock()
        ws_mock.send_chat_progress = AsyncMock(return_value=0)
        ws_mock.send_chat_complete = AsyncMock(return_value=0)
        ws_mock.send_chat_error = AsyncMock(return_value=0)

        mock_chat_repo = _make_mock_chat_repo()

        async def get_mock_redis():
            return task_redis

        async def mock_get_session():
            mock_db = MagicMock()
            yield mock_db

        with (
            patch("services.chat_task.get_redis", get_mock_redis),
            patch("services.chat_task.get_websocket_manager", return_value=ws_mock),
            patch("services.chat_task.get_storage_manager", return_value=storage_mock),
            patch(
                "services.chat_task.ChatSession",
                _make_chat_session_cls_mock(chat_mock),
            ),
            patch("services.chat_task.is_database_available", return_value=True),
            patch("services.chat_task.get_session", mock_get_session),
            patch("services.chat_task.ChatRepository", return_value=mock_chat_repo),
            patch("services.chat_task.QuotaRepository"),
        ):
            await execute_chat_task(
                task_id="chat_test123",
                session_id=TEST_SESSION_UUID,
                user_id="anonymous",
                message="Draw something",
                aspect_ratio=None,
                safety_level="moderate",
                enable_thinking=False,
                api_key="test-key",
                session_data_json=session_data_json,
            )

        task_data = task_redis._hashes["task:chat_test123"]
        assert task_data["status"] == "completed"
        result = json.loads(task_data["result_json"])
        assert result["image"]["key"] == "images/chat/test.png"
        assert result["image"]["width"] == 512

        # Verify image URL updated in DB
        mock_chat_repo.update_session_latest_image.assert_called_once()

    async def test_generation_error_refunds_quota(self, task_redis, session_data_json):
        """Background task refunds quota on generation error."""
        from services.chat_task import execute_chat_task

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text=None, error="Model overloaded"
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        ws_mock = MagicMock()
        ws_mock.send_chat_progress = AsyncMock(return_value=0)
        ws_mock.send_chat_error = AsyncMock(return_value=0)

        quota_mock = MagicMock()
        quota_mock.refund_quota = AsyncMock()

        async def get_mock_redis():
            return task_redis

        with (
            patch("services.chat_task.get_redis", get_mock_redis),
            patch("services.chat_task.get_websocket_manager", return_value=ws_mock),
            patch("services.chat_task.get_storage_manager", return_value=storage_mock),
            patch(
                "services.chat_task.ChatSession",
                _make_chat_session_cls_mock(chat_mock),
            ),
            patch("services.chat_task.get_quota_service", return_value=quota_mock),
            patch("services.chat_task.is_database_available", return_value=False),
        ):
            await execute_chat_task(
                task_id="chat_test123",
                session_id=TEST_SESSION_UUID,
                user_id="anonymous",
                message="Test",
                aspect_ratio=None,
                safety_level="moderate",
                enable_thinking=False,
                api_key="test-key",
                session_data_json=session_data_json,
            )

        task_data = task_redis._hashes["task:chat_test123"]
        assert task_data["status"] == "failed"
        assert "error" in task_data

        # Verify quota refund
        quota_mock.refund_quota.assert_called_once_with("anonymous", 1)

    async def test_persists_messages_to_db(self, task_redis, session_data_json):
        """Background task persists user and assistant messages to DB."""
        from services.chat_task import execute_chat_task

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="Updated!")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        ws_mock = MagicMock()
        ws_mock.send_chat_progress = AsyncMock(return_value=0)
        ws_mock.send_chat_complete = AsyncMock(return_value=0)
        ws_mock.send_chat_error = AsyncMock(return_value=0)

        mock_chat_repo = _make_mock_chat_repo()
        mock_chat_repo.count_messages_by_session = AsyncMock(return_value=4)

        async def get_mock_redis():
            return task_redis

        async def mock_get_session():
            mock_db = MagicMock()
            yield mock_db

        with (
            patch("services.chat_task.get_redis", get_mock_redis),
            patch("services.chat_task.get_websocket_manager", return_value=ws_mock),
            patch("services.chat_task.get_storage_manager", return_value=storage_mock),
            patch(
                "services.chat_task.ChatSession",
                _make_chat_session_cls_mock(chat_mock),
            ),
            patch("services.chat_task.is_database_available", return_value=True),
            patch("services.chat_task.get_session", mock_get_session),
            patch("services.chat_task.ChatRepository", return_value=mock_chat_repo),
            patch("services.chat_task.QuotaRepository"),
        ):
            await execute_chat_task(
                task_id="chat_test123",
                session_id=TEST_SESSION_UUID,
                user_id="anonymous",
                message="Add a sunset",
                aspect_ratio=None,
                safety_level="moderate",
                enable_thinking=False,
                api_key="test-key",
                session_data_json=session_data_json,
            )

        # Verify DB messages were created
        assert mock_chat_repo.create_message.call_count == 2

        # Verify message_count comes from DB
        result = json.loads(task_redis._hashes["task:chat_test123"]["result_json"])
        assert result["message_count"] == 4

        # No Redis session key should be written
        assert f"chat:anonymous:{TEST_SESSION_UUID}" not in task_redis._data

    async def test_loads_history_images(self, task_redis):
        """Background task loads history images from storage."""
        from services.chat_task import execute_chat_task

        existing_messages = [
            {"role": "user", "content": "Draw a cat", "timestamp": datetime.now().isoformat()},
            {
                "role": "assistant",
                "content": "Here's a cat.",
                "image_key": "img/cat.png",
                "thinking": None,
                "timestamp": datetime.now().isoformat(),
            },
        ]
        session_data_json = json.dumps(_make_session_data(messages=existing_messages))

        cat_img = Image.new("RGB", (64, 64), color="orange")
        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="Blue cat!")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=cat_img)

        ws_mock = MagicMock()
        ws_mock.send_chat_progress = AsyncMock(return_value=0)
        ws_mock.send_chat_complete = AsyncMock(return_value=0)
        ws_mock.send_chat_error = AsyncMock(return_value=0)

        async def get_mock_redis():
            return task_redis

        with (
            patch("services.chat_task.get_redis", get_mock_redis),
            patch("services.chat_task.get_websocket_manager", return_value=ws_mock),
            patch("services.chat_task.get_storage_manager", return_value=storage_mock),
            patch(
                "services.chat_task.ChatSession",
                _make_chat_session_cls_mock(chat_mock),
            ),
            patch("services.chat_task.is_database_available", return_value=False),
        ):
            await execute_chat_task(
                task_id="chat_test123",
                session_id=TEST_SESSION_UUID,
                user_id="anonymous",
                message="Make it blue",
                aspect_ratio=None,
                safety_level="moderate",
                enable_thinking=False,
                api_key="test-key",
                session_data_json=session_data_json,
            )

        # Verify send_message received history_images
        call_kwargs = chat_mock.send_message.call_args.kwargs
        assert "img/cat.png" in call_kwargs["history_images"]


# ============ ChatSession Unit Tests ============


class TestChatSessionInit:
    """ChatSession initialization tests."""

    def test_init_with_api_key(self):
        """ChatSession initializes with provided API key."""
        with patch("services.chat_session.genai") as mock_genai:
            from services.chat_session import ChatSession

            session = ChatSession(api_key="test-key")
            assert session._api_key == "test-key"
            mock_genai.Client.assert_called_once_with(api_key="test-key")

    def test_init_without_api_key_raises(self):
        """ChatSession raises ValueError without API key."""
        with (
            patch("services.chat_session.genai"),
            patch.dict("os.environ", {}, clear=True),
            patch("services.chat_session.os.getenv", return_value=None),
        ):
            from services.chat_session import ChatSession

            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                ChatSession(api_key=None)

    def test_update_api_key(self):
        """update_api_key reinitializes client."""
        with patch("services.chat_session.genai") as mock_genai:
            from services.chat_session import ChatSession

            session = ChatSession(api_key="old-key")
            session.update_api_key("new-key")

            assert session._api_key == "new-key"
            assert mock_genai.Client.call_count == 2  # initial + update


# ============ ChatSession._build_contents Tests ============


class TestBuildContents:
    """Tests for ChatSession._build_contents method."""

    @pytest.fixture
    def session(self):
        """Create a ChatSession with mocked client."""
        with patch("services.chat_session.genai"):
            from services.chat_session import ChatSession

            return ChatSession(api_key="test-key")

    def test_basic_no_history(self, session):
        """With no history, contents has only the new user message."""
        contents = session._build_contents([], "draw a cat")
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "draw a cat"

    def test_with_history(self, session):
        """History messages are correctly mapped to user/model roles."""
        history = [
            {"role": "user", "content": "draw a cat"},
            {"role": "assistant", "content": "here is a cat", "image_key": None},
        ]
        contents = session._build_contents(history, "make it blue")

        assert len(contents) == 3
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "draw a cat"
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "here is a cat"
        assert contents[2].role == "user"
        assert contents[2].parts[0].text == "make it blue"

    def test_with_images_and_signature(self, session):
        """Model images with thought_signature are included."""
        img = Image.new("RGB", (64, 64), color="red")
        history = [
            {"role": "user", "content": "draw a cat"},
            {"role": "assistant", "content": "here is a cat", "image_key": "img/cat.png"},
        ]
        history_images = {"img/cat.png": img}
        history_signatures = {"img/cat.png": b"fake_sig"}

        contents = session._build_contents(
            history, "make it blue", history_images, history_signatures
        )

        model_msg = contents[1]
        assert model_msg.role == "model"
        assert len(model_msg.parts) == 2
        assert model_msg.parts[0].text == "here is a cat"
        assert model_msg.parts[1].inline_data is not None
        assert model_msg.parts[1].inline_data.mime_type == "image/png"
        assert model_msg.parts[1].thought_signature == b"fake_sig"

    def test_model_image_without_signature_skipped(self, session):
        """Model images without thought_signature are skipped (legacy data)."""
        img = Image.new("RGB", (64, 64), color="red")
        history = [
            {"role": "user", "content": "draw a cat"},
            {"role": "assistant", "content": "here is a cat", "image_key": "img/cat.png"},
        ]
        history_images = {"img/cat.png": img}

        contents = session._build_contents(history, "make it blue", history_images)

        # Model message should only have text (image skipped due to missing signature)
        model_msg = contents[1]
        assert model_msg.role == "model"
        assert len(model_msg.parts) == 1
        assert model_msg.parts[0].text == "here is a cat"

    def test_user_image_without_signature_included(self, session):
        """User-uploaded images don't need thought_signature."""
        img = Image.new("RGB", (64, 64), color="blue")
        history = [
            {"role": "user", "content": "edit this", "image_key": "img/upload.png"},
            {"role": "assistant", "content": "done"},
        ]
        history_images = {"img/upload.png": img}

        contents = session._build_contents(history, "more changes", history_images)

        user_msg = contents[0]
        assert user_msg.role == "user"
        assert len(user_msg.parts) == 2
        assert user_msg.parts[1].inline_data is not None

    def test_truncation(self, session):
        """History beyond MAX_HISTORY_TURNS is truncated."""
        # Create 50 messages (25 turns) — exceeds MAX_HISTORY_TURNS=20
        history = []
        for i in range(50):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"msg {i}"})

        contents = session._build_contents(history, "new message")

        # Should be MAX_HISTORY_TURNS*2 from history + 1 new = 41
        assert len(contents) == session.MAX_HISTORY_TURNS * 2 + 1

    def test_old_images_excluded(self, session):
        """Images beyond IMAGE_HISTORY_TURNS are not included."""
        # Create 20 messages (10 turns)
        img = Image.new("RGB", (32, 32), color="green")
        history = []
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            image_key = f"img/{i}.png" if role == "assistant" else None
            history.append({"role": role, "content": f"msg {i}", "image_key": image_key})

        # All assistant images available
        history_images = {f"img/{i}.png": img for i in range(1, 20, 2)}

        contents = session._build_contents(history, "next", history_images)

        # Count how many parts have inline_data
        image_count = sum(
            1
            for content in contents
            for part in content.parts
            if hasattr(part, "inline_data") and part.inline_data is not None
        )

        # Only IMAGE_HISTORY_TURNS turns should have images
        assert image_count <= session.IMAGE_HISTORY_TURNS

    def test_missing_image_key_skipped(self, session):
        """If an image_key isn't in history_images, it's silently skipped."""
        history = [
            {"role": "user", "content": "draw a cat"},
            {"role": "assistant", "content": "here", "image_key": "missing.png"},
        ]
        contents = session._build_contents(history, "again", history_images={})

        # Model message should only have text part
        model_msg = contents[1]
        assert len(model_msg.parts) == 1
        assert model_msg.parts[0].text == "here"


# ============ ChatSession.send_message Tests ============


class TestChatSessionSendMessage:
    """ChatSession.send_message tests with mocked Google SDK."""

    @pytest.fixture
    def session(self):
        """Create a ChatSession with mocked client."""
        with patch("services.chat_session.genai") as mock_genai:
            from services.chat_session import ChatSession

            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            s = ChatSession(api_key="test-key")
            s.aspect_ratio = "16:9"
            yield s

    def _make_text_part(self, text, is_thought=False):
        """Create a mock response part with text."""
        part = MagicMock()
        part.thought = is_thought
        part.text = text
        part.inline_data = None
        return part

    def _make_image_part(self, width=512, height=512, color="red"):
        """Create a mock response part with image data."""
        img = Image.new("RGB", (width, height), color=color)
        buf = BytesIO()
        img.save(buf, format="PNG")

        part = MagicMock()
        part.thought = False
        part.text = None
        part.inline_data = MagicMock()
        part.inline_data.data = buf.getvalue()
        return part

    def _make_api_response(self, parts, finish_reason="STOP"):
        """Create a mock API response."""
        response = MagicMock()
        response.parts = parts
        candidate = MagicMock()
        candidate.finish_reason = finish_reason
        response.candidates = [candidate]
        return response

    def test_send_text_response(self, session):
        """send_message with text-only response."""
        api_response = self._make_api_response([self._make_text_part("Here's what I suggest.")])
        session.client.models.generate_content.return_value = api_response

        result = session.send_message("Make it brighter")

        assert result.text == "Here's what I suggest."
        assert result.image is None
        assert result.error is None
        assert result.duration > 0

    def test_send_image_response(self, session):
        """send_message with image in response."""
        api_response = self._make_api_response(
            [
                self._make_text_part("Here's the image."),
                self._make_image_part(512, 512, "blue"),
            ]
        )
        session.client.models.generate_content.return_value = api_response

        result = session.send_message("Generate a blue sky")

        assert result.text == "Here's the image."
        assert result.image is not None
        assert isinstance(result.image, Image.Image)
        assert result.image.size == (512, 512)

    def test_send_with_thinking(self, session):
        """send_message captures thinking/thought parts."""
        api_response = self._make_api_response(
            [
                self._make_text_part("Let me think about colors...", is_thought=True),
                self._make_text_part("Done, here's the result."),
            ]
        )
        session.client.models.generate_content.return_value = api_response

        result = session.send_message("More vibrant colors")

        assert result.thinking == "Let me think about colors..."
        assert result.text == "Done, here's the result."

    def test_send_safety_blocked(self, session):
        """send_message handles safety block from candidates."""
        api_response = self._make_api_response([], finish_reason="SAFETY")
        session.client.models.generate_content.return_value = api_response

        result = session.send_message("Something inappropriate")

        assert result.safety_blocked is True
        assert result.error is not None
        assert "safety" in result.error.lower()

    def test_send_sdk_exception(self, session):
        """send_message handles SDK exception gracefully."""
        session.client.models.generate_content.side_effect = Exception("API rate limit exceeded")

        result = session.send_message("Test prompt")

        assert result.error == "API rate limit exceeded"
        assert result.image is None

    def test_send_safety_exception(self, session):
        """send_message handles safety-related exception."""
        session.client.models.generate_content.side_effect = Exception(
            "Content was blocked for safety reasons"
        )

        result = session.send_message("Test prompt")

        assert result.safety_blocked is True
        assert "safety" in result.error.lower()

    def test_send_passes_config(self, session):
        """send_message passes correct config to generate_content."""
        api_response = self._make_api_response([self._make_text_part("OK")])
        session.client.models.generate_content.return_value = api_response

        session.send_message("Test", aspect_ratio="1:1", safety_level="relaxed")

        call_kwargs = session.client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-pro-image-preview"
        config = call_kwargs["config"]
        assert config.response_modalities == ["TEXT", "IMAGE"]
        assert config.image_config.aspect_ratio == "1:1"

    def test_send_uses_session_aspect_ratio(self, session):
        """send_message uses session aspect ratio when no override."""
        api_response = self._make_api_response([self._make_text_part("OK")])
        session.client.models.generate_content.return_value = api_response

        session.send_message("Test")

        call_kwargs = session.client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.image_config.aspect_ratio == "16:9"

    def test_send_with_history(self, session):
        """send_message passes history to generate_content via contents."""
        api_response = self._make_api_response([self._make_text_part("Blue cat!")])
        session.client.models.generate_content.return_value = api_response

        history = [
            {"role": "user", "content": "draw a cat"},
            {"role": "assistant", "content": "here is a cat", "image_key": None},
        ]
        result = session.send_message("make it blue", history=history)

        assert result.text == "Blue cat!"
        # Verify contents has 3 items: 2 history + 1 new
        call_kwargs = session.client.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        assert len(contents) == 3

    def test_image_bytes_roundtrip(self, session):
        """Image from SDK response can be read as valid PIL image."""
        original = Image.new("RGB", (64, 64), color=(42, 128, 255))
        buf = BytesIO()
        original.save(buf, format="PNG")

        part = MagicMock()
        part.thought = False
        part.text = None
        part.inline_data = MagicMock()
        part.inline_data.data = buf.getvalue()

        api_response = self._make_api_response([part])
        session.client.models.generate_content.return_value = api_response

        result = session.send_message("Test image")

        assert result.image is not None
        assert result.image.size == (64, 64)
        pixel = result.image.getpixel((0, 0))
        assert pixel == (42, 128, 255)
