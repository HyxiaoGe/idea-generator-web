"""
Common Pydantic schemas used across the API.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail for API responses."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")


class APIResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper.

    All API endpoints should return responses in this format.
    """

    success: bool = Field(..., description="Whether the request was successful")
    data: T | None = Field(default=None, description="Response data")
    error: ErrorDetail | None = Field(default=None, description="Error details if failed")

    @classmethod
    def ok(cls, data: T) -> "APIResponse[T]":
        """Create a successful response."""
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls, code: str, message: str, details: dict[str, Any] | None = None
    ) -> "APIResponse[None]":
        """Create a failed response."""
        return cls(success=False, error=ErrorDetail(code=code, message=message, details=details))


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Starting offset")
    has_more: bool = Field(..., description="Whether more items exist")


class HealthStatus(StrEnum):
    """Health check status enum."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    status: HealthStatus
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] | None = None


class HealthCheckResponse(BaseModel):
    """Basic health check response."""

    status: HealthStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class DetailedHealthCheckResponse(BaseModel):
    """Detailed health check response with component status."""

    status: HealthStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    version: str
    environment: str
    uptime_seconds: float
    components: dict[str, ComponentHealth] = Field(
        default_factory=dict, description="Health status of each component"
    )


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
    success: bool = True
