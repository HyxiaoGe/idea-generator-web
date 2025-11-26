"""
API Health Check Service for monitoring Google GenAI availability.
"""
import time
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum
import streamlit as st

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


# Health check configuration
HEALTH_CHECK_INTERVAL = 60.0  # Check every 60 seconds
HEALTH_CHECK_TIMEOUT = 10.0   # Timeout for health check request
HEALTH_CHECK_MODEL = "gemini-2.0-flash"  # Use a fast model for health checks


class HealthCheckService:
    """Service for checking Google GenAI API health."""

    @staticmethod
    def init_session_state():
        """Initialize health check state in session."""
        if "health_check_result" not in st.session_state:
            st.session_state.health_check_result = HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message="Not checked yet",
                timestamp=0.0
            )
        if "health_check_in_progress" not in st.session_state:
            st.session_state.health_check_in_progress = False

    @staticmethod
    def get_last_result() -> HealthCheckResult:
        """Get the last health check result."""
        HealthCheckService.init_session_state()
        return st.session_state.health_check_result

    @staticmethod
    def should_check() -> bool:
        """Check if enough time has passed since last check."""
        HealthCheckService.init_session_state()
        last_result = st.session_state.health_check_result
        if last_result.timestamp == 0.0:
            return True
        return (time.time() - last_result.timestamp) >= HEALTH_CHECK_INTERVAL

    @staticmethod
    def is_checking() -> bool:
        """Check if a health check is in progress."""
        HealthCheckService.init_session_state()
        return st.session_state.health_check_in_progress

    @staticmethod
    def check_health(api_key: str) -> HealthCheckResult:
        """
        Perform a health check by sending a simple text request.

        Args:
            api_key: Google API key to test

        Returns:
            HealthCheckResult with status and details
        """
        HealthCheckService.init_session_state()
        st.session_state.health_check_in_progress = True

        start_time = time.time()
        result = HealthCheckResult(
            status=HealthStatus.CHECKING,
            message="Checking...",
            timestamp=time.time()
        )

        try:
            client = genai.Client(api_key=api_key)

            # Simple text-only request to test connectivity (sync call)
            response = client.models.generate_content(
                model=HEALTH_CHECK_MODEL,
                contents="Say 'OK' if you can read this.",
                config=types.GenerateContentConfig(
                    response_modalities=["Text"],
                    max_output_tokens=10,
                )
            )

            response_time = time.time() - start_time

            # Check timeout manually
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

        finally:
            st.session_state.health_check_in_progress = False
            st.session_state.health_check_result = result

        return result

    @staticmethod
    def run_check(api_key: str) -> HealthCheckResult:
        """
        Run health check (direct sync call).

        Args:
            api_key: Google API key to test

        Returns:
            HealthCheckResult with status and details
        """
        return HealthCheckService.check_health(api_key)

    @staticmethod
    def get_status_indicator() -> tuple[str, str]:
        """
        Get status indicator emoji and text for display.

        Returns:
            Tuple of (emoji, status_text)
        """
        result = HealthCheckService.get_last_result()

        if result.status == HealthStatus.HEALTHY:
            return "🟢", result.message
        elif result.status == HealthStatus.UNHEALTHY:
            return "🔴", result.message
        elif result.status == HealthStatus.CHECKING:
            return "🔄", "Checking..."
        else:
            return "⚪", "Not checked"

    @staticmethod
    def is_healthy() -> bool:
        """Check if API is currently healthy."""
        result = HealthCheckService.get_last_result()
        return result.status == HealthStatus.HEALTHY


def get_health_service() -> type[HealthCheckService]:
    """Get the health check service class."""
    return HealthCheckService
