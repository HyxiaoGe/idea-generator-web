"""
Preferences service backed by SettingsRepository.

Implements prefhub's PreferencesService using the existing
user_settings table (Pattern B: JSONB preferences column).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from prefhub.services.preferences import PreferencesService

from database.repositories import SettingsRepository


class IdeaGeneratorPreferencesService(PreferencesService):
    """Storage backend using the existing user_settings table."""

    def __init__(self, settings_repo: SettingsRepository):
        self.settings_repo = settings_repo

    async def _load_raw(self, user_id: str) -> dict[str, Any]:
        settings = await self.settings_repo.get_by_user_id(UUID(user_id))
        if not settings:
            return {}
        return settings.preferences or {}

    async def _save_raw(self, user_id: str, data: dict[str, Any]) -> None:
        await self.settings_repo.upsert(
            user_id=UUID(user_id),
            preferences=data,
        )
