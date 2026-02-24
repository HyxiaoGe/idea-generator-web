"""
Chat Session Manager for multi-turn image generation.

Uses stateless generate_content(contents=[history...]) to maintain
multi-turn context. History is stored externally (Redis) and passed in
on each call — no server-side chat state is held.
"""

import logging
import os
import time
from dataclasses import dataclass
from io import BytesIO

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

from .generator import build_safety_settings

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass
class ChatResponse:
    """Response from a chat message."""

    text: str | None = None
    image: Image.Image | None = None
    thinking: str | None = None
    thought_signature: bytes | None = None
    duration: float = 0.0
    error: str | None = None
    safety_blocked: bool = False


class ChatSession:
    """
    Stateless multi-turn chat for iterative image generation.

    Each call to send_message() receives the full conversation history
    (from Redis) and passes it to generate_content() so the model sees
    all prior turns.
    """

    MODEL_ID = "gemini-3-pro-image-preview"
    MAX_HISTORY_TURNS = 20  # max turns (1 turn = user + model = 2 messages)
    IMAGE_HISTORY_TURNS = 5  # only include images from last N turns

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY not found")
        self.client = genai.Client(api_key=self._api_key)
        self.aspect_ratio = "16:9"

    def update_api_key(self, api_key: str):
        """Update the API key and reinitialize the client."""
        self._api_key = api_key
        self.client = genai.Client(api_key=api_key)

    def _build_contents(
        self,
        history: list[dict],
        new_message: str,
        history_images: dict[str, Image.Image] | None = None,
        history_signatures: dict[str, bytes] | None = None,
    ) -> list[types.Content]:
        """Build the contents list for generate_content from Redis history + new message.

        Args:
            history: Previous messages from Redis
            new_message: New user message
            history_images: Pre-loaded PIL images keyed by image_key
            history_signatures: thought_signature bytes keyed by image_key
        """
        # Truncate old history beyond MAX_HISTORY_TURNS
        max_messages = self.MAX_HISTORY_TURNS * 2
        if len(history) > max_messages:
            history = history[-max_messages:]

        # Only include images from the last IMAGE_HISTORY_TURNS turns
        image_cutoff = len(history) - (self.IMAGE_HISTORY_TURNS * 2)

        contents: list[types.Content] = []
        for i, msg in enumerate(history):
            role = "user" if msg["role"] == "user" else "model"
            parts: list[types.Part] = []

            if msg.get("content"):
                parts.append(types.Part(text=msg["content"]))

            # Attach image only for recent turns
            image_key = msg.get("image_key")
            if i >= image_cutoff and image_key and history_images and image_key in history_images:
                sig = history_signatures.get(image_key) if history_signatures else None
                # Gemini requires thought_signature on model-generated images;
                # images from older sessions may lack it — skip to avoid 400 INVALID_ARGUMENT
                if role == "model" and not sig:
                    logger.warning(
                        "Skipping history image %s: missing thought_signature", image_key
                    )
                else:
                    img = history_images[image_key]
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    part_kwargs: dict = {
                        "inline_data": types.Blob(mime_type="image/png", data=buf.getvalue()),
                    }
                    if sig:
                        part_kwargs["thought_signature"] = sig
                    parts.append(types.Part(**part_kwargs))

            if parts:
                contents.append(types.Content(role=role, parts=parts))

        # Append the new user message
        contents.append(types.Content(role="user", parts=[types.Part(text=new_message)]))
        return contents

    def send_message(
        self,
        message: str,
        history: list[dict] | None = None,
        history_images: dict[str, Image.Image] | None = None,
        history_signatures: dict[str, bytes] | None = None,
        aspect_ratio: str | None = None,
        safety_level: str = "moderate",
        enable_thinking: bool = False,
    ) -> ChatResponse:
        """
        Send a message with full conversation context and get a response.

        Args:
            message: New user message/prompt
            history: Previous messages from Redis (list of dicts with role/content/image_key)
            history_images: Pre-loaded PIL images keyed by image_key
            history_signatures: thought_signature bytes keyed by image_key
            aspect_ratio: Override aspect ratio for this request
            safety_level: Content safety level
        """
        start_time = time.time()
        response = ChatResponse()

        try:
            contents = self._build_contents(
                history or [], message, history_images, history_signatures
            )

            # Log contents summary for debugging
            content_summary = []
            for c in contents:
                parts_desc = []
                for p in c.parts:
                    if hasattr(p, "inline_data") and p.inline_data:
                        parts_desc.append(f"image({p.inline_data.mime_type})")
                    elif hasattr(p, "text") and p.text:
                        parts_desc.append(f"text({len(p.text)} chars)")
                content_summary.append(f"{c.role}: [{', '.join(parts_desc)}]")
            logger.info(f"Chat contents: {content_summary}")

            config_kwargs = {
                "response_modalities": ["TEXT", "IMAGE"],
                "image_config": types.ImageConfig(aspect_ratio=aspect_ratio or self.aspect_ratio),
                "safety_settings": build_safety_settings(safety_level),
            }
            if enable_thinking:
                config_kwargs["thinking_config"] = types.ThinkingConfig(include_thoughts=True)

            config = types.GenerateContentConfig(**config_kwargs)

            api_response = self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=contents,
                config=config,
            )

            # Check for safety blocks
            if hasattr(api_response, "candidates") and api_response.candidates:
                candidate = api_response.candidates[0]
                if hasattr(candidate, "finish_reason") and str(candidate.finish_reason) == "SAFETY":
                    response.safety_blocked = True
                    response.error = "Content blocked by safety filter"
                    response.duration = time.time() - start_time
                    return response

            # Process response parts
            for part in api_response.parts:
                if hasattr(part, "thought") and part.thought:
                    response.thinking = part.text
                elif hasattr(part, "text") and part.text:
                    response.text = part.text
                elif hasattr(part, "inline_data") and part.inline_data:
                    response.image = Image.open(BytesIO(part.inline_data.data))
                    if part.thought_signature:
                        response.thought_signature = part.thought_signature

            response.duration = time.time() - start_time

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Chat API error: {type(e).__name__}: {error_msg}")
            if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                response.safety_blocked = True
                response.error = "Content blocked by safety filter"
            else:
                response.error = error_msg
            response.duration = time.time() - start_time

        return response
