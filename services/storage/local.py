"""
Local file system storage provider.

This provider stores files on the local file system.
Suitable for development and single-server deployments.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import aiofiles.os

from .base import StorageConfig, StorageObject, StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    """Local file system storage provider."""

    def __init__(self, config: StorageConfig, user_id: str | None = None):
        """
        Initialize local storage provider.

        Args:
            config: Storage configuration
            user_id: Optional user ID for data isolation
        """
        self.config = config
        self.user_id = user_id
        self.base_path = Path(config.local_path)
        self._public_url = config.public_url

        # Ensure base directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        """Backend name."""
        return "local"

    @property
    def is_available(self) -> bool:
        """Check if backend is available."""
        return True

    def _get_full_path(self, key: str) -> Path:
        """Get full file path for a key."""
        return self.base_path / key

    async def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "image/png",
        metadata: dict[str, Any] | None = None,
    ) -> StorageObject:
        """
        Save data to local file system.

        Args:
            key: Storage key/path
            data: Raw bytes to store
            content_type: MIME type
            metadata: Optional metadata dict

        Returns:
            StorageObject with storage info
        """
        file_path = self._get_full_path(key)

        # Ensure parent directory exists
        await aiofiles.os.makedirs(file_path.parent, exist_ok=True)

        # Write file
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)

        logger.debug(f"Saved file to local storage: {key}")

        return StorageObject(
            key=key,
            filename=file_path.name,
            size=len(data),
            content_type=content_type,
            created_at=datetime.now().isoformat(),
            public_url=self.get_public_url(key),
            metadata=metadata or {},
        )

    async def load(self, key: str) -> bytes | None:
        """
        Load data from local file system.

        Args:
            key: Storage key/path

        Returns:
            Raw bytes or None if not found
        """
        file_path = self._get_full_path(key)

        if not file_path.exists():
            return None

        try:
            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Failed to load file {key}: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """
        Delete file from local storage.

        Args:
            key: Storage key/path

        Returns:
            True if deleted successfully
        """
        file_path = self._get_full_path(key)

        if not file_path.exists():
            return False

        try:
            await aiofiles.os.remove(file_path)
            logger.debug(f"Deleted file from local storage: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if file exists.

        Args:
            key: Storage key/path

        Returns:
            True if exists
        """
        file_path = self._get_full_path(key)
        return file_path.exists()

    def get_public_url(self, key: str) -> str | None:
        """
        Get public URL for a key.

        Args:
            key: Storage key/path

        Returns:
            Public URL if configured, otherwise API proxy path
        """
        if self._public_url:
            return f"{self._public_url.rstrip('/')}/{key}"
        # Return API proxy path for serving images
        return f"/api/images/{key}"

    async def list_keys(self, prefix: str = "", limit: int = 100) -> list[str]:
        """
        List keys with a given prefix.

        Args:
            prefix: Key prefix to filter by
            limit: Maximum number of keys to return

        Returns:
            List of keys
        """
        keys = []
        search_path = self._get_full_path(prefix) if prefix else self.base_path

        if not search_path.exists():
            return keys

        # If prefix is a directory, list its contents
        if search_path.is_dir():
            for path in search_path.rglob("*"):
                if path.is_file():
                    # Get relative path from base
                    rel_path = path.relative_to(self.base_path)
                    keys.append(str(rel_path))
                    if len(keys) >= limit:
                        break
        else:
            # If prefix matches files directly
            parent = search_path.parent
            pattern = search_path.name + "*"
            for path in parent.glob(pattern):
                if path.is_file():
                    rel_path = path.relative_to(self.base_path)
                    keys.append(str(rel_path))
                    if len(keys) >= limit:
                        break

        return keys
