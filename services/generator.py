"""
Async Image Generator Service using Google GenAI.
"""
import os
import time
import asyncio
from typing import Optional, Tuple
from dataclasses import dataclass
from PIL import Image
from io import BytesIO

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


@dataclass
class GenerationResult:
    """Result of an image generation."""
    image: Optional[Image.Image] = None
    text: Optional[str] = None
    thinking: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None


class ImageGenerator:
    """Async image generator using Google GenAI."""

    MODEL_ID = "gemini-2.0-flash-preview-image-generation"

    ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"]
    RESOLUTIONS = ["1K", "2K", "4K"]

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        self.client = genai.Client(api_key=api_key)
        self.stats = []

    async def generate(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "1K",
        enable_thinking: bool = False,
        enable_search: bool = False,
    ) -> GenerationResult:
        """
        Generate an image from a text prompt asynchronously.

        Args:
            prompt: Text description of the image to generate
            aspect_ratio: Image aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4)
            resolution: Image resolution (1K, 2K, 4K)
            enable_thinking: Whether to include model's thinking process
            enable_search: Whether to enable search grounding

        Returns:
            GenerationResult with image, text, and metadata
        """
        start_time = time.time()
        result = GenerationResult()

        try:
            # Build config
            config_dict = {
                "response_modalities": ["Text", "Image"],
                "image_config": {
                    "aspect_ratio": aspect_ratio,
                }
            }

            # Add resolution for higher quality
            if resolution in ["2K", "4K"]:
                config_dict["image_config"]["image_size"] = resolution

            # Add thinking config
            if enable_thinking:
                config_dict["thinking_config"] = {"include_thoughts": True}

            # Add search tool
            tools = []
            if enable_search:
                tools = [{"google_search": {}}]

            config = types.GenerateContentConfig(**config_dict)

            # Make async API call
            response = await self.client.aio.models.generate_content(
                model=self.MODEL_ID,
                contents=prompt,
                config=config,
            )

            # Process response
            for part in response.candidates[0].content.parts:
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

        except Exception as e:
            result.error = str(e)
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
