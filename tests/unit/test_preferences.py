"""Tests for prefhub integration — preferences service and schema."""

from __future__ import annotations

import pytest
from prefhub.schemas import Language, Theme
from prefhub.services.preferences import InMemoryPreferencesService, deep_merge

from api.schemas.settings import (
    RoutingStrategy,
    UserPreferences,
)

# ============ Schema Tests ============


class TestUserPreferencesSchema:
    def test_inherits_prefhub_defaults(self):
        """UserPreferences should include prefhub universal fields."""
        prefs = UserPreferences()
        assert prefs.ui.language == Language.ZH_CN
        assert prefs.ui.theme == Theme.SYSTEM
        assert prefs.ui.timezone == "Asia/Shanghai"
        assert prefs.notifications.enabled is True
        assert prefs.notifications.sound is False

    def test_domain_specific_defaults(self):
        """Domain-specific fields should have their own defaults."""
        prefs = UserPreferences()
        assert prefs.generation.default_aspect_ratio is None
        assert prefs.generation.default_resolution is None
        assert prefs.generation.default_provider is None
        assert prefs.generation.routing_strategy is None
        assert prefs.providers.providers == []
        assert prefs.providers.fallback_enabled is True

    def test_round_trip_from_dict(self):
        """Should construct from nested dict (as stored in JSONB)."""
        data = {
            "ui": {"language": "en", "theme": "dark"},
            "notifications": {"sound": True},
            "generation": {"default_resolution": "2K", "routing_strategy": "quality"},
            "providers": {
                "providers": [{"provider": "openai", "priority": 1}],
                "fallback_enabled": False,
            },
        }
        prefs = UserPreferences(**data)
        assert prefs.ui.language == Language.EN
        assert prefs.ui.theme == Theme.DARK
        assert prefs.notifications.sound is True
        assert prefs.notifications.enabled is True  # default preserved
        assert prefs.generation.default_resolution == "2K"
        assert prefs.generation.routing_strategy == RoutingStrategy.QUALITY
        assert len(prefs.providers.providers) == 1
        assert prefs.providers.providers[0].provider == "openai"
        assert prefs.providers.fallback_enabled is False


# ============ Deep Merge Tests ============


class TestDeepMergeWithDomainFields:
    def test_merge_generation_defaults(self):
        base = {
            "ui": {"language": "zh-CN"},
            "generation": {"default_resolution": "1K", "default_provider": "google"},
        }
        override = {"generation": {"default_resolution": "4K"}}
        result = deep_merge(base, override)
        assert result["generation"]["default_resolution"] == "4K"
        assert result["generation"]["default_provider"] == "google"
        assert result["ui"]["language"] == "zh-CN"

    def test_merge_preserves_providers(self):
        base = {
            "providers": {
                "providers": [{"provider": "google", "enabled": True}],
                "fallback_enabled": True,
            }
        }
        override = {"providers": {"fallback_enabled": False}}
        result = deep_merge(base, override)
        # List is at providers.providers level — deep_merge replaces non-dict values
        assert result["providers"]["fallback_enabled"] is False
        assert result["providers"]["providers"] == [{"provider": "google", "enabled": True}]


# ============ Service Tests ============


class TestPreferencesServiceIntegration:
    @pytest.mark.asyncio
    async def test_get_returns_defaults(self):
        service = InMemoryPreferencesService()
        result = await service.get("user-1")
        assert result.ui.language == Language.ZH_CN
        assert result.ui.theme == Theme.SYSTEM

    @pytest.mark.asyncio
    async def test_update_and_get(self):
        from prefhub.schemas.preferences import PreferencesUpdateRequest, UIPreferences

        service = InMemoryPreferencesService()
        req = PreferencesUpdateRequest(ui=UIPreferences(theme=Theme.DARK))
        result = await service.update("user-1", req)
        assert result.ui.theme == Theme.DARK
        assert result.ui.language == Language.ZH_CN  # default preserved

    @pytest.mark.asyncio
    async def test_domain_fields_survive_round_trip(self):
        """Domain-specific fields stored via _save_raw should load back."""
        service = InMemoryPreferencesService()
        data = {
            "ui": {"language": "en"},
            "generation": {"default_resolution": "2K"},
            "providers": {"fallback_enabled": False},
        }
        await service._save_raw("user-1", data)
        raw = await service._load_raw("user-1")
        prefs = UserPreferences(**raw)
        assert prefs.ui.language == Language.EN
        assert prefs.generation.default_resolution == "2K"
        assert prefs.providers.fallback_enabled is False
