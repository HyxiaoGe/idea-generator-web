"""
Shared error classification and user-friendly error messages.

Used by both the legacy generator and multi-provider abstraction layer.
"""

# Error type constants for i18n mapping
ERROR_TYPE_OVERLOADED = "overloaded"
ERROR_TYPE_UNAVAILABLE = "unavailable"
ERROR_TYPE_TIMEOUT = "timeout"
ERROR_TYPE_RATE_LIMITED = "rate_limited"
ERROR_TYPE_INVALID_KEY = "invalid_key"
ERROR_TYPE_SAFETY_BLOCKED = "safety_blocked"
ERROR_TYPE_CONNECTION = "connection"
ERROR_TYPE_UNKNOWN = "unknown"

# Network-related error keywords that should trigger retry
RETRYABLE_ERRORS = [
    "server disconnected",
    "connection reset",
    "connection refused",
    "timeout",
    "network",
    "unavailable",
    "overloaded",
    "503",
    "502",
    "504",
]


def is_retryable_error(error_msg: str) -> bool:
    """Check if an error is retryable based on error message."""
    error_lower = error_msg.lower()
    return any(keyword in error_lower for keyword in RETRYABLE_ERRORS)


def classify_error(error_msg: str) -> str:
    """
    Classify error message into error type for i18n lookup.

    Returns:
        Error type constant string for i18n key mapping
    """
    error_lower = error_msg.lower()

    if "overloaded" in error_lower or ("503" in error_lower and "unavailable" in error_lower):
        return ERROR_TYPE_OVERLOADED
    elif "503" in error_lower or "unavailable" in error_lower:
        return ERROR_TYPE_UNAVAILABLE
    elif "timeout" in error_lower:
        return ERROR_TYPE_TIMEOUT
    elif "quota" in error_lower or "rate" in error_lower:
        return ERROR_TYPE_RATE_LIMITED
    elif "api_key" in error_lower or "api key" in error_lower or "invalid key" in error_lower:
        return ERROR_TYPE_INVALID_KEY
    elif "safety" in error_lower or "blocked" in error_lower:
        return ERROR_TYPE_SAFETY_BLOCKED
    elif "server disconnected" in error_lower or "connection" in error_lower:
        return ERROR_TYPE_CONNECTION
    else:
        return ERROR_TYPE_UNKNOWN


def get_friendly_error_message(error_msg: str, translator=None) -> str:
    """
    Convert technical error messages to user-friendly messages.

    Args:
        error_msg: The technical error message
        translator: Optional Translator instance for i18n support

    Returns:
        User-friendly error message
    """
    error_type = classify_error(error_msg)

    # If translator is provided, use i18n
    if translator:
        i18n_key = f"errors.api.{error_type}"
        translated = translator.get(i18n_key)
        # If key exists and is not the key itself, return translated message
        if translated != i18n_key:
            return translated

    # Fallback to hardcoded bilingual messages
    fallback_messages = {
        ERROR_TYPE_OVERLOADED: "模型繁忙，请稍后重试 (Model overloaded)",
        ERROR_TYPE_UNAVAILABLE: "服务暂时不可用，请稍后重试 (Service unavailable)",
        ERROR_TYPE_TIMEOUT: "请求超时，请重试 (Request timeout)",
        ERROR_TYPE_RATE_LIMITED: "API 配额已用尽或请求过快 (Rate limited)",
        ERROR_TYPE_INVALID_KEY: "API Key 无效，请检查配置 (Invalid API key)",
        ERROR_TYPE_SAFETY_BLOCKED: "内容被安全过滤器拦截 (Blocked by safety filter)",
        ERROR_TYPE_CONNECTION: "网络连接异常，请重试 (Connection error)",
    }

    if error_type in fallback_messages:
        return fallback_messages[error_type]

    # Return original message if no match, but truncate if too long
    return error_msg[:200] if len(error_msg) > 200 else error_msg
