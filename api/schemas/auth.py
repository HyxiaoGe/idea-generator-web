"""
Authentication-related Pydantic schemas.
"""

from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class GitHubUserResponse(BaseModel):
    """GitHub user information."""

    id: str = Field(..., description="GitHub user ID")
    login: str = Field(..., description="GitHub username")
    name: Optional[str] = Field(None, description="Display name")
    email: Optional[str] = Field(None, description="Email address")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")
    user_folder_id: str = Field(..., description="User's storage folder ID")


class TokenResponse(BaseModel):
    """OAuth token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: GitHubUserResponse = Field(..., description="User information")


class AuthStatusResponse(BaseModel):
    """Authentication status response."""

    authenticated: bool = Field(..., description="Whether user is authenticated")
    user: Optional[GitHubUserResponse] = Field(None, description="User info if authenticated")


class LoginUrlResponse(BaseModel):
    """GitHub OAuth login URL response."""

    url: str = Field(..., description="GitHub authorization URL")
    state: Optional[str] = Field(None, description="CSRF state token")


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request body."""

    code: str = Field(..., description="Authorization code from GitHub")
    state: Optional[str] = Field(None, description="CSRF state token")


class LogoutResponse(BaseModel):
    """Logout response."""

    success: bool = Field(default=True)
    message: str = Field(default="Successfully logged out")
