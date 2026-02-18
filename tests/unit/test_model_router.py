"""
Unit tests for model_router module.

Tests alias resolution, preset selection, and model listing.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.model_router import (
    QualityPreset,
    get_all_models,
    resolve_alias,
    select_model_by_preset,
)
from services.providers.base import MediaType, ProviderCapability, ProviderModel


def _make_model(
    id: str,
    name: str,
    provider: str,
    tier: str = "balanced",
    arena_score: int | None = None,
    aliases: list[str] | None = None,
    hidden: bool = False,
    is_default: bool = False,
) -> ProviderModel:
    """Helper to create a ProviderModel for testing."""
    return ProviderModel(
        id=id,
        name=name,
        provider=provider,
        media_type=MediaType.IMAGE,
        capabilities=[ProviderCapability.TEXT_TO_IMAGE],
        tier=tier,
        arena_score=arena_score,
        aliases=aliases or [],
        hidden=hidden,
        is_default=is_default,
    )


class MockProviderEntry:
    """Mock provider entry returned by registry."""

    def __init__(self, name: str, display_name: str, models: list[ProviderModel]):
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

    def get_model_by_id(self, model_id: str) -> ProviderModel | None:
        for m in self._models:
            if m.id == model_id:
                return m
        for m in self._models:
            if model_id in m.aliases:
                return m
        return None


@pytest.fixture
def mock_registry():
    """Set up mock provider registry with test data."""
    providers = [
        MockProviderEntry(
            name="test-provider-a",
            display_name="Test Provider A",
            models=[
                _make_model(
                    "model-premium",
                    "Premium Model",
                    "test-provider-a",
                    tier="premium",
                    arena_score=1200,
                    aliases=["old-model-name"],
                ),
                _make_model(
                    "model-balanced",
                    "Balanced Model",
                    "test-provider-a",
                    tier="balanced",
                    arena_score=1100,
                    is_default=True,
                ),
                _make_model(
                    "model-hidden",
                    "Hidden Model",
                    "test-provider-a",
                    tier="balanced",
                    arena_score=1050,
                    hidden=True,
                ),
            ],
        ),
        MockProviderEntry(
            name="test-provider-b",
            display_name="Test Provider B",
            models=[
                _make_model(
                    "model-fast",
                    "Fast Model",
                    "test-provider-b",
                    tier="fast",
                    arena_score=1000,
                ),
                _make_model(
                    "model-balanced-b",
                    "Balanced B",
                    "test-provider-b",
                    tier="balanced",
                    arena_score=1150,
                    aliases=["legacy-b"],
                ),
            ],
        ),
    ]

    mock_reg = MagicMock()
    mock_reg.get_available_image_providers.return_value = providers

    with patch("services.model_router.get_provider_registry", return_value=mock_reg):
        yield mock_reg


class TestResolveAlias:
    """Tests for resolve_alias()."""

    def test_canonical_id(self, mock_registry):
        """Direct model ID should resolve to itself."""
        provider, model_id = resolve_alias("model-premium")
        assert provider == "test-provider-a"
        assert model_id == "model-premium"

    def test_alias_resolves(self, mock_registry):
        """Old alias should resolve to canonical model."""
        provider, model_id = resolve_alias("old-model-name")
        assert provider == "test-provider-a"
        assert model_id == "model-premium"

    def test_alias_from_provider_b(self, mock_registry):
        """Alias from second provider should resolve correctly."""
        provider, model_id = resolve_alias("legacy-b")
        assert provider == "test-provider-b"
        assert model_id == "model-balanced-b"

    def test_unknown_id(self, mock_registry):
        """Unknown ID returns (None, original_id)."""
        provider, model_id = resolve_alias("nonexistent-model")
        assert provider is None
        assert model_id == "nonexistent-model"


class TestSelectModelByPreset:
    """Tests for select_model_by_preset()."""

    def test_premium_preset(self, mock_registry):
        """Premium preset should select highest arena_score premium model."""
        provider, model_id = select_model_by_preset(QualityPreset.PREMIUM)
        assert model_id == "model-premium"
        assert provider == "test-provider-a"

    def test_balanced_preset(self, mock_registry):
        """Balanced preset should select highest arena_score balanced model."""
        provider, model_id = select_model_by_preset(QualityPreset.BALANCED)
        # model-balanced-b has score 1150, model-balanced has 1100
        assert model_id == "model-balanced-b"
        assert provider == "test-provider-b"

    def test_fast_preset(self, mock_registry):
        """Fast preset should select a fast-tier model."""
        provider, model_id = select_model_by_preset(QualityPreset.FAST)
        assert model_id == "model-fast"
        assert provider == "test-provider-b"

    def test_preferred_provider(self, mock_registry):
        """Preferred provider should be respected."""
        provider, model_id = select_model_by_preset(
            QualityPreset.BALANCED, preferred_provider="test-provider-a"
        )
        assert model_id == "model-balanced"
        assert provider == "test-provider-a"

    def test_preferred_provider_no_match_falls_back(self, mock_registry):
        """If preferred provider has no models for the tier, fall back to all."""
        provider, model_id = select_model_by_preset(
            QualityPreset.FAST, preferred_provider="test-provider-a"
        )
        # Provider A has no fast models, should fall back to all providers
        assert model_id == "model-fast"
        assert provider == "test-provider-b"

    def test_hidden_models_excluded(self, mock_registry):
        """Hidden models should not be selected."""
        provider, model_id = select_model_by_preset(QualityPreset.BALANCED)
        # model-hidden is balanced but hidden, should not be selected
        assert model_id != "model-hidden"


class TestGetAllModels:
    """Tests for get_all_models()."""

    def test_excludes_hidden_by_default(self, mock_registry):
        """Hidden models should be excluded by default."""
        models = get_all_models()
        model_ids = [m["id"] for m in models]
        assert "model-hidden" not in model_ids

    def test_includes_hidden_when_requested(self, mock_registry):
        """Hidden models should be included when requested."""
        models = get_all_models(include_hidden=True)
        model_ids = [m["id"] for m in models]
        assert "model-hidden" in model_ids

    def test_sorted_by_arena_score(self, mock_registry):
        """Models should be sorted by arena_score descending."""
        models = get_all_models()
        scores = [m["arena_score"] or 0 for m in models]
        assert scores == sorted(scores, reverse=True)

    def test_model_fields(self, mock_registry):
        """Each model dict should have expected fields."""
        models = get_all_models()
        assert len(models) > 0
        model = models[0]
        expected_fields = [
            "id",
            "name",
            "provider",
            "provider_display_name",
            "tier",
            "arena_rank",
            "arena_score",
            "max_resolution",
            "pricing",
            "quality_score",
            "latency_estimate",
            "strengths",
            "aliases",
            "is_default",
        ]
        for field in expected_fields:
            assert field in model, f"Missing field: {field}"

    def test_visible_model_count(self, mock_registry):
        """Should return correct number of visible models."""
        models = get_all_models()
        # 2 from provider A (1 hidden excluded) + 2 from provider B = 4
        assert len(models) == 4
