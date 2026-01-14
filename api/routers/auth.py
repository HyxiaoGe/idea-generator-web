"""
Authentication router for GitHub OAuth.

Endpoints:
- GET /api/auth/login - Get GitHub authorization URL
- POST /api/auth/callback - Handle OAuth callback
- GET /api/auth/me - Get current user info
- POST /api/auth/logout - Logout user
"""

import secrets
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import RedirectResponse

from core.exceptions import AuthenticationError
from core.security import verify_token
from services import AuthService, GitHubUser, get_auth_service
from api.schemas.auth import (
    TokenResponse,
    AuthStatusResponse,
    LoginUrlResponse,
    OAuthCallbackRequest,
    LogoutResponse,
    GitHubUserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ============ Dependencies ============

async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> Optional[GitHubUser]:
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


async def require_current_user(
    authorization: Optional[str] = Header(None)
) -> GitHubUser:
    """
    Require authenticated user.

    Raises 401 if not authenticated.
    """
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    return user


# ============ Endpoints ============

@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status():
    """Get authentication service status."""
    auth_service = get_auth_service()
    return AuthStatusResponse(
        authenticated=False,
        user=None,
    )


@router.get("/login", response_model=LoginUrlResponse)
async def get_login_url(
    redirect_uri: Optional[str] = None,
):
    """
    Get GitHub authorization URL.

    Args:
        redirect_uri: Optional override for callback URL
    """
    auth_service = get_auth_service()

    if not auth_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Authentication service not configured"
        )

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
        raise HTTPException(
            status_code=503,
            detail="Authentication service not configured"
        )

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
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )


@router.get("/callback")
async def oauth_callback_redirect(
    code: str,
    state: Optional[str] = None,
    redirect_to: Optional[str] = None,
):
    """
    Handle OAuth callback redirect from GitHub.

    This endpoint receives the redirect from GitHub and can either:
    1. Exchange code for token and redirect to frontend
    2. Return token directly (for SPA flows)
    """
    auth_service = get_auth_service()

    if not auth_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Authentication service not configured"
        )

    try:
        result = await auth_service.authenticate(code)

        # If redirect_to is provided, redirect with token as query param
        if redirect_to:
            return RedirectResponse(
                url=f"{redirect_to}?token={result['access_token']}"
            )

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
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )


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
    return LogoutResponse(
        success=True,
        message="Successfully logged out"
    )
