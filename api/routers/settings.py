"""
Settings router for user preferences and configuration.

Endpoints:
- GET /api/settings - Get user settings
- PUT /api/settings - Update user settings
- GET /api/settings/providers - Get provider preferences
- PUT /api/settings/providers - Update provider preferences
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ============ Helpers ============


async def get_or_create_settings(
    user: GitHubUser,
    settings_repo: SettingsRepository | None,
    user_repo: UserRepository | None,
) -> tuple[UserPreferences, APISettings, datetime | None]:
    """Get user settings, creating defaults if needed."""
    if not settings_repo or not user_repo:
        # No database, return defaults
        return UserPreferences(), APISettings(), None

    # Get user ID from database
    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        # User not in database yet, return defaults
        return UserPreferences(), APISettings(), None

    # Get settings
    settings = await settings_repo.get_by_user_id(db_user.id)
    if not settings:
        # No settings yet, return defaults
        return UserPreferences(), APISettings(), None

    # Parse settings from JSON
    prefs = UserPreferences(**settings.preferences) if settings.preferences else UserPreferences()
    api_settings = APISettings(**settings.api_settings) if settings.api_settings else APISettings()

    return prefs, api_settings, settings.updated_at


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
    prefs, api_settings, updated_at = await get_or_create_settings(user, settings_repo, user_repo)

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

    # Get user ID
    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found in database",
        )

    # Get current settings
    current = await settings_repo.get_by_user_id(db_user.id)

    # Merge preferences
    if request.preferences:
        new_prefs = request.preferences.model_dump(exclude_unset=True)
        if current and current.preferences:
            merged_prefs = {**current.preferences, **new_prefs}
        else:
            merged_prefs = new_prefs
    else:
        merged_prefs = current.preferences if current else {}

    # Merge API settings
    if request.api_settings:
        new_api = request.api_settings.model_dump(exclude_unset=True)
        if current and current.api_settings:
            merged_api = {**current.api_settings, **new_api}
        else:
            merged_api = new_api
    else:
        merged_api = current.api_settings if current else {}

    # Upsert settings
    settings = await settings_repo.upsert(
        user_id=db_user.id,
        preferences=merged_prefs,
        api_settings=merged_api,
    )

    return UpdateSettingsResponse(
        success=True,
        preferences=UserPreferences(**settings.preferences),
        api_settings=APISettings(**settings.api_settings),
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
    if not settings_repo or not user_repo:
        return GetProviderPreferencesResponse(provider_preferences=ProviderPreferences())

    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        return GetProviderPreferencesResponse(provider_preferences=ProviderPreferences())

    settings = await settings_repo.get_by_user_id(db_user.id)
    if not settings or not settings.preferences:
        return GetProviderPreferencesResponse(provider_preferences=ProviderPreferences())

    # Provider preferences are stored in preferences.provider_preferences
    provider_prefs_data = settings.preferences.get("provider_preferences", {})
    provider_prefs = (
        ProviderPreferences(**provider_prefs_data) if provider_prefs_data else ProviderPreferences()
    )

    return GetProviderPreferencesResponse(provider_preferences=provider_prefs)


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

    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found in database",
        )

    # Update provider_preferences in preferences
    settings = await settings_repo.update_preferences(
        user_id=db_user.id,
        provider_preferences=request.provider_preferences.model_dump(),
    )

    if not settings:
        raise HTTPException(
            status_code=500,
            detail="Failed to update settings",
        )

    return UpdateProviderPreferencesResponse(
        success=True,
        provider_preferences=request.provider_preferences,
        updated_at=settings.updated_at,
    )
