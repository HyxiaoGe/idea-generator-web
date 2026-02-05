"""
MinIO S3-compatible storage provider.

This provider stores files in MinIO or any S3-compatible storage.
Suitable for self-hosted object storage deployments.
"""

import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

from .base import StorageConfig, StorageObject, StorageProvider

logger = logging.getLogger(__name__)

# Try to import minio
try:
    from minio import Minio
    from minio.error import S3Error

    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    Minio = None
    S3Error = Exception


class MinIOStorageProvider(StorageProvider):
    """MinIO S3-compatible storage provider."""

    def __init__(self, config: StorageConfig, user_id: str | None = None):
        """
        Initialize MinIO storage provider.

        Args:
            config: Storage configuration
            user_id: Optional user ID for data isolation
        """
        self.config = config
        self.user_id = user_id
        self.bucket = config.bucket_name
        self._public_url = config.public_url
        self._client = None
        self._available = False

        if not MINIO_AVAILABLE:
            logger.warning("minio package not installed. Install with: pip install minio")
            return

        if not all([config.endpoint, config.access_key, config.secret_key]):
            logger.warning("MinIO credentials not fully configured")
            return

        self._init_client()

    def _init_client(self):
        """Initialize the MinIO client."""
        try:
            endpoint = self.config.endpoint
            # Strip protocol prefix if present
            if endpoint.startswith("http://"):
                endpoint = endpoint[7:]
            elif endpoint.startswith("https://"):
                endpoint = endpoint[8:]

            self._client = Minio(
                endpoint=endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=self.config.use_ssl,
            )

            # Ensure bucket exists
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")

            self._available = True
            logger.info(f"MinIO client initialized for bucket: {self.bucket}")

        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            self._available = False
            self._client = None

    @property
    def name(self) -> str:
        """Backend name."""
        return "minio"

    @property
    def is_available(self) -> bool:
        """Check if backend is available."""
        return self._available and self._client is not None

    async def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "image/png",
        metadata: dict[str, Any] | None = None,
    ) -> StorageObject:
        """
        Save data to MinIO.

        Args:
            key: Storage key/path
            data: Raw bytes to store
            content_type: MIME type
            metadata: Optional metadata dict

        Returns:
            StorageObject with storage info
        """
        import urllib.parse

        if not self.is_available:
            raise RuntimeError("MinIO storage is not available")

        try:
            # Prepare metadata (MinIO only supports ASCII, so URL-encode non-ASCII)
            minio_metadata = {}
            if metadata:
                for k, v in metadata.items():
                    if v is not None:
                        # URL-encode to handle non-ASCII characters
                        value = str(v)[:256]
                        minio_metadata[k] = urllib.parse.quote(value, safe="")

            self._client.put_object(
                self.bucket,
                key,
                BytesIO(data),
                len(data),
                content_type=content_type,
                metadata=minio_metadata if minio_metadata else None,
            )

            logger.debug(f"Saved file to MinIO: {key}")

            return StorageObject(
                key=key,
                filename=key.split("/")[-1],
                size=len(data),
                content_type=content_type,
                created_at=datetime.now().isoformat(),
                public_url=self.get_public_url(key),
                metadata=metadata or {},
            )

        except S3Error as e:
            logger.error(f"Failed to save to MinIO: {e}")
            raise

    async def load(self, key: str) -> bytes | None:
        """
        Load data from MinIO.

        Args:
            key: Storage key/path

        Returns:
            Raw bytes or None if not found
        """
        if not self.is_available:
            return None

        try:
            response = self._client.get_object(self.bucket, key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            logger.error(f"Failed to load from MinIO: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """
        Delete file from MinIO.

        Args:
            key: Storage key/path

        Returns:
            True if deleted successfully
        """
        if not self.is_available:
            return False

        try:
            self._client.remove_object(self.bucket, key)
            logger.debug(f"Deleted file from MinIO: {key}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete from MinIO: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in MinIO.

        Args:
            key: Storage key/path

        Returns:
            True if exists
        """
        if not self.is_available:
            return False

        try:
            self._client.stat_object(self.bucket, key)
            return True
        except S3Error:
            return False

    def get_public_url(self, key: str) -> str | None:
        """
        Get public URL for a key.

        Args:
            key: Storage key/path

        Returns:
            Public URL if configured, otherwise presigned URL
        """
        if self._public_url:
            return f"{self._public_url.rstrip('/')}/{key}"

        if not self.is_available:
            return None

        # Generate presigned URL (7 days expiry)
        try:
            return self._client.presigned_get_object(self.bucket, key, expires=timedelta(days=7))
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL: {e}")
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
            objects = self._client.list_objects(self.bucket, prefix=prefix, recursive=True)
            for obj in objects:
                keys.append(obj.object_name)
                if len(keys) >= limit:
                    break
        except S3Error as e:
            logger.error(f"Failed to list objects: {e}")

        return keys
