"""
Settings router for user preferences and configuration.

Preferences merge logic is delegated to prefhub's PreferencesService.
API settings (webhooks, rate limits) remain handled locally.

Endpoints:
- GET /api/settings - Get user settings
- PUT /api/settings - Update user settings
- GET /api/settings/providers - Get provider preferences
- PUT /api/settings/providers - Update provider preferences
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from prefhub.services.preferences import deep_merge

from api.dependencies import get_settings_repository, get_user_repository
from api.routers.auth import require_current_user
from api.schemas.settings import (
    APISettings,
    GetProviderPreferencesResponse,
    GetSettingsResponse,
    ProviderPreferences,
    UpdateProviderPreferencesRequest,
    UpdateProviderPreferencesResponse,
    UpdateSettingsRequest,
    UpdateSettingsResponse,
    UserPreferences,
)
from database.repositories import SettingsRepository, UserRepository
from services.auth_service import GitHubUser
from services.preferences_service import IdeaGeneratorPreferencesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ============ Helpers ============


async def _get_db_user_id(
    user: GitHubUser,
    user_repo: UserRepository | None,
) -> str | None:
    """Resolve GitHub user to database UUID string."""
    if not user_repo:
        return None
    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        return None
    return str(db_user.id)


# ============ Endpoints ============


@router.get("", response_model=GetSettingsResponse)
async def get_settings(
    user: GitHubUser = Depends(require_current_user),
    settings_repo: SettingsRepository | None = Depends(get_settings_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Get current user settings.

    Returns default settings if none have been saved.
    """
    user_id = await _get_db_user_id(user, user_repo)

    if not user_id or not settings_repo:
        return GetSettingsResponse()

    pref_service = IdeaGeneratorPreferencesService(settings_repo)
    raw = await pref_service._load_raw(user_id)
    prefs = UserPreferences(**raw) if raw else UserPreferences()

    # Load api_settings separately
    db_settings = await settings_repo.get_by_user_id(UUID(user_id))
    api_settings = (
        APISettings(**db_settings.api_settings)
        if db_settings and db_settings.api_settings
        else APISettings()
    )
    updated_at = db_settings.updated_at if db_settings else None

    return GetSettingsResponse(
        preferences=prefs,
        api_settings=api_settings,
        updated_at=updated_at,
    )


@router.put("", response_model=UpdateSettingsResponse)
async def update_settings(
    request: UpdateSettingsRequest,
    user: GitHubUser = Depends(require_current_user),
    settings_repo: SettingsRepository | None = Depends(get_settings_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Update user settings.

    Only provided fields are updated; others remain unchanged.
    """
    if not settings_repo or not user_repo:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Settings cannot be saved.",
        )

    user_id = await _get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found in database")

    db_user_id = UUID(user_id)
    pref_service = IdeaGeneratorPreferencesService(settings_repo)

    # Merge preferences via prefhub deep_merge
    if request.preferences:
        current_raw = await pref_service._load_raw(user_id)
        update_dict = request.preferences.model_dump(exclude_unset=True)
        merged_prefs = deep_merge(current_raw, update_dict)
        await pref_service._save_raw(user_id, merged_prefs)
    else:
        current_raw = await pref_service._load_raw(user_id)
        merged_prefs = current_raw

    # Merge API settings (not part of prefhub)
    current = await settings_repo.get_by_user_id(db_user_id)
    if request.api_settings:
        new_api = request.api_settings.model_dump(exclude_unset=True)
        if current and current.api_settings:
            merged_api = {**current.api_settings, **new_api}
        else:
            merged_api = new_api
        await settings_repo.upsert(user_id=db_user_id, api_settings=merged_api)
    else:
        merged_api = current.api_settings if current else {}

    # Reload for updated_at
    settings = await settings_repo.get_by_user_id(db_user_id)

    return UpdateSettingsResponse(
        success=True,
        preferences=UserPreferences(**merged_prefs),
        api_settings=APISettings(**merged_api),
        updated_at=settings.updated_at,
    )


@router.get("/providers", response_model=GetProviderPreferencesResponse)
async def get_provider_preferences(
    user: GitHubUser = Depends(require_current_user),
    settings_repo: SettingsRepository | None = Depends(get_settings_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Get user's provider preferences.

    These preferences affect which providers are used for generation.
    """
    user_id = await _get_db_user_id(user, user_repo)

    if not user_id or not settings_repo:
        return GetProviderPreferencesResponse(provider_preferences=ProviderPreferences())

    pref_service = IdeaGeneratorPreferencesService(settings_repo)
    raw = await pref_service._load_raw(user_id)
    prefs = UserPreferences(**raw) if raw else UserPreferences()

    return GetProviderPreferencesResponse(provider_preferences=prefs.providers)


@router.put("/providers", response_model=UpdateProviderPreferencesResponse)
async def update_provider_preferences(
    request: UpdateProviderPreferencesRequest,
    user: GitHubUser = Depends(require_current_user),
    settings_repo: SettingsRepository | None = Depends(get_settings_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Update user's provider preferences.
    """
    if not settings_repo or not user_repo:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Settings cannot be saved.",
        )

    user_id = await _get_db_user_id(user, user_repo)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found in database")

    pref_service = IdeaGeneratorPreferencesService(settings_repo)
    current_raw = await pref_service._load_raw(user_id)
    update_dict = {"providers": request.provider_preferences.model_dump()}
    merged = deep_merge(current_raw, update_dict)
    await pref_service._save_raw(user_id, merged)

    # Reload for updated_at
    db_settings = await settings_repo.get_by_user_id(UUID(user_id))

    return UpdateProviderPreferencesResponse(
        success=True,
        provider_preferences=request.provider_preferences,
        updated_at=db_settings.updated_at,
    )
