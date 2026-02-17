"""
Preferences service backed by PreferencesRepository.

Implements prefhub's PreferencesService using the existing
user_preferences table (Pattern B: JSONB preferences column).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from prefhub.services.preferences import PreferencesService

from database.repositories import PreferencesRepository


class IdeaGeneratorPreferencesService(PreferencesService):
    """Storage backend using the user_preferences table."""

    def __init__(self, prefs_repo: PreferencesRepository):
        self.prefs_repo = prefs_repo

    async def _load_raw(self, user_id: str) -> dict[str, Any]:
        record = await self.prefs_repo.get_by_user_id(UUID(user_id))
        if not record:
            return {}
        return record.preferences or {}

    async def _save_raw(self, user_id: str, data: dict[str, Any]) -> None:
        await self.prefs_repo.upsert(
            user_id=UUID(user_id),
            preferences=data,
        )
