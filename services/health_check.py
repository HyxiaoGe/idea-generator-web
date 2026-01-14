"""
API Health Check Service for monitoring Google GenAI availability.
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """API health status."""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    CHECKING = "checking"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    status: HealthStatus
    message: str
    response_time: float = 0.0
    timestamp: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "message": self.message,
            "response_time": self.response_time,
            "timestamp": self.timestamp,
            "error": self.error,
        }


# Health check configuration
HEALTH_CHECK_TIMEOUT = 10.0   # Timeout for health check request
HEALTH_CHECK_MODEL = "gemini-2.0-flash"  # Use a fast model for health checks


class GeminiHealthChecker:
    """Service for checking Google GenAI API health."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the health checker.

        Args:
            api_key: Google API key to use for health checks
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._last_result: Optional[HealthCheckResult] = None
        self._last_check_time: float = 0.0

    @property
    def api_key(self) -> Optional[str]:
        """Get the API key."""
        return self._api_key

    @api_key.setter
    def api_key(self, value: str):
        """Set the API key."""
        self._api_key = value

    @property
    def last_result(self) -> Optional[HealthCheckResult]:
        """Get the last health check result."""
        return self._last_result

    def check_health(self, api_key: Optional[str] = None) -> HealthCheckResult:
        """
        Perform a health check by sending a simple text request.

        Args:
            api_key: Optional API key override

        Returns:
            HealthCheckResult with status and details
        """
        effective_key = api_key or self._api_key

        if not effective_key:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="No API key configured",
                timestamp=time.time(),
                error="Missing API key"
            )

        start_time = time.time()

        try:
            client = genai.Client(api_key=effective_key)

            # Simple text-only request to test connectivity
            response = client.models.generate_content(
                model=HEALTH_CHECK_MODEL,
                contents="Say 'OK' if you can read this.",
                config=types.GenerateContentConfig(
                    response_modalities=["Text"],
                    max_output_tokens=10,
                )
            )

            response_time = time.time() - start_time

            # Check timeout
            if response_time > HEALTH_CHECK_TIMEOUT:
                result = HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message=f"API slow ({response_time:.1f}s)",
                    response_time=response_time,
                    timestamp=time.time(),
                    error="Slow response"
                )
            # Check if we got a valid response
            elif response.candidates and len(response.candidates) > 0:
                result = HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message=f"API is responsive ({response_time:.1f}s)",
                    response_time=response_time,
                    timestamp=time.time()
                )
            else:
                result = HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message="API returned empty response",
                    response_time=response_time,
                    timestamp=time.time(),
                    error="Empty response"
                )

        except Exception as e:
            error_msg = str(e)
            response_time = time.time() - start_time

            # Categorize the error
            if "api_key" in error_msg.lower() or "invalid" in error_msg.lower():
                message = "Invalid API key"
            elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
                message = "API quota/rate limit exceeded"
            elif "server disconnected" in error_msg.lower():
                message = "Server disconnected"
            elif "timeout" in error_msg.lower():
                message = "Connection timeout"
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                message = "Network error"
            else:
                message = f"API error: {error_msg[:50]}"

            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=message,
                response_time=response_time,
                timestamp=time.time(),
                error=error_msg
            )
            logger.warning(f"Health check failed: {error_msg}")

        self._last_result = result
        self._last_check_time = time.time()
        return result

    async def check_health_async(self, api_key: Optional[str] = None) -> HealthCheckResult:
        """
        Perform a health check asynchronously.

        Note: Currently runs sync internally. Can be converted to true async
        when google-genai supports async natively.
        """
        # For now, just wrap the sync call
        # TODO: Use async when available
        return self.check_health(api_key)

    def is_healthy(self) -> bool:
        """Check if API is currently healthy based on last check."""
        if self._last_result is None:
            return False
        return self._last_result.status == HealthStatus.HEALTHY

    def get_status_indicator(self) -> tuple[str, str]:
        """
        Get status indicator emoji and text for display.

        Returns:
            Tuple of (emoji, status_text)
        """
        if self._last_result is None:
            return "⚪", "Not checked"

        if self._last_result.status == HealthStatus.HEALTHY:
            return "🟢", self._last_result.message
        elif self._last_result.status == HealthStatus.UNHEALTHY:
            return "🔴", self._last_result.message
        elif self._last_result.status == HealthStatus.CHECKING:
            return "🔄", "Checking..."
        else:
            return "⚪", "Unknown"


# Singleton instance
_health_checker: Optional[GeminiHealthChecker] = None


def get_health_checker(api_key: Optional[str] = None) -> GeminiHealthChecker:
    """Get or create the health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = GeminiHealthChecker(api_key=api_key)
    elif api_key and _health_checker.api_key != api_key:
        _health_checker.api_key = api_key
    return _health_checker
