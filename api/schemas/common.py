"""
Common Pydantic schemas used across the API.
"""

from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar, Optional, List, Dict, Any

from pydantic import BaseModel, Field


T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail for API responses."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details"
    )


class APIResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper.

    All API endpoints should return responses in this format.
    """

    success: bool = Field(..., description="Whether the request was successful")
    data: Optional[T] = Field(default=None, description="Response data")
    error: Optional[ErrorDetail] = Field(default=None, description="Error details if failed")

    @classmethod
    def ok(cls, data: T) -> "APIResponse[T]":
        """Create a successful response."""
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> "APIResponse[None]":
        """Create a failed response."""
        return cls(
            success=False,
            error=ErrorDetail(code=code, message=message, details=details)
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: List[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Starting offset")
    has_more: bool = Field(..., description="Whether more items exist")


class HealthStatus(str, Enum):
    """Health check status enum."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    status: HealthStatus
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


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
    components: Dict[str, ComponentHealth] = Field(
        default_factory=dict,
        description="Health status of each component"
    )


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
    success: bool = True
