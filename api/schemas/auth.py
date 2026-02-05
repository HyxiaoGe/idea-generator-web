"""
Authentication-related Pydantic schemas.
"""

from pydantic import BaseModel, Field


class GitHubUserResponse(BaseModel):
    """GitHub user information."""

    id: str = Field(..., description="GitHub user ID")
    login: str = Field(..., description="GitHub username")
    name: str | None = Field(None, description="Display name")
    email: str | None = Field(None, description="Email address")
    avatar_url: str | None = Field(None, description="Avatar URL")
    user_folder_id: str = Field(..., description="User's storage folder ID")


class TokenResponse(BaseModel):
    """OAuth token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: GitHubUserResponse = Field(..., description="User information")


class AuthStatusResponse(BaseModel):
    """Authentication status response."""

    authenticated: bool = Field(..., description="Whether user is authenticated")
    user: GitHubUserResponse | None = Field(None, description="User info if authenticated")


class LoginUrlResponse(BaseModel):
    """GitHub OAuth login URL response."""

    url: str = Field(..., description="GitHub authorization URL")
    state: str | None = Field(None, description="CSRF state token")


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request body."""

    code: str = Field(..., description="Authorization code from GitHub")
    state: str | None = Field(None, description="CSRF state token")


class LogoutResponse(BaseModel):
    """Logout response."""

    success: bool = Field(default=True)
    message: str = Field(default="Successfully logged out")


# ============ Token Refresh ============


class RefreshTokenRequest(BaseModel):
    """Request for token refresh."""

    refresh_token: str = Field(..., description="Refresh token")


class RefreshTokenResponse(BaseModel):
    """Response for token refresh."""

    access_token: str = Field(..., description="New JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")


# ============ Sessions ============


class SessionInfo(BaseModel):
    """Information about an active session."""

    id: str = Field(..., description="Session ID")
    device: str | None = Field(None, description="Device information")
    ip_address: str | None = Field(None, description="IP address")
    user_agent: str | None = Field(None, description="User agent string")
    last_active: str | None = Field(None, description="Last activity timestamp")
    created_at: str = Field(..., description="Session creation timestamp")
    is_current: bool = Field(default=False, description="Whether this is the current session")


class ListSessionsResponse(BaseModel):
    """Response for listing sessions."""

    sessions: list[SessionInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of sessions")


class RevokeSessionResponse(BaseModel):
    """Response for revoking a session."""

    success: bool = True
    message: str = Field(default="Session revoked successfully")


# ============ API Keys ============


class APIKeyScope(BaseModel):
    """API Key scope/permission."""

    name: str = Field(..., description="Scope name (e.g., 'generate:read', 'generate:write')")
    description: str | None = Field(None, description="Scope description")


class CreateAPIKeyRequest(BaseModel):
    """Request for creating an API key."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name for the API key",
    )
    scopes: list[str] | None = Field(
        default=None,
        description="Scopes/permissions for the key (None = all permissions)",
    )
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Number of days until expiration (None = never expires)",
    )


class CreateAPIKeyResponse(BaseModel):
    """Response for creating an API key."""

    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key: str = Field(
        ...,
        description="The full API key (only shown once!)",
    )
    key_prefix: str = Field(..., description="Key prefix for identification")
    scopes: list[str] | None = Field(None, description="Granted scopes")
    expires_at: str | None = Field(None, description="Expiration timestamp")
    created_at: str = Field(..., description="Creation timestamp")


class APIKeyInfo(BaseModel):
    """API key information (without the actual key)."""

    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key_prefix: str = Field(..., description="Key prefix (e.g., 'nb_sk_abc...')")
    scopes: list[str] | None = Field(None, description="Granted scopes")
    last_used_at: str | None = Field(None, description="Last usage timestamp")
    expires_at: str | None = Field(None, description="Expiration timestamp")
    created_at: str = Field(..., description="Creation timestamp")
    is_expired: bool = Field(default=False, description="Whether the key has expired")


class ListAPIKeysResponse(BaseModel):
    """Response for listing API keys."""

    keys: list[APIKeyInfo] = Field(default_factory=list)
    total: int = Field(..., description="Total number of API keys")


class DeleteAPIKeyResponse(BaseModel):
    """Response for deleting an API key."""

    success: bool = True
    message: str = Field(default="API key deleted successfully")
