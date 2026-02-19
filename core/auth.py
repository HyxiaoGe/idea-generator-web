"""
Central authentication module using auth-service JWT validation.

Replaces the old GitHub OAuth auth (services/auth_service.py) with
RS256 JWT verification via the auth-client SDK.
"""

import logging
from dataclasses import dataclass, field

from auth import AuthenticatedUser, JWTValidator
from fastapi import Header

from .config import get_settings
from .exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)


@dataclass
class AppUser:
    """Application user, constructed from auth-service JWT."""

    id: str  # auth-service UUID (sub claim)
    email: str
    name: str | None
    avatar_url: str | None
    scopes: list[str] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)

    @property
    def user_folder_id(self) -> str:
        """Get the folder ID used for storage — uses auth-service sub directly."""
        return self.id

    @property
    def display_name(self) -> str:
        """Get the best display name for the user."""
        return self.name or self.email

    @property
    def is_admin(self) -> bool:
        """Check if the user has admin privileges."""
        return "admin" in self.scopes


# ============ Singleton JWTValidator ============

_validator: JWTValidator | None = None


def get_validator() -> JWTValidator:
    """Get or create the JWTValidator singleton."""
    global _validator
    if _validator is None:
        settings = get_settings()
        _validator = JWTValidator(
            jwks_url=f"{settings.auth_service_url}/.well-known/jwks.json",
            audience=settings.auth_service_client_id,
            cache_ttl=300,
        )
    return _validator


def _to_app_user(auth_user: AuthenticatedUser) -> AppUser:
    """Convert SDK AuthenticatedUser to AppUser."""
    return AppUser(
        id=auth_user.sub,
        email=auth_user.email,
        name=auth_user.raw_payload.get("name"),
        avatar_url=auth_user.raw_payload.get("avatar_url"),
        scopes=auth_user.scopes,
        raw_payload=auth_user.raw_payload,
    )


# ============ FastAPI Dependencies ============


async def get_current_user(authorization: str | None = Header(None)) -> AppUser | None:
    """
    Get current user from JWT token in Authorization header.

    Returns None if not authenticated (allows unauthenticated access).
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        validator = get_validator()
        auth_user = await validator.verify_async(parts[1])
        return _to_app_user(auth_user)
    except Exception as e:
        logger.warning("JWT verification failed: %s", e)
        return None


async def require_current_user(authorization: str | None = Header(None)) -> AppUser:
    """
    Require authenticated user.

    Raises 401 if not authenticated.
    """
    user = await get_current_user(authorization)
    if not user:
        raise AuthenticationError(message="Authentication required")
    return user


async def require_admin(authorization: str | None = Header(None)) -> AppUser:
    """
    Require admin scopes.

    Raises 401 if not authenticated, 403 if not admin.
    """
    user = await require_current_user(authorization)
    if not user.is_admin:
        raise AuthorizationError(message="Admin privileges required")
    return user
