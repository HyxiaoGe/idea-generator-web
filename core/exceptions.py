"""
Custom exception classes for the application.

All exceptions inherit from AppException and include:
- error_code: Machine-readable error code for i18n
- message: Human-readable error message
- status_code: HTTP status code to return
"""

from typing import Any


class AppException(Exception):
    """Base exception for all application errors."""

    error_code: str = "internal_error"
    message: str = "An unexpected error occurred"
    status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message or self.message
        self.error_code = error_code or self.error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API response."""
        result = {
            "code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    error_code = "authentication_failed"
    message = "Authentication failed"
    status_code = 401


class AuthorizationError(AppException):
    """Raised when user lacks permission."""

    error_code = "authorization_failed"
    message = "You do not have permission to perform this action"
    status_code = 403


class NotFoundError(AppException):
    """Raised when a resource is not found."""

    error_code = "not_found"
    message = "Resource not found"
    status_code = 404


class ValidationError(AppException):
    """Raised when input validation fails."""

    error_code = "validation_error"
    message = "Invalid input"
    status_code = 422


class QuotaExceededError(AppException):
    """Raised when quota limit is exceeded."""

    error_code = "quota_exceeded"
    message = "Quota limit exceeded"
    status_code = 429


class RateLimitError(AppException):
    """Raised when rate limit is exceeded."""

    error_code = "rate_limit_exceeded"
    message = "Too many requests, please try again later"
    status_code = 429


class ExternalServiceError(AppException):
    """Raised when an external service fails."""

    error_code = "external_service_error"
    message = "External service unavailable"
    status_code = 503


class ContentBlockedError(AppException):
    """Raised when content is blocked by safety filter."""

    error_code = "content_blocked"
    message = "Content blocked by safety filter"
    status_code = 400


class GenerationError(AppException):
    """Raised when image generation fails."""

    error_code = "generation_failed"
    message = "Image generation failed"
    status_code = 500


class ModelUnavailableError(AppException):
    """Raised when requested model is currently unavailable."""

    error_code = "model_unavailable"
    message = "Requested model is currently unavailable"
    status_code = 503


class GenerationTimeoutError(AppException):
    """Raised when generation times out."""

    error_code = "generation_timeout"
    message = "Generation timed out"
    status_code = 504


class StorageError(AppException):
    """Raised when storage operation fails."""

    error_code = "storage_error"
    message = "Storage operation failed"
    status_code = 500


class TaskNotFoundError(NotFoundError):
    """Raised when a task is not found."""

    error_code = "task_not_found"
    message = "Task not found"


class SessionNotFoundError(NotFoundError):
    """Raised when a chat session is not found."""

    error_code = "session_not_found"
    message = "Chat session not found"
