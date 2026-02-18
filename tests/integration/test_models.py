"""
Integration tests for GET /api/models endpoint.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.providers.base import MediaType, ProviderCapability, ProviderModel


def _make_model(
    id: str,
    name: str,
    provider: str,
    tier: str = "balanced",
    arena_score: int | None = None,
    hidden: bool = False,
) -> ProviderModel:
    return ProviderModel(
        id=id,
        name=name,
        provider=provider,
        media_type=MediaType.IMAGE,
        capabilities=[ProviderCapability.TEXT_TO_IMAGE],
        tier=tier,
        arena_score=arena_score,
        hidden=hidden,
    )


class MockProviderEntry:
    def __init__(self, name, display_name, models):
        self._name = name
        self._display_name = display_name
        self._models = models

    @property
    def name(self):
        return self._name

    @property
    def display_name(self):
        return self._display_name

    @property
    def models(self):
        return self._models

    def get_model_by_id(self, model_id):
        for m in self._models:
            if m.id == model_id:
                return m
        return None


@pytest.fixture
def mock_registry_for_models():
    """Mock provider registry for models endpoint tests."""
    providers = [
        MockProviderEntry(
            "google",
            "Google Gemini",
            [
                _make_model("imagen-4", "Imagen 4", "google", tier="premium", arena_score=1200),
                _make_model("hidden-model", "Hidden", "google", hidden=True),
            ],
        ),
        MockProviderEntry(
            "openai",
            "OpenAI",
            [
                _make_model(
                    "gpt-image-1", "GPT Image 1", "openai", tier="balanced", arena_score=1100
                ),
            ],
        ),
    ]

    mock_reg = MagicMock()
    mock_reg.get_available_image_providers.return_value = providers

    return mock_reg


def test_list_models(client, mock_registry_for_models):
    """GET /api/models should return presets and visible models."""
    with patch(
        "services.model_router.get_provider_registry",
        return_value=mock_registry_for_models,
    ):
        response = client.get("/api/models")

    assert response.status_code == 200
    data = response.json()

    # Check presets
    assert "presets" in data
    preset_ids = [p["id"] for p in data["presets"]]
    assert "premium" in preset_ids
    assert "balanced" in preset_ids
    assert "fast" in preset_ids

    # Check default preset
    assert data["default_preset"] == "balanced"

    # Check models
    assert "models" in data
    model_ids = [m["id"] for m in data["models"]]
    assert "imagen-4" in model_ids
    assert "gpt-image-1" in model_ids

    # Hidden models should be excluded
    assert "hidden-model" not in model_ids


def test_list_models_sorted_by_arena_score(client, mock_registry_for_models):
    """Models should be sorted by arena_score descending."""
    with patch(
        "services.model_router.get_provider_registry",
        return_value=mock_registry_for_models,
    ):
        response = client.get("/api/models")

    data = response.json()
    models = data["models"]
    scores = [m["arena_score"] or 0 for m in models]
    assert scores == sorted(scores, reverse=True)
