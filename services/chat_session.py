"""
Chat Session Manager for multi-turn image generation.
"""
import os
import time
import asyncio
from typing import Optional, List
from dataclasses import dataclass, field
from PIL import Image
from io import BytesIO

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ChatMessage:
    """A single message in the chat."""
    role: str  # "user" or "assistant"
    content: str
    image: Optional[Image.Image] = None
    thinking: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChatResponse:
    """Response from a chat message."""
    text: Optional[str] = None
    image: Optional[Image.Image] = None
    thinking: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None


class ChatSession:
    """
    Manages a multi-turn chat session for iterative image generation.
    Supports refining images through conversation.
    """

    MODEL_ID = "gemini-2.0-flash-preview-image-generation"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the chat session.

        Args:
            api_key: Google API key. If not provided, will try to get from environment.
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY not found")
        self.client = genai.Client(api_key=self._api_key)
        self.chat = None
        self.messages: List[ChatMessage] = []
        self.aspect_ratio = "16:9"

    def update_api_key(self, api_key: str):
        """Update the API key and reinitialize the client."""
        self._api_key = api_key
        self.client = genai.Client(api_key=api_key)
        # Clear existing chat session as the client changed
        self.clear_session()

    def start_session(self, aspect_ratio: str = "16:9"):
        """Start a new chat session."""
        self.chat = self.client.chats.create(model=self.MODEL_ID)
        self.messages = []
        self.aspect_ratio = aspect_ratio

    def clear_session(self):
        """Clear the current chat session."""
        self.chat = None
        self.messages = []

    async def send_message(
        self,
        message: str,
        aspect_ratio: Optional[str] = None
    ) -> ChatResponse:
        """
        Send a message and get a response with optional image.

        Args:
            message: User's message/prompt
            aspect_ratio: Override aspect ratio for this message

        Returns:
            ChatResponse with text and/or image
        """
        if self.chat is None:
            self.start_session()

        start_time = time.time()
        response = ChatResponse()

        # Record user message
        self.messages.append(ChatMessage(role="user", content=message))

        try:
            # Build config
            config = {
                "response_modalities": ["TEXT", "IMAGE"],
                "image_config": {
                    "aspect_ratio": aspect_ratio or self.aspect_ratio
                }
            }

            # Use sync chat.send_message wrapped in executor
            # because google-genai chat doesn't have async send_message yet
            loop = asyncio.get_event_loop()
            api_response = await loop.run_in_executor(
                None,
                lambda: self.chat.send_message(message, config=config)
            )

            # Process response
            for part in api_response.parts:
                if hasattr(part, 'thought') and part.thought:
                    response.thinking = part.text
                elif hasattr(part, 'text') and part.text:
                    response.text = part.text
                elif hasattr(part, 'inline_data') and part.inline_data:
                    image_data = part.inline_data.data
                    response.image = Image.open(BytesIO(image_data))
                # Handle as_image() method if available
                if hasattr(part, 'as_image'):
                    try:
                        img = part.as_image()
                        if img:
                            response.image = img
                    except:
                        pass

            response.duration = time.time() - start_time

            # Record assistant message
            self.messages.append(ChatMessage(
                role="assistant",
                content=response.text or "",
                image=response.image,
                thinking=response.thinking
            ))

        except Exception as e:
            response.error = str(e)
            response.duration = time.time() - start_time

        return response

    def get_history(self) -> List[ChatMessage]:
        """Get the chat history."""
        return self.messages.copy()

    def is_active(self) -> bool:
        """Check if there's an active chat session."""
        return self.chat is not None
