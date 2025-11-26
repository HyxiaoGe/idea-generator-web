"""
Async Image Generator Service using Google GenAI.
"""
import os
import time
import asyncio
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass
from PIL import Image
from io import BytesIO

from google import genai
from google.genai import types
from dotenv import load_dotenv

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
    "503",
    "502",
    "504",
]


def is_retryable_error(error_msg: str) -> bool:
    """Check if an error is retryable based on error message."""
    error_lower = error_msg.lower()
    return any(keyword in error_lower for keyword in RETRYABLE_ERRORS)


def build_safety_settings(level: str = "moderate") -> List[types.SafetySetting]:
    """
    Build safety settings based on the specified level.

    Args:
        level: Safety level ("strict", "moderate", "relaxed", "none")

    Returns:
        List of SafetySetting objects
    """
    threshold = SAFETY_LEVELS.get(level, types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)
    return [
        types.SafetySetting(category=category, threshold=threshold)
        for category in HARM_CATEGORIES
    ]


@dataclass
class GenerationResult:
    """Result of an image generation."""
    image: Optional[Image.Image] = None
    text: Optional[str] = None
    thinking: Optional[str] = None
    search_sources: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None
    safety_blocked: bool = False
    safety_ratings: Optional[List] = None


class ImageGenerator:
    """Async image generator using Google GenAI."""

    MODEL_ID = "gemini-3-pro-image-preview"

    ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"]
    RESOLUTIONS = ["1K", "2K", "4K"]

    def __init__(self, api_key: Optional[str] = None):
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
            models = list(client.models.list())
            return True, "API key is valid"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
                return False, "Invalid API key"
            elif "quota" in error_msg.lower():
                return False, "API key quota exceeded"
            else:
                return False, f"Validation failed: {error_msg[:100]}"

    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "1K",
        enable_thinking: bool = False,
        enable_search: bool = False,
        safety_level: str = "moderate",
    ) -> GenerationResult:
        """
        Generate an image from a text prompt asynchronously.

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
        last_error = None

        # Build config once
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

        # Retry loop
        for attempt in range(MAX_RETRIES + 1):
            try:
                # Make async API call
                response = await self.client.aio.models.generate_content(
                    model=self.MODEL_ID,
                    contents=prompt,
                    config=config,
                )

                # Check for safety blocks
                if response.candidates:
                    candidate = response.candidates[0]

                    # Get safety ratings
                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        result.safety_ratings = [
                            {"category": str(r.category), "probability": str(r.probability)}
                            for r in candidate.safety_ratings
                        ]

                    # Check if blocked by safety filter
                    if hasattr(candidate, 'finish_reason'):
                        if str(candidate.finish_reason) == "SAFETY":
                            result.safety_blocked = True
                            result.error = "Content blocked by safety filter"
                            result.duration = time.time() - start_time
                            return result

                    # Process response parts
                    if hasattr(candidate, 'content') and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, 'thought') and part.thought:
                                result.thinking = part.text
                            elif hasattr(part, 'text') and part.text:
                                result.text = part.text
                            elif hasattr(part, 'inline_data') and part.inline_data:
                                # Convert to PIL Image
                                image_data = part.inline_data.data
                                result.image = Image.open(BytesIO(image_data))

                result.duration = time.time() - start_time
                self._record_stats(result.duration)
                return result  # Success, return immediately

            except Exception as e:
                error_msg = str(e)
                last_error = error_msg

                # Check if error is safety related (no retry)
                if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.duration = time.time() - start_time
                    return result

                # Check if error is retryable
                if is_retryable_error(error_msg) and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"Retryable error on attempt {attempt + 1}: {error_msg}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error or max retries reached
                break

        # All retries failed
        result.error = last_error
        result.duration = time.time() - start_time
        return result

    def _record_stats(self, duration: float):
        """Record generation statistics."""
        self.stats.append({
            "duration": duration,
            "timestamp": time.time()
        })

    def get_stats_summary(self) -> str:
        """Get summary of generation statistics."""
        if not self.stats:
            return "No generations recorded."
        total = sum(s["duration"] for s in self.stats)
        avg = total / len(self.stats)
        return f"Generations: {len(self.stats)} | Total: {total:.2f}s | Avg: {avg:.2f}s"

    async def blend_images(
        self,
        prompt: str,
        images: List[Image.Image],
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
        last_error = None

        if not images:
            result.error = "No images provided for blending"
            return result

        # Build contents and config once
        contents = [prompt] + images
        config = types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio
            ),
            safety_settings=build_safety_settings(safety_level),
        )

        # Retry loop
        for attempt in range(MAX_RETRIES + 1):
            try:
                # Make async API call
                response = await self.client.aio.models.generate_content(
                    model=self.MODEL_ID,
                    contents=contents,
                    config=config,
                )

                # Check for safety blocks and process response
                if response.candidates:
                    candidate = response.candidates[0]

                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        result.safety_ratings = [
                            {"category": str(r.category), "probability": str(r.probability)}
                            for r in candidate.safety_ratings
                        ]

                    if hasattr(candidate, 'finish_reason') and str(candidate.finish_reason) == "SAFETY":
                        result.safety_blocked = True
                        result.error = "Content blocked by safety filter"
                        result.duration = time.time() - start_time
                        return result

                    if hasattr(candidate, 'content') and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                result.text = part.text
                            elif hasattr(part, 'inline_data') and part.inline_data:
                                image_data = part.inline_data.data
                                result.image = Image.open(BytesIO(image_data))

                result.duration = time.time() - start_time
                self._record_stats(result.duration)
                return result  # Success

            except Exception as e:
                error_msg = str(e)
                last_error = error_msg

                if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.duration = time.time() - start_time
                    return result

                if is_retryable_error(error_msg) and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"Retryable error on attempt {attempt + 1}: {error_msg}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue

                break

        result.error = last_error
        result.duration = time.time() - start_time
        return result

    async def generate_with_search(
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
        last_error = None

        config = types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio
            ),
            tools=[{"google_search": {}}],
            safety_settings=build_safety_settings(safety_level),
        )

        # Retry loop
        for attempt in range(MAX_RETRIES + 1):
            try:
                # Make async API call
                response = await self.client.aio.models.generate_content(
                    model=self.MODEL_ID,
                    contents=prompt,
                    config=config,
                )

                # Check for safety blocks and process response
                if response.candidates:
                    candidate = response.candidates[0]

                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        result.safety_ratings = [
                            {"category": str(r.category), "probability": str(r.probability)}
                            for r in candidate.safety_ratings
                        ]

                    if hasattr(candidate, 'finish_reason') and str(candidate.finish_reason) == "SAFETY":
                        result.safety_blocked = True
                        result.error = "Content blocked by safety filter"
                        result.duration = time.time() - start_time
                        return result

                    if hasattr(candidate, 'content') and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                result.text = part.text
                            elif hasattr(part, 'inline_data') and part.inline_data:
                                image_data = part.inline_data.data
                                result.image = Image.open(BytesIO(image_data))

                    # Get search sources
                    if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                        metadata = candidate.grounding_metadata
                        if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point:
                            result.search_sources = metadata.search_entry_point.rendered_content

                result.duration = time.time() - start_time
                self._record_stats(result.duration)
                return result  # Success

            except Exception as e:
                error_msg = str(e)
                last_error = error_msg

                if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                    result.safety_blocked = True
                    result.error = "Content blocked by safety filter"
                    result.duration = time.time() - start_time
                    return result

                if is_retryable_error(error_msg) and attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"Retryable error on attempt {attempt + 1}: {error_msg}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue

                break

        result.error = last_error
        result.duration = time.time() - start_time
        return result
