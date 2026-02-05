"""
Integration tests for chat endpoints.
"""

import json
from datetime import datetime
from unittest.mock import patch


class TestChatEndpoints:
    """Tests for /api/chat endpoints."""

    def test_create_chat_session(self, client, mock_redis):
        """Test creating a new chat session."""

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.post("/api/chat", json={"aspect_ratio": "16:9"})

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["aspect_ratio"] == "16:9"

    def test_create_chat_session_default_aspect(self, client, mock_redis):
        """Test creating chat session with default aspect ratio."""

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.post("/api/chat", json={})

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data

    def test_list_chat_sessions_empty(self, client, mock_redis):
        """Test listing sessions when none exist."""

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.get("/api/chat")

            assert response.status_code == 200
            data = response.json()
            assert data["sessions"] == []
            assert data["total"] == 0

    def test_list_chat_sessions_with_data(self, client, mock_redis):
        """Test listing sessions with existing data."""
        # Set up mock session data
        session_data = {
            "session_id": "test-session-1",
            "user_id": "anonymous",
            "aspect_ratio": "16:9",
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
        }
        mock_redis._data["chat:anonymous:test-session-1"] = json.dumps(session_data)
        mock_redis._sets["chat_sessions:anonymous"] = {"test-session-1"}

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.get("/api/chat")

            assert response.status_code == 200
            data = response.json()
            assert len(data["sessions"]) == 1
            assert data["total"] == 1

    def test_get_chat_history_not_found(self, client, mock_redis):
        """Test getting history for non-existent session."""

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.get("/api/chat/nonexistent-session")

            assert response.status_code == 404

    def test_get_chat_history_success(self, client, mock_redis):
        """Test getting chat history successfully."""
        session_data = {
            "session_id": "test-session",
            "user_id": "anonymous",
            "aspect_ratio": "16:9",
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": datetime.now().isoformat()},
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "timestamp": datetime.now().isoformat(),
                },
            ],
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
        }
        mock_redis._data["chat:anonymous:test-session"] = json.dumps(session_data)

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.get("/api/chat/test-session")

            assert response.status_code == 200
            data = response.json()
            assert len(data["messages"]) == 2

    def test_delete_chat_session_not_found(self, client, mock_redis):
        """Test deleting non-existent session."""

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.delete("/api/chat/nonexistent-session")

            assert response.status_code == 404

    def test_delete_chat_session_success(self, client, mock_redis):
        """Test deleting existing session."""
        mock_redis._data["chat:anonymous:test-session"] = "{}"

        async def mock_get_redis():
            return mock_redis

        with patch("api.routers.chat.get_redis", mock_get_redis):
            response = client.delete("/api/chat/test-session")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
