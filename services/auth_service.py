"""
GitHub OAuth authentication service for FastAPI.
Uses httpx for OAuth flow and JWT for token management.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from core.exceptions import AuthenticationError
from core.security import create_access_token, generate_user_folder_id, verify_token

logger = logging.getLogger(__name__)


def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from environment variables."""
    return os.getenv(key, default)


@dataclass
class GitHubUser:
    """Represents an authenticated GitHub user."""

    id: str
    login: str
    name: str | None
    email: str | None
    avatar_url: str | None

    @property
    def display_name(self) -> str:
        """Get the best display name for the user."""
        return self.name or self.login

    @property
    def user_folder_id(self) -> str:
        """Get a safe folder identifier for the user."""
        return generate_user_folder_id(self.id, "github")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "login": self.login,
            "name": self.name,
            "email": self.email,
            "avatar_url": self.avatar_url,
            "user_folder_id": self.user_folder_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GitHubUser":
        """Create from dictionary."""
        return cls(
            id=str(data.get("id", "")),
            login=data.get("login", ""),
            name=data.get("name"),
            email=data.get("email"),
            avatar_url=data.get("avatar_url"),
        )


class AuthService:
    """Service for handling GitHub OAuth authentication."""

    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_API_URL = "https://api.github.com/user"

    def __init__(self):
        """Initialize the authentication service."""
        self.client_id = get_config_value("GITHUB_CLIENT_ID", "")
        self.client_secret = get_config_value("GITHUB_CLIENT_SECRET", "")
        self.redirect_uri = get_config_value("GITHUB_REDIRECT_URI", "")
        self.enabled = get_config_value("AUTH_ENABLED", "false").lower() == "true"

    @property
    def is_configured(self) -> bool:
        """Check if OAuth is properly configured."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_available(self) -> bool:
        """Check if authentication is available and configured."""
        return self.enabled and self.is_configured

    def get_authorization_url(
        self, state: str | None = None, redirect_uri: str | None = None
    ) -> str:
        """
        Get the GitHub authorization URL.

        Args:
            state: Optional state parameter for CSRF protection
            redirect_uri: Optional override for redirect URI

        Returns:
            GitHub authorization URL
        """
        params = {
            "client_id": self.client_id,
            "scope": "read:user user:email",
        }
        # Only include redirect_uri if explicitly set
        effective_redirect = redirect_uri or self.redirect_uri
        if effective_redirect:
            params["redirect_uri"] = effective_redirect
        if state:
            params["state"] = state

        return f"{self.GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from GitHub callback

        Returns:
            Token response from GitHub

        Raises:
            AuthenticationError: If token exchange fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GITHUB_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} {response.text}")
                raise AuthenticationError(
                    message="Failed to exchange authorization code",
                    details={"status_code": response.status_code},
                )

            data = response.json()

            if "error" in data:
                logger.error(f"Token exchange error: {data}")
                raise AuthenticationError(
                    message=data.get("error_description", data.get("error")),
                    error_code="oauth_error",
                )

            return data

    async def get_user_info(self, access_token: str) -> GitHubUser:
        """
        Fetch user information from GitHub API.

        Args:
            access_token: GitHub access token

        Returns:
            GitHubUser object

        Raises:
            AuthenticationError: If user info fetch fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.GITHUB_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "NanoBananaLab/2.0",
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch user info: {response.status_code}")
                raise AuthenticationError(
                    message="Failed to fetch user information",
                    details={"status_code": response.status_code},
                )

            data = response.json()
            return GitHubUser.from_dict(data)

    async def authenticate(self, code: str) -> dict[str, Any]:
        """
        Complete the OAuth authentication flow.

        Args:
            code: Authorization code from GitHub callback

        Returns:
            Dictionary with JWT token and user info
        """
        # Exchange code for GitHub access token
        token_response = await self.exchange_code_for_token(code)
        github_access_token = token_response.get("access_token")

        if not github_access_token:
            raise AuthenticationError(message="No access token received")

        # Get user info
        user = await self.get_user_info(github_access_token)

        # Create JWT token
        jwt_token = create_access_token(
            data={
                "sub": user.id,
                "login": user.login,
                "name": user.name,
                "email": user.email,
                "avatar_url": user.avatar_url,
                "provider": "github",
            }
        )

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": user.to_dict(),
        }

    def get_user_from_token(self, token: str) -> GitHubUser | None:
        """
        Get user info from JWT token.

        Args:
            token: JWT token

        Returns:
            GitHubUser if valid, None otherwise
        """
        try:
            payload = verify_token(token)
            return GitHubUser(
                id=payload.get("sub", ""),
                login=payload.get("login", ""),
                name=payload.get("name"),
                email=payload.get("email"),
                avatar_url=payload.get("avatar_url"),
            )
        except AuthenticationError:
            return None


# Singleton instance
_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """Get or create the auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
