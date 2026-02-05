"""
Alibaba Cloud OSS storage provider.

This provider stores files in Alibaba Cloud Object Storage Service.
Suitable for China-based deployments with good domestic performance.
"""

import logging
from datetime import datetime
from typing import Any

from .base import StorageConfig, StorageObject, StorageProvider

logger = logging.getLogger(__name__)

# Try to import oss2
try:
    import oss2
    from oss2.exceptions import NoSuchKey

    OSS_AVAILABLE = True
except ImportError:
    OSS_AVAILABLE = False
    oss2 = None
    NoSuchKey = Exception


class AliyunOSSProvider(StorageProvider):
    """Alibaba Cloud OSS storage provider."""

    def __init__(self, config: StorageConfig, user_id: str | None = None):
        """
        Initialize Alibaba OSS provider.

        Args:
            config: Storage configuration
            user_id: Optional user ID for data isolation
        """
        self.config = config
        self.user_id = user_id
        self.bucket_name = config.bucket_name
        self._public_url = config.public_url
        self._endpoint = config.endpoint
        self._bucket = None
        self._available = False

        if not OSS_AVAILABLE:
            logger.warning("oss2 package not installed. Install with: pip install oss2")
            return

        if not all([config.endpoint, config.access_key, config.secret_key]):
            logger.warning("Alibaba OSS credentials not fully configured")
            return

        self._init_client()

    def _init_client(self):
        """Initialize the OSS client."""
        try:
            auth = oss2.Auth(self.config.access_key, self.config.secret_key)

            # Ensure endpoint has proper format
            endpoint = self._endpoint
            if not endpoint.startswith("http"):
                endpoint = f"https://{endpoint}"

            self._bucket = oss2.Bucket(auth, endpoint, self.bucket_name)
            self._available = True
            logger.info(f"Alibaba OSS client initialized for bucket: {self.bucket_name}")

        except Exception as e:
            logger.error(f"Failed to initialize OSS client: {e}")
            self._available = False
            self._bucket = None

    @property
    def name(self) -> str:
        """Backend name."""
        return "oss"

    @property
    def is_available(self) -> bool:
        """Check if backend is available."""
        return self._available and self._bucket is not None

    async def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "image/png",
        metadata: dict[str, Any] | None = None,
    ) -> StorageObject:
        """
        Save data to OSS.

        Args:
            key: Storage key/path
            data: Raw bytes to store
            content_type: MIME type
            metadata: Optional metadata dict

        Returns:
            StorageObject with storage info
        """
        if not self.is_available:
            raise RuntimeError("Alibaba OSS is not available")

        try:
            headers = {
                "Content-Type": content_type,
                "Cache-Control": "public, max-age=31536000",
                "x-oss-storage-class": "Standard",
            }

            # Add custom metadata headers
            if metadata:
                for k, v in metadata.items():
                    if v is not None:
                        # OSS custom headers must start with x-oss-meta-
                        headers[f"x-oss-meta-{k}"] = str(v)[:256]

            self._bucket.put_object(key, data, headers=headers)

            logger.debug(f"Saved file to OSS: {key}")

            return StorageObject(
                key=key,
                filename=key.split("/")[-1],
                size=len(data),
                content_type=content_type,
                created_at=datetime.now().isoformat(),
                public_url=self.get_public_url(key),
                metadata=metadata or {},
            )

        except Exception as e:
            logger.error(f"Failed to save to OSS: {e}")
            raise

    async def load(self, key: str) -> bytes | None:
        """
        Load data from OSS.

        Args:
            key: Storage key/path

        Returns:
            Raw bytes or None if not found
        """
        if not self.is_available:
            return None

        try:
            result = self._bucket.get_object(key)
            return result.read()
        except NoSuchKey:
            return None
        except Exception as e:
            logger.error(f"Failed to load from OSS: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """
        Delete file from OSS.

        Args:
            key: Storage key/path

        Returns:
            True if deleted successfully
        """
        if not self.is_available:
            return False

        try:
            self._bucket.delete_object(key)
            logger.debug(f"Deleted file from OSS: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from OSS: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in OSS.

        Args:
            key: Storage key/path

        Returns:
            True if exists
        """
        if not self.is_available:
            return False

        try:
            return self._bucket.object_exists(key)
        except Exception:
            return False

    def get_public_url(self, key: str) -> str | None:
        """
        Get public URL for a key.

        Args:
            key: Storage key/path

        Returns:
            Public URL if configured, otherwise default bucket domain
        """
        if self._public_url:
            return f"{self._public_url.rstrip('/')}/{key}"

        # Default bucket domain
        if self._endpoint:
            # Extract region from endpoint (e.g., oss-cn-hangzhou.aliyuncs.com)
            endpoint = self._endpoint.replace("https://", "").replace("http://", "")
            return f"https://{self.bucket_name}.{endpoint}/{key}"

        return None

    async def list_keys(self, prefix: str = "", limit: int = 100) -> list[str]:
        """
        List keys with a given prefix.

        Args:
            prefix: Key prefix to filter by
            limit: Maximum number of keys to return

        Returns:
            List of keys
        """
        if not self.is_available:
            return []

        keys = []
        try:
            # Use iterator for listing
            for obj in oss2.ObjectIterator(self._bucket, prefix=prefix):
                keys.append(obj.key)
                if len(keys) >= limit:
                    break
        except Exception as e:
            logger.error(f"Failed to list objects: {e}")

        return keys
