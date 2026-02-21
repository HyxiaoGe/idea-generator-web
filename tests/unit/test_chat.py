"""
Unit tests for chat endpoints — focused on POST /api/chat/{session_id}/message (send_message).

Tests the router layer (mock Redis + mock ChatSession + mock storage) and
the ChatSession class (mock Google SDK with real message processing).
"""

import json
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

# ============ Helpers ============


def _make_send_request(message="Make it more colorful", aspect_ratio=None, safety_level="moderate"):
    """Build a send message request dict."""
    req = {"message": message, "safety_level": safety_level}
    if aspect_ratio:
        req["aspect_ratio"] = aspect_ratio
    return req


def _make_session_data(session_id="test-session-123", messages=None):
    """Build mock Redis session data."""
    now = datetime.now().isoformat()
    return {
        "session_id": session_id,
        "user_id": "anonymous",
        "aspect_ratio": "16:9",
        "messages": messages or [],
        "created_at": now,
        "last_activity": now,
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


@contextmanager
def _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_session_mock):
    """Patch all chat send_message endpoint dependencies."""
    from services.chat_session import ChatSession as RealChatSession

    async def get_mock_redis():
        return mock_redis

    # Build a mock class that returns chat_session_mock on instantiation
    # but preserves class-level constants the router accesses
    mock_cls = MagicMock(return_value=chat_session_mock)
    mock_cls.IMAGE_HISTORY_TURNS = RealChatSession.IMAGE_HISTORY_TURNS

    with (
        patch("api.routers.chat.get_redis", get_mock_redis),
        patch("core.redis.get_redis", get_mock_redis),
        patch("api.routers.chat.get_quota_service", return_value=mock_quota_service),
        patch("api.routers.chat.get_storage_manager", return_value=storage_mock),
        patch("api.routers.chat.ChatSession", mock_cls),
    ):
        yield


# ============ Router Tests: Send Message ============


class TestSendMessageValidation:
    """Request validation tests for POST /api/chat/{session_id}/message."""

    def test_missing_message(self, client, mock_redis):
        """Send without message returns 422."""
        response = client.post("/api/chat/test-session/message", json={})
        assert response.status_code == 422

    def test_empty_message(self, client, mock_redis):
        """Send with empty message returns 422."""
        response = client.post(
            "/api/chat/test-session/message",
            json={"message": ""},
        )
        assert response.status_code == 422

    def test_message_too_long(self, client, mock_redis):
        """Send with message exceeding max_length returns 422."""
        response = client.post(
            "/api/chat/test-session/message",
            json={"message": "x" * 2001},
        )
        assert response.status_code == 422


class TestSendMessageSuccess:
    """Successful send_message tests."""

    def test_send_text_only_response(self, client, mock_redis, mock_quota_service):
        """Send message gets text-only response (no image)."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text="I'll make the colors more vibrant.", image=None
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "I'll make the colors more vibrant."
        assert data["image"] is None
        assert data["duration"] > 0
        assert data["message_count"] == 2  # user + assistant

    def test_send_with_image_response(self, client, mock_redis, mock_quota_service):
        """Send message gets response with generated image."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        img = Image.new("RGB", (512, 512), color="blue")
        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text="Here's the colorful version.", image=img
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)
        save_result = MagicMock()
        save_result.key = "images/chat/test.png"
        save_result.filename = "test.png"
        save_result.public_url = "https://cdn.example.com/images/chat/test.png"
        storage_mock.save_image = AsyncMock(return_value=save_result)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Here's the colorful version."
        assert data["image"] is not None
        assert data["image"]["key"] == "images/chat/test.png"
        assert data["image"]["width"] == 512
        assert data["image"]["height"] == 512

    def test_send_with_thinking(self, client, mock_redis, mock_quota_service):
        """Send message includes thinking in response."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text="Done!", thinking="Let me adjust the saturation and hue..."
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["thinking"] == "Let me adjust the saturation and hue..."

    def test_send_with_aspect_ratio_override(self, client, mock_redis, mock_quota_service):
        """Send message passes aspect ratio override to ChatSession."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="Square version.")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(aspect_ratio="1:1"),
            )

        assert response.status_code == 200
        # Verify ChatSession.send_message was called with the right aspect ratio
        call_kwargs = chat_mock.send_message.call_args
        assert call_kwargs.kwargs.get("aspect_ratio") == "1:1"

    def test_send_updates_redis_session(self, client, mock_redis, mock_quota_service):
        """Send message updates session data in Redis with new messages."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="Updated!")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(message="Add a sunset"),
            )

        # Verify Redis was updated with the new messages
        updated_data = json.loads(mock_redis._data[session_key])
        assert len(updated_data["messages"]) == 2
        assert updated_data["messages"][0]["role"] == "user"
        assert updated_data["messages"][0]["content"] == "Add a sunset"
        assert updated_data["messages"][1]["role"] == "assistant"
        assert updated_data["messages"][1]["content"] == "Updated!"

    def test_send_with_existing_conversation(self, client, mock_redis, mock_quota_service):
        """Send message in session that already has messages."""
        existing_messages = [
            {"role": "user", "content": "Draw a cat", "timestamp": datetime.now().isoformat()},
            {
                "role": "assistant",
                "content": "Here's a cat.",
                "image_key": None,
                "thinking": None,
                "timestamp": datetime.now().isoformat(),
            },
        ]
        session_data = _make_session_data(messages=existing_messages)
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="Made it colorful!")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message_count"] == 4  # 2 existing + 2 new

    def test_send_passes_history_to_chat_session(self, client, mock_redis, mock_quota_service):
        """Send message passes existing history to ChatSession.send_message."""
        existing_messages = [
            {"role": "user", "content": "Draw a cat", "timestamp": datetime.now().isoformat()},
            {
                "role": "assistant",
                "content": "Here's a cat.",
                "image_key": None,
                "thinking": None,
                "timestamp": datetime.now().isoformat(),
            },
        ]
        session_data = _make_session_data(messages=existing_messages)
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="OK!")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(message="Make it blue"),
            )

        # Verify history was passed (the list is mutated after send, so check
        # it contains at least the original messages plus the new ones)
        call_kwargs = chat_mock.send_message.call_args.kwargs
        assert call_kwargs["message"] == "Make it blue"
        # history is the same list object as session_data["messages"], which
        # gets new messages appended after send_message returns, so verify
        # it was passed (non-empty) and contains the originals
        assert len(call_kwargs["history"]) >= 2
        assert call_kwargs["history"][0]["content"] == "Draw a cat"
        assert call_kwargs["history"][1]["content"] == "Here's a cat."
        assert isinstance(call_kwargs["history_images"], dict)


class TestSendMessageErrors:
    """Error handling tests for send_message."""

    def test_session_not_found(self, client, mock_redis, mock_quota_service):
        """Send to non-existent session returns 404."""
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)
        chat_mock = MagicMock()

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/nonexistent-session/message",
                json=_make_send_request(),
            )

        assert response.status_code == 404

    def test_quota_exceeded(self, client, mock_redis):
        """Send fails with 429 when quota exceeded."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        quota_service = MagicMock()
        quota_service.check_quota = AsyncMock(
            return_value=(False, "Daily limit reached", {"used": 50, "limit": 50})
        )

        chat_mock = MagicMock()
        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 429

    def test_provider_error(self, client, mock_redis, mock_quota_service):
        """Send fails with 500 when ChatSession returns error."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text=None, error="Model overloaded"
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 500

    def test_safety_blocked(self, client, mock_redis, mock_quota_service):
        """Send fails with 500 when content is safety-blocked."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(
            text=None, error="Content blocked by safety filter"
        )

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 500

    def test_no_api_key(self, client, mock_redis, mock_quota_service):
        """Send fails when no API key is configured."""
        session_data = _make_session_data()
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=None)

        # Patch ChatSession to raise on init (no API key) and settings to return None
        with _patch_no_api_key(mock_redis, mock_quota_service, storage_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        assert response.status_code == 422


@contextmanager
def _patch_no_api_key(mock_redis, mock_quota_service, storage_mock):
    """Patch for no API key scenario."""

    async def get_mock_redis():
        return mock_redis

    mock_settings = MagicMock()
    mock_settings.get_google_api_key.return_value = None

    with (
        patch("api.routers.chat.get_redis", get_mock_redis),
        patch("core.redis.get_redis", get_mock_redis),
        patch("api.routers.chat.get_quota_service", return_value=mock_quota_service),
        patch("api.routers.chat.get_storage_manager", return_value=storage_mock),
        patch("api.routers.chat.get_settings", return_value=mock_settings),
    ):
        yield


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

    def test_with_images(self, session):
        """Recent history images are included in model message parts."""
        img = Image.new("RGB", (64, 64), color="red")
        history = [
            {"role": "user", "content": "draw a cat"},
            {"role": "assistant", "content": "here is a cat", "image_key": "img/cat.png"},
        ]
        history_images = {"img/cat.png": img}

        contents = session._build_contents(history, "make it blue", history_images)

        # Model message should have 2 parts: text + image
        model_msg = contents[1]
        assert model_msg.role == "model"
        assert len(model_msg.parts) == 2
        assert model_msg.parts[0].text == "here is a cat"
        assert model_msg.parts[1].inline_data is not None
        assert model_msg.parts[1].inline_data.mime_type == "image/png"

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


# ============ Router-Level History Image Loading Tests ============


class TestRouterHistoryImageLoading:
    """Tests that the router correctly loads history images and passes them to ChatSession."""

    def test_router_loads_history_images(self, client, mock_redis, mock_quota_service):
        """Router loads images from storage for recent history messages."""
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
        session_data = _make_session_data(messages=existing_messages)
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        cat_img = Image.new("RGB", (64, 64), color="orange")
        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="Blue cat!")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(return_value=cat_img)

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(message="Make it blue"),
            )

        assert response.status_code == 200
        # Verify send_message received history_images with the loaded image
        call_kwargs = chat_mock.send_message.call_args.kwargs
        assert "img/cat.png" in call_kwargs["history_images"]

    def test_router_handles_failed_image_load(self, client, mock_redis, mock_quota_service):
        """Router gracefully handles image loading failures."""
        existing_messages = [
            {"role": "user", "content": "Draw a cat", "timestamp": datetime.now().isoformat()},
            {
                "role": "assistant",
                "content": "Here's a cat.",
                "image_key": "img/missing.png",
                "thinking": None,
                "timestamp": datetime.now().isoformat(),
            },
        ]
        session_data = _make_session_data(messages=existing_messages)
        session_key = "chat:anonymous:test-session-123"
        mock_redis._data[session_key] = json.dumps(session_data)

        chat_mock = MagicMock()
        chat_mock.send_message.return_value = _make_chat_response(text="OK")

        storage_mock = MagicMock()
        storage_mock.load_image = AsyncMock(side_effect=Exception("File not found"))

        with _patch_chat_deps(mock_redis, mock_quota_service, storage_mock, chat_mock):
            response = client.post(
                "/api/chat/test-session-123/message",
                json=_make_send_request(),
            )

        # Should still succeed — failed image loads are silently skipped
        assert response.status_code == 200
        call_kwargs = chat_mock.send_message.call_args.kwargs
        assert call_kwargs["history_images"] == {}
