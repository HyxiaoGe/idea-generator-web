"""
Integration tests for history endpoints.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestHistoryEndpoints:
    """Tests for /api/history endpoints."""

    def test_list_history_empty(self, client):
        """Test listing history when empty."""
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(return_value=[])

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history")

            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []
            assert data["total"] == 0

    def test_list_history_with_data(self, client):
        """Test listing history with existing data."""
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(
            return_value=[
                {
                    "key": "2024/01/01/image1.png",
                    "filename": "image1.png",
                    "prompt": "test prompt 1",
                    "mode": "basic",
                    "settings": {"aspect_ratio": "16:9"},
                    "duration": 1.5,
                    "created_at": datetime.now().isoformat(),
                },
                {
                    "key": "2024/01/01/image2.png",
                    "filename": "image2.png",
                    "prompt": "test prompt 2",
                    "mode": "chat",
                    "settings": {"aspect_ratio": "1:1"},
                    "duration": 2.0,
                    "created_at": datetime.now().isoformat(),
                },
            ]
        )
        mock_storage.get_public_url = MagicMock(return_value="https://example.com/image.png")

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history")

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 2

    def test_list_history_with_mode_filter(self, client):
        """Test listing history with mode filter."""
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(return_value=[])

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history?mode=basic")

            assert response.status_code == 200
            mock_storage.get_history.assert_called()

    def test_list_history_with_search(self, client):
        """Test listing history with search filter."""
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(return_value=[])

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history?search=sunset")

            assert response.status_code == 200

    def test_list_history_pagination(self, client):
        """Test history pagination."""
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(return_value=[])

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history?limit=10&offset=20")

            assert response.status_code == 200
            data = response.json()
            assert data["limit"] == 10
            assert data["offset"] == 20

    def test_get_history_stats(self, client):
        """Test getting history statistics."""
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(
            return_value=[
                {
                    "key": "1",
                    "mode": "basic",
                    "duration": 1.5,
                    "created_at": datetime.now().isoformat(),
                },
                {
                    "key": "2",
                    "mode": "basic",
                    "duration": 2.0,
                    "created_at": datetime.now().isoformat(),
                },
                {
                    "key": "3",
                    "mode": "chat",
                    "duration": 1.0,
                    "created_at": datetime.now().isoformat(),
                },
            ]
        )

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_images"] == 3
            assert "images_by_mode" in data

    def test_get_history_item_not_found(self, client):
        """Test getting non-existent history item."""
        mock_storage = MagicMock()
        mock_storage.get_history_item = AsyncMock(return_value=None)

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history/nonexistent-item")

            assert response.status_code == 404

    def test_get_history_item_success(self, client):
        """Test getting existing history item."""
        mock_storage = MagicMock()
        mock_storage.get_history_item = AsyncMock(
            return_value={
                "key": "2024/01/01/image.png",
                "filename": "image.png",
                "prompt": "test prompt",
                "mode": "basic",
                "settings": {"aspect_ratio": "16:9"},
                "duration": 1.5,
                "created_at": datetime.now().isoformat(),
            }
        )
        mock_storage.get_public_url = MagicMock(return_value="https://example.com/image.png")

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history/test-item")

            assert response.status_code == 200
            data = response.json()
            assert "item" in data

    def test_delete_history_item_not_found(self, client):
        """Test deleting non-existent history item."""
        mock_storage = MagicMock()
        mock_storage.get_history_item = AsyncMock(return_value=None)

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.delete("/api/history/nonexistent-item")

            assert response.status_code == 404

    def test_delete_history_item_success(self, client):
        """Test deleting existing history item."""
        mock_storage = MagicMock()
        mock_storage.get_history_item = AsyncMock(return_value={"key": "test-item"})
        mock_storage.delete_image = AsyncMock(return_value=True)

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.delete("/api/history/test-item")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_get_history_image_not_found(self, client):
        """Test getting image that doesn't exist."""
        mock_storage = MagicMock()
        mock_storage.load_image_bytes = AsyncMock(return_value=None)

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history/nonexistent/image")

            assert response.status_code == 404

    def test_get_history_image_success(self, client):
        """Test getting image successfully."""
        mock_storage = MagicMock()
        # Create simple PNG image bytes
        mock_storage.load_image_bytes = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        with patch("api.routers.history.get_storage_manager", return_value=mock_storage):
            response = client.get("/api/history/test-item/image")

            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
