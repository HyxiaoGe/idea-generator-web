"""
Storage provider abstract base class and data types.

This module defines the interface that all storage backends must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from PIL import Image


@dataclass
class StorageConfig:
    """Storage backend configuration."""

    # Backend type: local, minio, oss, cos, r2
    backend: str = "local"

    # Common settings
    bucket_name: str = "nano-banana-images"
    public_url: str | None = None  # CDN/public URL prefix

    # Authentication
    access_key: str | None = None
    secret_key: str | None = None

    # Endpoint settings
    endpoint: str | None = None
    region: str | None = None
    use_ssl: bool = False  # Whether to use HTTPS

    # Local storage settings
    local_path: str = "outputs/web"


@dataclass
class StorageObject:
    """Storage object metadata."""

    key: str  # Storage path/key
    filename: str  # File name
    size: int = 0  # Size in bytes
    content_type: str = "image/png"
    created_at: str = ""  # ISO timestamp
    public_url: str | None = None  # Public access URL
    metadata: dict[str, Any] = field(default_factory=dict)


class StorageProvider(ABC):
    """
    Abstract base class for storage backends.

    All storage providers must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name: local, minio, oss, cos, r2."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is configured and available."""
        pass

    @abstractmethod
    async def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "image/png",
        metadata: dict[str, Any] | None = None,
    ) -> StorageObject:
        """
        Save data to storage.

        Args:
            key: Storage key/path
            data: Raw bytes to store
            content_type: MIME type
            metadata: Optional metadata dict

        Returns:
            StorageObject with storage info
        """
        pass

    @abstractmethod
    async def load(self, key: str) -> bytes | None:
        """
        Load data from storage.

        Args:
            key: Storage key/path

        Returns:
            Raw bytes or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete data from storage.

        Args:
            key: Storage key/path

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in storage.

        Args:
            key: Storage key/path

        Returns:
            True if exists
        """
        pass

    @abstractmethod
    def get_public_url(self, key: str) -> str | None:
        """
        Get public access URL for a key.

        Args:
            key: Storage key/path

        Returns:
            Public URL or None if not available
        """
        pass

    # Convenience methods with default implementations

    async def save_image(
        self,
        key: str,
        image: Image.Image,
        format: str = "PNG",
        metadata: dict[str, Any] | None = None,
    ) -> StorageObject:
        """
        Save a PIL Image to storage.

        Args:
            key: Storage key/path
            image: PIL Image object
            format: Image format (PNG, JPEG, WEBP)
            metadata: Optional metadata dict

        Returns:
            StorageObject with storage info
        """
        buffer = BytesIO()
        save_kwargs = {}
        if format.upper() in ("JPEG", "JPG") or format.upper() == "WEBP":
            save_kwargs["quality"] = 95

        image.save(buffer, format=format.upper(), **save_kwargs)
        data = buffer.getvalue()

        content_type = f"image/{format.lower()}"
        if format.upper() in ("JPEG", "JPG"):
            content_type = "image/jpeg"

        return await self.save(key, data, content_type, metadata)

    async def load_image(self, key: str) -> Image.Image | None:
        """
        Load an image from storage as PIL Image.

        Args:
            key: Storage key/path

        Returns:
            PIL Image or None if not found
        """
        data = await self.load(key)
        if data:
            return Image.open(BytesIO(data))
        return None

    async def list_keys(self, prefix: str = "", limit: int = 100) -> list[str]:
        """
        List keys with a given prefix.

        Default implementation returns empty list.
        Subclasses can override for actual listing.

        Args:
            prefix: Key prefix to filter by
            limit: Maximum number of keys to return

        Returns:
            List of keys
        """
        return []
