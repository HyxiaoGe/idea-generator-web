"""
Services module for Nano Banana Lab.
"""
from .generator import ImageGenerator, get_friendly_error_message
from .chat_session import ChatSession
from .cost_estimator import estimate_cost, format_cost, get_pricing_table, CostEstimate
from .image_storage import ImageStorage, get_storage, get_current_user_storage
from .r2_storage import R2Storage, get_r2_storage
from .persistence import PersistenceService, get_persistence, init_from_persistence
from .generation_state import (
    GenerationStateManager,
    GenerationStatus,
    GenerationTask,
)
from .history_sync import HistorySyncManager, get_history_sync, get_current_user_history_sync
from .health_check import (
    HealthCheckService,
    HealthCheckResult,
    HealthStatus,
    get_health_service,
)
from .auth import (
    AuthService,
    GitHubUser,
    get_auth_service,
    init_auth,
    is_authenticated,
    get_current_user,
    get_user_id,
    require_auth,
)
from .prompt_generator import PromptGenerator, get_prompt_generator
from .prompt_storage import PromptStorage, get_prompt_storage, get_current_user_prompt_storage
from .trial_quota import (
    TrialQuotaService,
    get_trial_quota_service,
    is_trial_mode,
    QUOTA_CONFIGS,
    GLOBAL_DAILY_QUOTA,
)

__all__ = [
    "ImageGenerator",
    "get_friendly_error_message",
    "ChatSession",
    "estimate_cost",
    "format_cost",
    "get_pricing_table",
    "CostEstimate",
    "ImageStorage",
    "get_storage",
    "get_current_user_storage",
    "R2Storage",
    "get_r2_storage",
    "PersistenceService",
    "get_persistence",
    "init_from_persistence",
    "GenerationStateManager",
    "GenerationStatus",
    "GenerationTask",
    "HistorySyncManager",
    "get_history_sync",
    "get_current_user_history_sync",
    "HealthCheckService",
    "HealthCheckResult",
    "HealthStatus",
    "get_health_service",
    "AuthService",
    "GitHubUser",
    "get_auth_service",
    "init_auth",
    "is_authenticated",
    "get_current_user",
    "get_user_id",
    "require_auth",
    "PromptGenerator",
    "get_prompt_generator",
    "PromptStorage",
    "get_prompt_storage",
    "get_current_user_prompt_storage",
    "TrialQuotaService",
    "get_trial_quota_service",
    "is_trial_mode",
    "QUOTA_CONFIGS",
    "GLOBAL_DAILY_QUOTA",
]
