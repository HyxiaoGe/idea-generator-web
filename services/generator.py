"""
Image Generator Service using Google GenAI.
"""

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

load_dotenv()

logger = logging.getLogger(__name__)


# Safety level presets
SAFETY_LEVELS = {
    "strict": types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    "moderate": types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    "relaxed": types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    "none": types.HarmBlockThreshold.BLOCK_NONE,
}

HARM_CATEGORIES = [
    types.HarmCategory.HARM_CATEGORY_HARASSMENT,
    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
]


# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # Exponential backoff delays in seconds

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

# Error type constants for i18n mapping
ERROR_TYPE_OVERLOADED = "overloaded"
ERROR_TYPE_UNAVAILABLE = "unavailable"
ERROR_TYPE_TIMEOUT = "timeout"
ERROR_TYPE_RATE_LIMITED = "rate_limited"
ERROR_TYPE_INVALID_KEY = "invalid_key"
ERROR_TYPE_SAFETY_BLOCKED = "safety_blocked"
ERROR_TYPE_CONNECTION = "connection"
ERROR_TYPE_UNKNOWN = "unknown"


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
    elif "api_key" in error_lower or "invalid" in error_lower:
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


def build_safety_settings(level: str = "moderate") -> list[types.SafetySetting]:
    """
    Build safety settings based on the specified level.

    Args:
        level: Safety level ("strict", "moderate", "relaxed", "none")

    Returns:
        List of SafetySetting objects
    """
    threshold = SAFETY_LEVELS.get(level, types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)
    return [
        types.SafetySetting(category=category, threshold=threshold) for category in HARM_CATEGORIES
    ]


@dataclass
class GenerationResult:
    """Result of an image generation."""

    image: Image.Image | None = None
    text: str | None = None
    thinking: str | None = None
    search_sources: str | None = None
    duration: float = 0.0
    error: str | None = None
    safety_blocked: bool = False
    safety_ratings: list | None = None


class ImageGenerator:
    """Image generator using Google GenAI."""

    MODEL_ID = "gemini-3-pro-image-preview"

    ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"]
    RESOLUTIONS = ["1K", "2K", "4K"]

    def __init__(self, api_key: str | None = None):
        """
        Initialize the image generator.

        Args:
            api_key: Google API key. If not provided, will try to get from environment.
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY not found")
        self.client = genai.Client(api_key=self._api_key)
        self.stats = []

    def update_api_key(self, api_key: str):
        """Update the API key and reinitialize the client."""
        self._api_key = api_key
        self.client = genai.Client(api_key=api_key)

    @property
    def api_key(self) -> str:
        """Get the current API key (masked)."""
        if self._api_key:
            return self._api_key[:8] + "..." + self._api_key[-4:]
        return ""

    @staticmethod
    def validate_api_key(api_key: str) -> tuple[bool, str]:
        """
        Validate an API key by making a simple request.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not api_key or len(api_key) < 10:
            return False, "API key is too short"

        try:
            client = genai.Client(api_key=api_key)
            # Try to list models as a simple validation
            # This is a lightweight call that verifies the key works
            list(client.models.list())
            return True, "API key is valid"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
                return False, "Invalid API key"
            elif "quota" in error_msg.lower():
                return False, "API key quota exceeded"
            else:
                return False, f"Validation failed: {error_msg[:100]}"

    def _execute_with_retry(
        self,
        api_call: Callable[[], Any],
        result: GenerationResult,
        start_time: float,
    ) -> tuple[Any, str | None]:
        """
        Execute an API call with retry logic.

        Args:
            api_call: Callable that makes the API request
            result: GenerationResult to update on safety errors
            start_time: Start timestamp for duration calculation

        Returns:
            Tuple of (response, last_error) - response is None if all retries failed
        """
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = api_call()
                return response, None

            except Exception as e:
                error_msg = str(e)
                last_error = error_msg

                # Check if error is safety related (no retry)
                if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.duration = time.time() - start_time
                    return None, error_msg

                # Check if error is retryable
                if is_retryable_error(error_msg) and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Retryable error on attempt {attempt + 1}: {error_msg}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                    continue

                # Non-retryable error or max retries reached
                break

        return None, last_error

    def _process_response(
        self,
        response: Any,
        result: GenerationResult,
        extract_search: bool = False,
    ) -> bool:
        """
        Process API response and extract data into result.

        Args:
            response: API response object
            result: GenerationResult to populate
            extract_search: Whether to extract search grounding metadata

        Returns:
            True if response was successfully processed, False if safety blocked
        """
        if not response.candidates:
            return True

        candidate = response.candidates[0]

        # Extract safety ratings
        if hasattr(candidate, "safety_ratings") and candidate.safety_ratings:
            result.safety_ratings = [
                {"category": str(r.category), "probability": str(r.probability)}
                for r in candidate.safety_ratings
            ]

        # Check if blocked by safety filter
        if hasattr(candidate, "finish_reason") and str(candidate.finish_reason) == "SAFETY":
            result.safety_blocked = True
            result.error = "Content blocked by safety filter"
            return False

        # Process response parts
        if hasattr(candidate, "content") and candidate.content:
            for part in candidate.content.parts:
                if hasattr(part, "thought") and part.thought:
                    result.thinking = part.text
                elif hasattr(part, "text") and part.text:
                    result.text = part.text
                elif hasattr(part, "inline_data") and part.inline_data:
                    image_data = part.inline_data.data
                    result.image = Image.open(BytesIO(image_data))

        # Extract search sources if requested
        if (
            extract_search
            and hasattr(candidate, "grounding_metadata")
            and candidate.grounding_metadata
        ):
            metadata = candidate.grounding_metadata
            if hasattr(metadata, "search_entry_point") and metadata.search_entry_point:
                result.search_sources = metadata.search_entry_point.rendered_content

        return True

    def _record_stats(self, duration: float):
        """Record generation statistics."""
        self.stats.append({"duration": duration, "timestamp": time.time()})

    def get_stats_summary(self) -> str:
        """Get summary of generation statistics."""
        if not self.stats:
            return "No generations recorded."
        total = sum(s["duration"] for s in self.stats)
        avg = total / len(self.stats)
        return f"Generations: {len(self.stats)} | Total: {total:.2f}s | Avg: {avg:.2f}s"

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "1K",
        enable_thinking: bool = False,
        enable_search: bool = False,
        safety_level: str = "moderate",
    ) -> GenerationResult:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            aspect_ratio: Image aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4)
            resolution: Image resolution (1K, 2K, 4K)
            enable_thinking: Whether to include model's thinking process
            enable_search: Whether to enable search grounding
            safety_level: Content safety level ("strict", "moderate", "relaxed", "none")

        Returns:
            GenerationResult with image, text, and metadata
        """
        start_time = time.time()
        result = GenerationResult()

        # Build config
        config_dict = {
            "response_modalities": ["Text", "Image"],
            "image_config": {
                "aspect_ratio": aspect_ratio,
            },
            "safety_settings": build_safety_settings(safety_level),
        }

        # Add resolution for higher quality
        if resolution in ["2K", "4K"]:
            config_dict["image_config"]["image_size"] = resolution

        # Add thinking config
        if enable_thinking:
            config_dict["thinking_config"] = {"include_thoughts": True}

        config = types.GenerateContentConfig(**config_dict)

        # Define API call
        def api_call():
            return self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=prompt,
                config=config,
            )

        # Execute with retry
        response, last_error = self._execute_with_retry(api_call, result, start_time)

        if response is None:
            if not result.error:  # Not a safety error
                result.error = last_error
            result.duration = time.time() - start_time
            return result

        # Process response
        if not self._process_response(response, result):
            result.duration = time.time() - start_time
            return result

        result.duration = time.time() - start_time
        self._record_stats(result.duration)
        return result

    def blend_images(
        self,
        prompt: str,
        images: list[Image.Image],
        aspect_ratio: str = "1:1",
        safety_level: str = "moderate",
    ) -> GenerationResult:
        """
        Blend multiple images based on a prompt.

        Args:
            prompt: Description of how to combine the images
            images: List of PIL Image objects to blend (max 14 for Pro model)
            aspect_ratio: Output aspect ratio
            safety_level: Content safety level

        Returns:
            GenerationResult with blended image
        """
        start_time = time.time()
        result = GenerationResult()

        if not images:
            result.error = "No images provided for blending"
            return result

        # Build contents and config
        contents = [prompt] + images
        config = types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            safety_settings=build_safety_settings(safety_level),
        )

        # Define API call
        def api_call():
            return self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=contents,
                config=config,
            )

        # Execute with retry
        response, last_error = self._execute_with_retry(api_call, result, start_time)

        if response is None:
            if not result.error:
                result.error = last_error
            result.duration = time.time() - start_time
            return result

        # Process response
        if not self._process_response(response, result):
            result.duration = time.time() - start_time
            return result

        result.duration = time.time() - start_time
        self._record_stats(result.duration)
        return result

    def generate_with_search(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        safety_level: str = "moderate",
    ) -> GenerationResult:
        """
        Generate an image using real-time search data.

        Args:
            prompt: Text description that benefits from real-time data
            aspect_ratio: Image aspect ratio
            safety_level: Content safety level

        Returns:
            GenerationResult with image and search sources
        """
        start_time = time.time()
        result = GenerationResult()

        config = types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            tools=[{"google_search": {}}],
            safety_settings=build_safety_settings(safety_level),
        )

        # Define API call
        def api_call():
            return self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=prompt,
                config=config,
            )

        # Execute with retry
        response, last_error = self._execute_with_retry(api_call, result, start_time)

        if response is None:
            if not result.error:
                result.error = last_error
            result.duration = time.time() - start_time
            return result

        # Process response with search extraction
        if not self._process_response(response, result, extract_search=True):
            result.duration = time.time() - start_time
            return result

        result.duration = time.time() - start_time
        self._record_stats(result.duration)
        return result
