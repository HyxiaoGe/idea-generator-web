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
]
