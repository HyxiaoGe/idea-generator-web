"""
Services module for Nano Banana Lab.

This module provides the core business logic services for the application.
Services are designed to be framework-agnostic and can be used with FastAPI.
"""

# Core generation services
from .generator import ImageGenerator, get_friendly_error_message
from .chat_session import ChatSession
from .cost_estimator import estimate_cost, format_cost, get_pricing_table, CostEstimate

# Storage services
from .image_storage import ImageStorage, get_storage
from .r2_storage import R2Storage, get_r2_storage

# Health check (FastAPI compatible)
from .health_check import (
    GeminiHealthChecker,
    HealthCheckResult,
    HealthStatus,
    get_health_checker,
)

# Authentication (FastAPI compatible - uses httpx)
from .auth_service import (
    AuthService,
    GitHubUser,
    get_auth_service,
)

# Quota management (Redis-based)
from .quota_service import (
    QuotaService,
    QuotaConfig,
    get_quota_service,
    is_trial_mode,
    QUOTA_CONFIGS,
    GLOBAL_DAILY_QUOTA,
    GENERATION_COOLDOWN,
)

# Prompt services
from .prompt_generator import PromptGenerator, get_prompt_generator
from .prompt_storage import PromptStorage, get_prompt_storage

# Content moderation
from .content_filter import ContentFilter, get_content_filter
from .ai_content_moderator import AIContentModerator, get_ai_moderator
from .audit_logger import AuditLogger, get_audit_logger

__all__ = [
    # Generator
    "ImageGenerator",
    "get_friendly_error_message",
    "ChatSession",
    # Cost
    "estimate_cost",
    "format_cost",
    "get_pricing_table",
    "CostEstimate",
    # Storage
    "ImageStorage",
    "get_storage",
    "R2Storage",
    "get_r2_storage",
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
]
