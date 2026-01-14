"""
Security utilities for JWT token handling and authentication.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import jwt, JWTError

from .config import get_settings
from .exceptions import AuthenticationError


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    settings = get_settings()

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise AuthenticationError(
            message="Invalid or expired token",
            details={"error": str(e)},
        )


def generate_user_folder_id(user_id: str, provider: str = "github") -> str:
    """
    Generate a safe folder identifier for user data isolation.

    Uses MD5 hash for privacy and filesystem safety.

    Args:
        user_id: User's unique identifier
        provider: Authentication provider (github, etc.)

    Returns:
        16-character hex string suitable for folder names
    """
    return hashlib.md5(f"{provider}_{user_id}".encode()).hexdigest()[:16]


def extract_token_from_header(authorization: Optional[str]) -> Optional[str]:
    """
    Extract JWT token from Authorization header.

    Supports "Bearer <token>" format.

    Args:
        authorization: Authorization header value

    Returns:
        Token string or None if not present/invalid format
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]
