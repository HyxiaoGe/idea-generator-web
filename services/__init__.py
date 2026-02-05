"""
Services module for Nano Banana Lab.

This module provides the core business logic services for the application.
Services are designed to be framework-agnostic and can be used with FastAPI.
"""

# Core generation services (legacy, for backward compatibility)
from .ai_content_moderator import AIContentModerator, get_ai_moderator
from .audit_logger import AuditLogger, get_audit_logger

# Authentication (FastAPI compatible - uses httpx)
from .auth_service import (
    AuthService,
    GitHubUser,
    get_auth_service,
)
from .chat_session import ChatSession

# Content moderation
from .content_filter import ContentFilter, get_content_filter
from .cost_estimator import CostEstimate, estimate_cost, format_cost, get_pricing_table
from .generator import ImageGenerator, get_friendly_error_message

# Health check (FastAPI compatible)
from .health_check import (
    GeminiHealthChecker,
    HealthCheckResult,
    HealthStatus,
    get_health_checker,
)

# Storage services (legacy)
from .image_storage import ImageStorage, get_storage

# Prompt services
from .prompt_generator import PromptGenerator, get_prompt_generator
from .prompt_storage import PromptStorage, get_prompt_storage

# Provider Router
from .provider_router import (
    ProviderRouter,
    RoutingDecision,
    RoutingStrategy,
    get_provider_router,
)

# Multi-provider abstraction layer
from .providers import (
    GenerationRequest,
    # Protocols
    ImageProvider,
    # Enums
    MediaType,
    ProviderCapability,
    ProviderConfig,
    # Data classes
    ProviderModel,
    # Registry
    ProviderRegistry,
    VideoProvider,
    get_provider_registry,
)
from .providers import (
    GenerationResult as ProviderGenerationResult,
)

# Quota management (Redis-based)
from .quota_service import (
    GENERATION_COOLDOWN,
    GLOBAL_DAILY_QUOTA,
    QUOTA_CONFIGS,
    QuotaConfig,
    QuotaService,
    get_quota_service,
    is_trial_mode,
)
from .r2_storage import R2Storage, get_r2_storage

# New pluggable storage system
from .storage import (
    StorageConfig,
    StorageManager,
    StorageObject,
    StorageProvider,
    get_storage_config,
    get_storage_manager,
)

# WebSocket
from .websocket_manager import WebSocketManager, get_websocket_manager

__all__ = [
    # Legacy Generator (backward compatibility)
    "ImageGenerator",
    "get_friendly_error_message",
    "ChatSession",
    # Cost
    "estimate_cost",
    "format_cost",
    "get_pricing_table",
    "CostEstimate",
    # Storage (legacy)
    "ImageStorage",
    "get_storage",
    "R2Storage",
    "get_r2_storage",
    # Storage (new pluggable system)
    "StorageConfig",
    "StorageObject",
    "StorageProvider",
    "StorageManager",
    "get_storage_manager",
    "get_storage_config",
    # Health
    "GeminiHealthChecker",
    "HealthCheckResult",
    "HealthStatus",
    "get_health_checker",
    # Auth
    "AuthService",
    "GitHubUser",
    "get_auth_service",
    # Quota
    "QuotaService",
    "QuotaConfig",
    "get_quota_service",
    "is_trial_mode",
    "QUOTA_CONFIGS",
    "GLOBAL_DAILY_QUOTA",
    "GENERATION_COOLDOWN",
    # Prompts
    "PromptGenerator",
    "get_prompt_generator",
    "PromptStorage",
    "get_prompt_storage",
    # Content moderation
    "ContentFilter",
    "get_content_filter",
    "AIContentModerator",
    "get_ai_moderator",
    "AuditLogger",
    "get_audit_logger",
    # Multi-provider abstraction
    "MediaType",
    "ProviderCapability",
    "ProviderModel",
    "GenerationRequest",
    "ProviderGenerationResult",
    "ProviderConfig",
    "ImageProvider",
    "VideoProvider",
    "ProviderRegistry",
    "get_provider_registry",
    # Provider Router
    "ProviderRouter",
    "RoutingStrategy",
    "RoutingDecision",
    "get_provider_router",
    # WebSocket
    "WebSocketManager",
    "get_websocket_manager",
]
