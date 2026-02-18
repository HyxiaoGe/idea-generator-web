"""
Security utilities for authentication.
"""


def extract_token_from_header(authorization: str | None) -> str | None:
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
