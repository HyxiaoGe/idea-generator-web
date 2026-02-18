"""
Authentication-related Pydantic schemas.
"""

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    """User information from auth-service JWT."""

    id: str = Field(..., description="Auth-service user ID (UUID)")
    email: str | None = Field(None, description="Email address")
    name: str | None = Field(None, description="Display name")
    avatar_url: str | None = Field(None, description="Avatar URL")
    user_folder_id: str = Field(..., description="User's storage folder ID")


class AuthStatusResponse(BaseModel):
    """Authentication status response."""

    authenticated: bool = Field(..., description="Whether user is authenticated")
    user: UserResponse | None = Field(None, description="User info if authenticated")


class LogoutResponse(BaseModel):
    """Logout response."""

    success: bool = Field(default=True)
    message: str = Field(default="Successfully logged out")


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
