"""
Authentication router for GitHub OAuth and API key management.

Endpoints:
- GET /api/auth/login - Get GitHub authorization URL
- POST /api/auth/callback - Handle OAuth callback
- GET /api/auth/me - Get current user info
- POST /api/auth/logout - Logout user
- POST /api/auth/refresh - Refresh JWT token
- GET /api/auth/api-keys - List API keys
- POST /api/auth/api-keys - Create API key
- DELETE /api/auth/api-keys/{id} - Delete API key
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse

from api.dependencies import get_api_key_repository, get_user_repository
from api.schemas.auth import (
    APIKeyInfo,
    AuthStatusResponse,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    DeleteAPIKeyResponse,
    GitHubUserResponse,
    ListAPIKeysResponse,
    LoginUrlResponse,
    LogoutResponse,
    OAuthCallbackRequest,
    RefreshTokenResponse,
    TokenResponse,
)
from core.exceptions import AuthenticationError
from database.repositories import APIKeyRepository, UserRepository
from services import GitHubUser, get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ============ Dependencies ============


async def get_current_user(authorization: str | None = Header(None)) -> GitHubUser | None:
    """
    Get current user from JWT token in Authorization header.

    Returns None if not authenticated (allows unauthenticated access).
    """
    if not authorization:
        return None

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    auth_service = get_auth_service()
    return auth_service.get_user_from_token(token)


async def require_current_user(authorization: str | None = Header(None)) -> GitHubUser:
    """
    Require authenticated user.

    Raises 401 if not authenticated.
    """
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ============ Endpoints ============


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status():
    """Get authentication service status."""
    get_auth_service()
    return AuthStatusResponse(
        authenticated=False,
        user=None,
    )


@router.get("/login", response_model=LoginUrlResponse)
async def get_login_url(
    redirect_uri: str | None = None,
):
    """
    Get GitHub authorization URL.

    Args:
        redirect_uri: Optional override for callback URL
    """
    auth_service = get_auth_service()

    if not auth_service.is_available:
        raise HTTPException(status_code=503, detail="Authentication service not configured")

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)

    url = auth_service.get_authorization_url(
        state=state,
        redirect_uri=redirect_uri,
    )

    return LoginUrlResponse(url=url, state=state)


@router.post("/callback", response_model=TokenResponse)
async def oauth_callback(request: OAuthCallbackRequest):
    """
    Handle OAuth callback from GitHub.

    Exchange authorization code for JWT token.
    """
    auth_service = get_auth_service()

    if not auth_service.is_available:
        raise HTTPException(status_code=503, detail="Authentication service not configured")

    try:
        result = await auth_service.authenticate(request.code)

        user_data = result["user"]
        return TokenResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            user=GitHubUserResponse(
                id=user_data["id"],
                login=user_data["login"],
                name=user_data.get("name"),
                email=user_data.get("email"),
                avatar_url=user_data.get("avatar_url"),
                user_folder_id=user_data["user_folder_id"],
            ),
        )

    except AuthenticationError as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/callback")
async def oauth_callback_redirect(
    code: str,
    state: str | None = None,
    redirect_to: str | None = None,
):
    """
    Handle OAuth callback redirect from GitHub.

    This endpoint receives the redirect from GitHub and can either:
    1. Exchange code for token and redirect to frontend
    2. Return token directly (for SPA flows)
    """
    auth_service = get_auth_service()

    if not auth_service.is_available:
        raise HTTPException(status_code=503, detail="Authentication service not configured")

    try:
        result = await auth_service.authenticate(code)

        # If redirect_to is provided, redirect with token as query param
        if redirect_to:
            return RedirectResponse(url=f"{redirect_to}?token={result['access_token']}")

        # Otherwise return token directly
        user_data = result["user"]
        return TokenResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            user=GitHubUserResponse(
                id=user_data["id"],
                login=user_data["login"],
                name=user_data.get("name"),
                email=user_data.get("email"),
                avatar_url=user_data.get("avatar_url"),
                user_folder_id=user_data["user_folder_id"],
            ),
        )

    except AuthenticationError as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=GitHubUserResponse)
async def get_current_user_info(
    user: GitHubUser = Depends(require_current_user),
):
    """Get current authenticated user information."""
    return GitHubUserResponse(
        id=user.id,
        login=user.login,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        user_folder_id=user.user_folder_id,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    user: GitHubUser = Depends(require_current_user),
):
    """
    Logout current user.

    Note: JWT tokens are stateless, so this just confirms logout.
    Client should discard the token.
    """
    logger.info(f"User logged out: {user.login}")
    return LogoutResponse(success=True, message="Successfully logged out")


# ============ Token Refresh ============


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    user: GitHubUser = Depends(require_current_user),
):
    """
    Refresh the current JWT token.

    Returns a new token with extended expiration.
    The current token must still be valid.
    """
    auth_service = get_auth_service()

    # Create new token with same user data
    new_token = auth_service.create_jwt_token(user.to_dict())

    return RefreshTokenResponse(
        access_token=new_token,
        token_type="bearer",
        expires_in=auth_service.token_expiry_hours * 3600,
    )


# ============ API Keys ============


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns (full_key, key_hash, key_prefix).
    """
    # Generate random key
    random_part = secrets.token_urlsafe(32)
    full_key = f"nb_sk_{random_part}"

    # Hash for storage
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()

    # Prefix for identification
    key_prefix = full_key[:16]

    return full_key, key_hash, key_prefix


@router.get("/api-keys", response_model=ListAPIKeysResponse)
async def list_api_keys(
    user: GitHubUser = Depends(require_current_user),
    api_key_repo: APIKeyRepository | None = Depends(get_api_key_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """List all API keys for the current user."""
    if not api_key_repo or not user_repo:
        return ListAPIKeysResponse(keys=[], total=0)

    db_user = await user_repo.get_by_github_id(int(user.id))
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
    user: GitHubUser = Depends(require_current_user),
    api_key_repo: APIKeyRepository | None = Depends(get_api_key_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """
    Create a new API key.

    The full key is only returned once. Store it securely.
    """
    if not api_key_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check key limit (max 10 keys per user)
    current_count = await api_key_repo.count_by_user(db_user.id)
    if current_count >= 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum number of API keys (10) reached",
        )

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
        key=full_key,  # Only time the full key is returned
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        created_at=api_key.created_at.isoformat(),
    )


@router.delete("/api-keys/{key_id}", response_model=DeleteAPIKeyResponse)
async def delete_api_key(
    key_id: str,
    user: GitHubUser = Depends(require_current_user),
    api_key_repo: APIKeyRepository | None = Depends(get_api_key_repository),
    user_repo: UserRepository | None = Depends(get_user_repository),
):
    """Delete an API key."""
    if not api_key_repo or not user_repo:
        raise HTTPException(status_code=503, detail="Database not configured")

    db_user = await user_repo.get_by_github_id(int(user.id))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        key_uuid = UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID")

    deleted = await api_key_repo.delete_by_user(db_user.id, key_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")

    return DeleteAPIKeyResponse(success=True)
