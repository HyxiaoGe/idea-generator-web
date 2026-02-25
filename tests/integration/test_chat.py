"""
Integration tests for chat endpoints.

After the migration from Redis to DB (chat session storage), these tests
mock the ChatRepository dependency instead of Redis.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from api.dependencies import require_chat_repository


def _mock_db_session(session_id="test-session-1", aspect_ratio="16:9", messages=None):
    """Create a mock DB ChatSession object."""
    s = MagicMock()
    s.id = uuid.UUID(session_id) if len(session_id) < 36 else uuid.uuid4()
    s.aspect_ratio = aspect_ratio
    s.message_count = len(messages) if messages else 0
    s.created_at = datetime.now()
    s.updated_at = datetime.now()
    s.messages = messages or []
    return s


def _mock_db_message(role="user", content="Hello", image_url=None, thinking=None):
    """Create a mock DB ChatMessage object."""
    m = MagicMock()
    m.role = role
    m.content = content
    m.image_url = image_url
    m.thinking = thinking
    m.thought_signature = None
    m.created_at = datetime.now()
    return m


class TestChatEndpoints:
    """Tests for /api/chat endpoints."""

    def test_create_chat_session(self, client):
        """Test creating a new chat session."""
        mock_repo = AsyncMock()
        mock_repo.create_session.return_value = None

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.post("/api/chat", json={"aspect_ratio": "16:9"})
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["aspect_ratio"] == "16:9"
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_create_chat_session_default_aspect(self, client):
        """Test creating chat session with default aspect ratio."""
        mock_repo = AsyncMock()
        mock_repo.create_session.return_value = None

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.post("/api/chat", json={})
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_list_chat_sessions_empty(self, client):
        """Test listing sessions when none exist."""
        mock_repo = AsyncMock()
        mock_repo.list_sessions_by_user.return_value = []

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.get("/api/chat")
            assert response.status_code == 200
            data = response.json()
            assert data["sessions"] == []
            assert data["total"] == 0
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_list_chat_sessions_with_data(self, client):
        """Test listing sessions with existing data."""
        session_id = str(uuid.uuid4())
        mock_session = _mock_db_session(session_id=session_id)

        mock_repo = AsyncMock()
        mock_repo.list_sessions_by_user.return_value = [mock_session]

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.get("/api/chat")
            assert response.status_code == 200
            data = response.json()
            assert len(data["sessions"]) == 1
            assert data["total"] == 1
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_get_chat_history_not_found(self, client):
        """Test getting history for non-existent session."""
        mock_repo = AsyncMock()
        mock_repo.get_session_with_messages.return_value = None

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.get(f"/api/chat/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_get_chat_history_success(self, client):
        """Test getting chat history successfully."""
        session_id = str(uuid.uuid4())
        messages = [
            _mock_db_message(role="user", content="Hello"),
            _mock_db_message(role="assistant", content="Hi there!"),
        ]
        mock_session = _mock_db_session(session_id=session_id, messages=messages)

        mock_repo = AsyncMock()
        mock_repo.get_session_with_messages.return_value = mock_session

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.get(f"/api/chat/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert len(data["messages"]) == 2
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_delete_chat_session_not_found(self, client):
        """Test deleting non-existent session."""
        mock_repo = AsyncMock()
        mock_repo.delete_session.return_value = False

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.delete(f"/api/chat/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)

    def test_delete_chat_session_success(self, client):
        """Test deleting existing session."""
        mock_repo = AsyncMock()
        mock_repo.delete_session.return_value = True

        from api.main import app

        app.dependency_overrides[require_chat_repository] = lambda: mock_repo
        try:
            response = client.delete(f"/api/chat/{uuid.uuid4()}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
        finally:
            app.dependency_overrides.pop(require_chat_repository, None)
