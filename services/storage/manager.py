"""
Unified storage manager.

This module provides a high-level interface for storing and managing images,
abstracting away the underlying storage backend.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any

from PIL import Image

from .base import StorageConfig, StorageObject, StorageProvider

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Unified storage manager.

    Routes operations to the configured storage backend and manages
    history indexing and user isolation.
    """

    def __init__(self, config: StorageConfig, user_id: str | None = None):
        """
        Initialize storage manager.

        Args:
            config: Storage configuration
            user_id: Optional user ID for data isolation
        """
        self.config = config
        self.user_id = user_id
        self._provider = self._create_provider()
        self._history_cache: list[dict] | None = None

    def _create_provider(self) -> StorageProvider:
        """Create storage provider based on configuration."""
        backend = self.config.backend.lower()

        if backend == "local":
            from .local import LocalStorageProvider

            return LocalStorageProvider(self.config, self.user_id)
        elif backend == "minio":
            from .minio import MinIOStorageProvider

            return MinIOStorageProvider(self.config, self.user_id)
        elif backend == "oss":
            from .oss import AliyunOSSProvider

            return AliyunOSSProvider(self.config, self.user_id)
        else:
            raise ValueError(f"Unknown storage backend: {backend}")

    @property
    def provider(self) -> StorageProvider:
        """Get the underlying storage provider."""
        return self._provider

    @property
    def is_available(self) -> bool:
        """Check if storage is available."""
        return self._provider.is_available

    def _get_prefix(self) -> str:
        """Get user-specific prefix for data isolation."""
        if self.user_id:
            return f"users/{self.user_id}/"
        return ""

    def _generate_key(self, prompt: str, mode: str = "basic") -> str:
        """
        Generate storage key for an image.

        Format: {prefix}YYYY/MM/DD/{mode}_{HHMMSS}_{slug}.png

        Args:
            prompt: Image generation prompt
            mode: Generation mode (basic, chat, batch, etc.)

        Returns:
            Storage key
        """
        now = datetime.now()
        date_path = now.strftime("%Y/%m/%d")
        timestamp = now.strftime("%H%M%S")

        # Create slug from prompt (alphanumeric only, limited length)
        slug = re.sub(r"[^a-zA-Z0-9\s]", "", prompt[:30])
        slug = re.sub(r"\s+", "_", slug.strip())[:20].lower()
        if not slug:
            slug = "image"

        return f"{self._get_prefix()}{date_path}/{mode}_{timestamp}_{slug}.png"

    def _get_history_key(self) -> str:
        """Get the history.json key for the current user."""
        return f"{self._get_prefix()}history.json"

    async def save_image(
        self,
        image: Image.Image,
        prompt: str,
        settings: dict[str, Any],
        mode: str = "basic",
        duration: float = 0.0,
        text_response: str | None = None,
        thinking: str | None = None,
        session_id: str | None = None,
        chat_index: int | None = None,
        **extra,
    ) -> StorageObject:
        """
        Save a generated image.

        Args:
            image: PIL Image to save
            prompt: Generation prompt
            settings: Generation settings
            mode: Generation mode
            duration: Generation duration in seconds
            text_response: Optional text response from model
            thinking: Optional thinking process
            session_id: Optional chat session ID
            chat_index: Optional index within chat session
            **extra: Additional metadata

        Returns:
            StorageObject with storage info
        """
        key = self._generate_key(prompt, mode)

        metadata = {
            "prompt": prompt[:500],
            "mode": mode,
            "duration": round(duration, 2),
            **settings,
            **extra,
        }

        if text_response:
            metadata["text_response"] = text_response[:500]
        if thinking:
            metadata["thinking"] = thinking[:500]
        if session_id:
            metadata["session_id"] = session_id
        if chat_index is not None:
            metadata["chat_index"] = chat_index

        result = await self._provider.save_image(key, image, metadata=metadata)

        # Update history index
        await self._update_history(result, metadata)

        return result

    async def load_image(self, key: str) -> Image.Image | None:
        """
        Load an image from storage.

        Args:
            key: Storage key

        Returns:
            PIL Image or None if not found
        """
        return await self._provider.load_image(key)

    async def load_image_bytes(self, key: str) -> bytes | None:
        """
        Load image bytes from storage.

        Args:
            key: Storage key

        Returns:
            Raw bytes or None if not found
        """
        return await self._provider.load(key)

    def get_public_url(self, key: str) -> str | None:
        """
        Get public URL for an image.

        Args:
            key: Storage key

        Returns:
            Public URL or None
        """
        return self._provider.get_public_url(key)

    async def delete_image(self, key: str) -> bool:
        """
        Delete an image from storage.

        Args:
            key: Storage key

        Returns:
            True if deleted successfully
        """
        deleted = await self._provider.delete(key)

        if deleted:
            # Remove from history
            await self._remove_from_history(key)

        return deleted

    async def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get image history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of history records
        """
        if self._history_cache is not None:
            return self._history_cache[:limit]

        # Load from storage
        history_key = self._get_history_key()
        data = await self._provider.load(history_key)

        if data:
            try:
                self._history_cache = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error("Failed to parse history.json")
                self._history_cache = []
        else:
            self._history_cache = []

        return self._history_cache[:limit]

    async def get_history_item(self, item_id: str) -> dict[str, Any] | None:
        """
        Get a single history item by ID.

        Args:
            item_id: The key or filename

        Returns:
            History record or None
        """
        history = await self.get_history(limit=100)

        for record in history:
            if record.get("key") == item_id or record.get("filename") == item_id:
                return record

        return None

    async def _update_history(self, obj: StorageObject, metadata: dict[str, Any]):
        """
        Update the history index.

        Args:
            obj: Storage object that was saved
            metadata: Associated metadata
        """
        try:
            history = await self.get_history(limit=100)

            record = {
                "key": obj.key,
                "filename": obj.filename,
                "url": obj.public_url,
                "created_at": datetime.now().isoformat(),
                "prompt": metadata.get("prompt", ""),
                "mode": metadata.get("mode", "basic"),
                "settings": {
                    "aspect_ratio": metadata.get("aspect_ratio"),
                    "resolution": metadata.get("resolution"),
                    "provider": metadata.get("provider"),
                    "model": metadata.get("model"),
                },
                "duration": metadata.get("duration", 0),
            }

            # Include optional fields
            if metadata.get("text_response"):
                record["text_response"] = metadata["text_response"]
            if metadata.get("thinking"):
                record["thinking"] = metadata["thinking"]
            if metadata.get("session_id"):
                record["session_id"] = metadata["session_id"]
            if metadata.get("chat_index") is not None:
                record["chat_index"] = metadata["chat_index"]

            history.insert(0, record)
            history = history[:100]  # Keep last 100 records

            self._history_cache = history

            # Save updated history
            history_key = self._get_history_key()
            await self._provider.save(
                history_key,
                json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
            )

        except Exception as e:
            logger.error(f"Failed to update history: {e}")

    async def _remove_from_history(self, key: str):
        """
        Remove an item from history.

        Args:
            key: Storage key to remove
        """
        try:
            history = await self.get_history(limit=100)
            history = [r for r in history if r.get("key") != key]

            self._history_cache = history

            # Save updated history
            history_key = self._get_history_key()
            await self._provider.save(
                history_key,
                json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
            )

        except Exception as e:
            logger.error(f"Failed to remove from history: {e}")

    async def clear_history(self):
        """Clear all images and history for the current user."""
        # Get current history
        history = await self.get_history(limit=1000)

        # Delete all images
        for record in history:
            key = record.get("key")
            if key:
                await self._provider.delete(key)

        # Delete history file
        history_key = self._get_history_key()
        await self._provider.delete(history_key)

        self._history_cache = []

    def invalidate_cache(self):
        """Invalidate the history cache."""
        self._history_cache = None
