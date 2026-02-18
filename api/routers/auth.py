"""
Authentication router for user info and API key management.

OAuth flow (login, callback, refresh) is handled by auth-service directly.
This router provides:
- GET /api/auth/status - Auth service status
- GET /api/auth/me - Get current user info (from JWT)
- POST /api/auth/logout - Logout confirmation
- GET/POST/DELETE /api/auth/api-keys - API key management
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends

from api.dependencies import get_api_key_repository, get_user_repository
from api.schemas.auth import (
    APIKeyInfo,
    AuthStatusResponse,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    DeleteAPIKeyResponse,
    ListAPIKeysResponse,
    LogoutResponse,
    UserResponse,
)
from core.auth import AppUser, require_current_user
from core.exceptions import AuthenticationError
from database.repositories import APIKeyRepository, UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ============ Endpoints ============


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status():
    """Get authentication service status."""
    return AuthStatusResponse(
        authenticated=False,
        user=None,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: AppUser = Depends(require_current_user),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Get current authenticated user information.

    Also syncs the user to the database if DB is enabled.
    """
    # Sync user to DB on each /me call (lightweight upsert)
    if user_repo:
        try:
            await user_repo.create_or_update_from_auth(
                auth_id=user.id,
                email=user.email,
                name=user.name,
                avatar_url=user.avatar_url,
            )
        except Exception:
            logger.warning("Failed to sync user to database", exc_info=True)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        user_folder_id=user.user_folder_id,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    user: AppUser = Depends(require_current_user),
):
    """
    Logout current user.

    Frontend should also call auth-service /auth/token/revoke.
    This endpoint just confirms logout on the backend side.
    """
    logger.info(f"User logged out: {user.display_name}")
    return LogoutResponse(success=True, message="Successfully logged out")


# ============ API Keys ============


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns (full_key, key_hash, key_prefix).
    """
    random_part = secrets.token_urlsafe(32)
    full_key = f"nb_sk_{random_part}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:16]
    return full_key, key_hash, key_prefix


async def _get_db_user(
    user: AppUser,
    user_repo: UserRepository | None,
):
    """Look up DB user by auth_id."""
    if not user_repo:
        return None
    return await user_repo.get_by_auth_id(user.id)


@router.get("/api-keys", response_model=ListAPIKeysResponse)
async def list_api_keys(
    user: AppUser = Depends(require_current_user),
    api_key_repo: APIKeyRepository | None = Depends(get_api_key_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List all API keys for the current user."""
    if not api_key_repo or not user_repo:
        return ListAPIKeysResponse(keys=[], total=0)

    db_user = await user_repo.get_by_auth_id(user.id)
    if not db_user:
        return ListAPIKeysResponse(keys=[], total=0)

    api_keys = await api_key_repo.list_by_user(db_user.id)

    keys = []
    for key in api_keys:
        keys.append(
            APIKeyInfo(
                id=str(key.id),
                name=key.name,
                key_prefix=key.key_prefix,
                scopes=key.scopes,
                last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
                expires_at=key.expires_at.isoformat() if key.expires_at else None,
                created_at=key.created_at.isoformat(),
                is_expired=key.is_expired,
            )
        )

    return ListAPIKeysResponse(keys=keys, total=len(keys))


@router.post("/api-keys", response_model=CreateAPIKeyResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    user: AppUser = Depends(require_current_user),
    api_key_repo: APIKeyRepository | None = Depends(get_api_key_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Create a new API key.

    The full key is only returned once. Store it securely.
    """
    if not api_key_repo or not user_repo:
        raise AuthenticationError(message="Database not configured")

    db_user = await user_repo.get_by_auth_id(user.id)
    if not db_user:
        raise AuthenticationError(message="User record not synced. Please re-login.")

    # Check key limit (max 10 keys per user)
    current_count = await api_key_repo.count_by_user(db_user.id)
    if current_count >= 10:
        raise AuthenticationError(message="Maximum number of API keys (10) reached")

    # Generate key
    full_key, key_hash, key_prefix = generate_api_key()

    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now() + timedelta(days=request.expires_in_days)

    # Create in database
    api_key = await api_key_repo.create(
        user_id=db_user.id,
        name=request.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=request.scopes,
        expires_at=expires_at,
    )

    return CreateAPIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        key=full_key,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        created_at=api_key.created_at.isoformat(),
    )


@router.delete("/api-keys/{key_id}", response_model=DeleteAPIKeyResponse)
async def delete_api_key(
    key_id: str,
    user: AppUser = Depends(require_current_user),
    api_key_repo: APIKeyRepository | None = Depends(get_api_key_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Delete an API key."""
    if not api_key_repo or not user_repo:
        raise AuthenticationError(message="Database not configured")

    db_user = await user_repo.get_by_auth_id(user.id)
    if not db_user:
        raise AuthenticationError(message="User record not synced. Please re-login.")

    try:
        key_uuid = UUID(key_id)
    except ValueError:
        raise AuthenticationError(message="Invalid key ID")

    deleted = await api_key_repo.delete_by_user(db_user.id, key_uuid)
    if not deleted:
        raise AuthenticationError(message="API key not found")

    return DeleteAPIKeyResponse(success=True)
