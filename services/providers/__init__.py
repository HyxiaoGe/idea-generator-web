"""
AI Provider abstraction layer for multi-vendor support.

This module provides a unified interface for various AI image and video
generation providers including Google, OpenAI, Black Forest Labs, Runway,
and Chinese providers (Alibaba, Zhipu, ByteDance, MiniMax).
"""

# Chinese image provider implementations
from .alibaba import AlibabaProvider
from .base import (
    ERROR_TYPE_CONNECTION,
    ERROR_TYPE_INVALID_KEY,
    # Error types
    ERROR_TYPE_OVERLOADED,
    ERROR_TYPE_RATE_LIMITED,
    ERROR_TYPE_SAFETY_BLOCKED,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_UNAVAILABLE,
    ERROR_TYPE_UNKNOWN,
    ApiKeyHeaderAuth,
    # Authentication strategies
    AuthStrategy,
    AuthType,
    BaseImageProvider,
    # Base classes
    BaseProvider,
    BaseVideoProvider,
    BearerTokenAuth,
    # Circuit breaker
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    # Cost tracking
    CostRecord,
    CostTracker,
    ExecutionMode,
    GenerationRequest,
    GenerationResult,
    HmacSignatureAuth,
    HTTPProviderMixin,
    # Protocols
    ImageProvider,
    # Enums
    MediaType,
    ProviderCapability,
    ProviderConfig,
    # Data classes
    ProviderModel,
    ProviderRegion,
    RetryConfig,
    TaskInfo,
    TaskPollingMixin,
    VideoProvider,
    VolcanoEngineAuth,
    classify_error,
    get_friendly_error_message,
    # Utilities
    is_retryable_error,
)
from .bytedance import ByteDanceProvider

# China base classes
from .china_base import (
    ChinaImageProvider,
    ChinaVideoProvider,
)
from .flux import FluxProvider

# Image provider implementations (Global)
from .google import GoogleProvider
from .kling import KlingProvider
from .minimax import MiniMaxProvider
from .openai import OpenAIProvider
from .registry import (
    ProviderRegistry,
    get_provider_registry,
)

# Video provider implementations
from .runway import RunwayProvider
from .zhipu import ZhipuProvider

__all__ = [
    # Enums
    "MediaType",
    "ProviderCapability",
    "ProviderRegion",
    "ExecutionMode",
    "AuthType",
    # Data classes
    "ProviderModel",
    "GenerationRequest",
    "GenerationResult",
    "ProviderConfig",
    "RetryConfig",
    "TaskInfo",
    # Protocols
    "ImageProvider",
    "VideoProvider",
    # Base classes
    "BaseProvider",
    "BaseImageProvider",
    "BaseVideoProvider",
    "HTTPProviderMixin",
    "TaskPollingMixin",
    # China base classes
    "ChinaImageProvider",
    "ChinaVideoProvider",
    # Authentication strategies
    "AuthStrategy",
    "BearerTokenAuth",
    "ApiKeyHeaderAuth",
    "HmacSignatureAuth",
    "VolcanoEngineAuth",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerManager",
    # Cost tracking
    "CostRecord",
    "CostTracker",
    # Error types
    "ERROR_TYPE_OVERLOADED",
    "ERROR_TYPE_UNAVAILABLE",
    "ERROR_TYPE_TIMEOUT",
    "ERROR_TYPE_RATE_LIMITED",
    "ERROR_TYPE_INVALID_KEY",
    "ERROR_TYPE_SAFETY_BLOCKED",
    "ERROR_TYPE_CONNECTION",
    "ERROR_TYPE_UNKNOWN",
    # Utilities
    "is_retryable_error",
    "classify_error",
    "get_friendly_error_message",
    # Registry
    "ProviderRegistry",
    "get_provider_registry",
    # Global Image Providers
    "GoogleProvider",
    "OpenAIProvider",
    "FluxProvider",
    # Video Providers
    "RunwayProvider",
    "KlingProvider",
    # Chinese Image Providers
    "AlibabaProvider",
    "ZhipuProvider",
    "ByteDanceProvider",
    "MiniMaxProvider",
]
