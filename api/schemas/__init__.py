"""
Pydantic schemas for API request/response models.
"""

from .common import (
    APIResponse,
    ErrorDetail,
    PaginatedResponse,
    HealthStatus,
    HealthCheckResponse,
    DetailedHealthCheckResponse,
    ComponentHealth,
    MessageResponse,
)

from .auth import (
    GitHubUserResponse,
    TokenResponse,
    AuthStatusResponse,
    LoginUrlResponse,
    OAuthCallbackRequest,
    LogoutResponse,
)

from .generate import (
    AspectRatio,
    Resolution,
    SafetyLevel,
    GenerationMode,
    GenerationSettings,
    GenerateImageRequest,
    GeneratedImage,
    GenerateImageResponse,
    BatchGenerateRequest,
    BatchGenerateResponse,
    TaskProgress,
    BlendImagesRequest,
    StyleTransferRequest,
    SearchGenerateRequest,
    CostEstimate,
)

from .quota import (
    ModeQuota,
    QuotaStatusResponse,
    QuotaCheckRequest,
    QuotaCheckResponse,
    QuotaConfigResponse,
)

from .chat import (
    ChatMessage,
    CreateChatRequest,
    CreateChatResponse,
    SendMessageRequest,
    SendMessageResponse,
    ChatSessionInfo,
    ChatHistoryResponse,
    ListChatsResponse,
)

from .history import (
    HistoryItem,
    HistorySettings,
    HistoryListResponse,
    HistoryDetailResponse,
    HistoryDeleteResponse,
    HistoryStatsResponse,
)

from .prompts import (
    PromptTemplate,
    PromptCategory,
    ListPromptsResponse,
    GeneratePromptsRequest,
    GeneratePromptsResponse,
    ToggleFavoriteResponse,
    SavePromptRequest,
    SavePromptResponse,
)

__all__ = [
    # Common
    "APIResponse",
    "ErrorDetail",
    "PaginatedResponse",
    "HealthStatus",
    "HealthCheckResponse",
    "DetailedHealthCheckResponse",
    "ComponentHealth",
    "MessageResponse",
    # Auth
    "GitHubUserResponse",
    "TokenResponse",
    "AuthStatusResponse",
    "LoginUrlResponse",
    "OAuthCallbackRequest",
    "LogoutResponse",
    # Generate
    "AspectRatio",
    "Resolution",
    "SafetyLevel",
    "GenerationMode",
    "GenerationSettings",
    "GenerateImageRequest",
    "GeneratedImage",
    "GenerateImageResponse",
    "BatchGenerateRequest",
    "BatchGenerateResponse",
    "TaskProgress",
    "BlendImagesRequest",
    "StyleTransferRequest",
    "SearchGenerateRequest",
    "CostEstimate",
    # Quota
    "ModeQuota",
    "QuotaStatusResponse",
    "QuotaCheckRequest",
    "QuotaCheckResponse",
    "QuotaConfigResponse",
    # Chat
    "ChatMessage",
    "CreateChatRequest",
    "CreateChatResponse",
    "SendMessageRequest",
    "SendMessageResponse",
    "ChatSessionInfo",
    "ChatHistoryResponse",
    "ListChatsResponse",
    # History
    "HistoryItem",
    "HistorySettings",
    "HistoryListResponse",
    "HistoryDetailResponse",
    "HistoryDeleteResponse",
    "HistoryStatsResponse",
    # Prompts
    "PromptTemplate",
    "PromptCategory",
    "ListPromptsResponse",
    "GeneratePromptsRequest",
    "GeneratePromptsResponse",
    "ToggleFavoriteResponse",
    "SavePromptRequest",
    "SavePromptResponse",
]
