"""
Integration tests for prompts endpoints.
"""

from unittest.mock import MagicMock, patch


class TestPromptsEndpoints:
    """Tests for /api/prompts endpoints."""

    def test_list_prompts_empty(self, client):
        """Test listing prompts when empty."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = []
        mock_storage.is_favorite.return_value = False

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.get("/api/prompts")

            assert response.status_code == 200
            data = response.json()
            assert "prompts" in data
            assert "categories" in data

    def test_list_prompts_with_category_filter(self, client):
        """Test listing prompts with category filter."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = [
            {"id": "1", "text": "Portrait prompt 1", "description": "Test"},
            {"id": "2", "text": "Portrait prompt 2", "description": "Test"},
        ]
        mock_storage.is_favorite.return_value = False

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.get("/api/prompts?category=portrait")

            assert response.status_code == 200

    def test_list_prompts_with_search(self, client):
        """Test listing prompts with search filter."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = []
        mock_storage.is_favorite.return_value = False

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.get("/api/prompts?search=sunset")

            assert response.status_code == 200

    def test_list_prompts_favorites_only(self, client):
        """Test listing only favorite prompts."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = []
        mock_storage.is_favorite.return_value = False

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.get("/api/prompts?favorites_only=true")

            assert response.status_code == 200

    def test_get_categories(self, client):
        """Test getting prompt categories."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = []

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.get("/api/prompts/categories")

            assert response.status_code == 200
            data = response.json()
            assert len(data) > 0
            # Check category structure
            assert all("name" in cat for cat in data)
            assert all("display_name" in cat for cat in data)

    def test_generate_prompts_no_api_key(self, client):
        """Test generating prompts without API key."""
        with patch("api.routers.prompts.get_settings") as mock_settings:
            mock_settings.return_value.google_api_key = None

            response = client.post(
                "/api/prompts/generate", json={"category": "portrait", "count": 5}
            )

            assert response.status_code == 400

    def test_generate_prompts_success(self, client):
        """Test successful prompt generation."""
        mock_generator = MagicMock()
        mock_generator.generate_category_prompts.return_value = [
            {"id": "1", "text": "Generated prompt 1", "description": "Test"},
            {"id": "2", "text": "Generated prompt 2", "description": "Test"},
        ]

        mock_storage = MagicMock()
        mock_storage.save_category_prompts.return_value = True

        with patch("api.routers.prompts.PromptGenerator", return_value=mock_generator):
            with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
                response = client.post(
                    "/api/prompts/generate",
                    json={"category": "portrait", "count": 2},
                    headers={"X-API-Key": "test-api-key"},
                )

                assert response.status_code == 200
                data = response.json()
                assert "prompts" in data
                assert data["count"] == 2

    def test_save_custom_prompt(self, client):
        """Test saving a custom prompt."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = []
        mock_storage.save_category_prompts.return_value = True

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.post(
                "/api/prompts",
                json={
                    "text": "A beautiful sunset over the ocean",
                    "description": "Landscape prompt",
                    "tags": ["sunset", "ocean", "landscape"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "prompt" in data
            assert data["prompt"]["text"] == "A beautiful sunset over the ocean"

    def test_save_custom_prompt_empty_text(self, client):
        """Test saving prompt with empty text."""
        response = client.post("/api/prompts", json={"text": "", "description": "Test"})

        assert response.status_code == 422

    def test_toggle_favorite(self, client):
        """Test toggling favorite status."""
        mock_storage = MagicMock()
        mock_storage.toggle_favorite.return_value = True

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.post("/api/prompts/test-prompt-id/favorite")

            assert response.status_code == 200
            data = response.json()
            assert "is_favorite" in data

    def test_delete_custom_prompt(self, client):
        """Test deleting a custom prompt."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = [
            {"id": "test-prompt-id", "text": "Test prompt"}
        ]
        mock_storage.save_category_prompts.return_value = True

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.delete("/api/prompts/test-prompt-id?category=custom")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_delete_non_custom_prompt_fails(self, client):
        """Test that deleting non-custom prompts fails."""
        response = client.delete("/api/prompts/test-prompt-id?category=portrait")

        assert response.status_code == 400
        assert "custom" in response.json()["detail"].lower()

    def test_delete_prompt_not_found(self, client):
        """Test deleting non-existent prompt."""
        mock_storage = MagicMock()
        mock_storage.get_category_prompts.return_value = []

        with patch("api.routers.prompts.get_user_prompt_storage", return_value=mock_storage):
            response = client.delete("/api/prompts/nonexistent?category=custom")

            assert response.status_code == 404
