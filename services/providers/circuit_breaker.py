"""
Circuit breaker pattern for provider fault tolerance.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: float = 60.0  # Seconds before trying half-open
    half_open_max_calls: int = 1  # Max concurrent calls in half-open state


class CircuitBreaker:
    """Circuit breaker for provider fault tolerance."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = "closed"  # closed, open, half-open
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0
        self._half_open_calls = 0

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time > self.config.timeout:
                self.state = "half-open"
                self._half_open_calls = 0
                logger.info(f"[CircuitBreaker:{self.name}] Transitioning to half-open")
                return True
            return False

        # Half-open state - allow limited calls
        if self._half_open_calls < self.config.half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == "half-open":
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = "closed"
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"[CircuitBreaker:{self.name}] Circuit closed")
        else:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "half-open":
            self.state = "open"
            self.success_count = 0
            logger.warning(f"[CircuitBreaker:{self.name}] Circuit reopened after half-open failure")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = "open"
            self.success_count = 0
            logger.warning(
                f"[CircuitBreaker:{self.name}] Circuit opened after {self.failure_count} failures"
            )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self.state = "closed"
        self.failure_count = 0
        self.success_count = 0
        self._half_open_calls = 0

    def get_status(self) -> dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
        }


class CircuitBreakerManager:
    """Manages circuit breakers for all providers."""

    _breakers: dict[str, CircuitBreaker] = {}

    @classmethod
    def get(cls, provider_name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        """Get or create a circuit breaker for a provider."""
        if provider_name not in cls._breakers:
            cls._breakers[provider_name] = CircuitBreaker(provider_name, config)
        return cls._breakers[provider_name]

    @classmethod
    def reset(cls, provider_name: str) -> bool:
        """Reset a specific circuit breaker."""
        if provider_name in cls._breakers:
            cls._breakers[provider_name].reset()
            return True
        return False

    @classmethod
    def reset_all(cls) -> None:
        """Reset all circuit breakers."""
        for breaker in cls._breakers.values():
            breaker.reset()

    @classmethod
    def get_all_status(cls) -> dict[str, dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in cls._breakers.items()}
