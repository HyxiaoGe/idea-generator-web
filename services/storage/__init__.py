"""
Pluggable storage system for Nano Banana Lab.

Supports multiple storage backends:
- Local file system (development)
- MinIO (self-hosted S3-compatible)
- Alibaba Cloud OSS (China production)

Usage:
    from services.storage import get_storage_manager

    # Get storage manager for a user
    storage = get_storage_manager(user_id="user123")

    # Save an image
    result = await storage.save_image(
        image=pil_image,
        prompt="a cute cat",
        settings={"aspect_ratio": "1:1", "resolution": "1K"},
        mode="basic",
    )

    # Get history
    history = await storage.get_history(limit=50)
"""

from .base import StorageConfig, StorageObject, StorageProvider
from .local import LocalStorageProvider
from .manager import StorageManager
from .minio import MinIOStorageProvider
from .oss import AliyunOSSProvider

# Cache for user-specific storage manager instances
_storage_instances: dict[str | None, StorageManager] = {}


def get_storage_config() -> StorageConfig:
    """
    Get storage configuration from application settings.

    Returns:
        StorageConfig instance
    """
    from core.config import get_settings

    settings = get_settings()

    config = StorageConfig(
        backend=settings.storage_backend,
        bucket_name=settings.storage_bucket,
        public_url=settings.storage_public_url,
        local_path=settings.storage_local_path,
    )

    # Configure provider-specific settings
    if settings.storage_backend == "minio":
        config.endpoint = settings.minio_endpoint
        config.access_key = settings.minio_access_key
        config.secret_key = settings.minio_secret_key
        config.use_ssl = settings.minio_use_ssl
        if settings.minio_bucket:
            config.bucket_name = settings.minio_bucket
    elif settings.storage_backend == "oss":
        config.endpoint = settings.oss_endpoint
        config.access_key = settings.oss_access_key
        config.secret_key = settings.oss_secret_key

    return config


def get_storage_manager(user_id: str | None = None) -> StorageManager:
    """
    Get or create a storage manager instance for the given user.

    Args:
        user_id: Optional user ID for data isolation.
                 If None, returns shared storage instance.

    Returns:
        StorageManager instance for the user
    """
    global _storage_instances

    if user_id not in _storage_instances:
        config = get_storage_config()
        _storage_instances[user_id] = StorageManager(config, user_id=user_id)

    return _storage_instances[user_id]


def clear_storage_cache():
    """Clear all cached storage manager instances."""
    global _storage_instances
    _storage_instances = {}


__all__ = [
    # Core classes
    "StorageConfig",
    "StorageObject",
    "StorageProvider",
    "StorageManager",
    # Providers
    "LocalStorageProvider",
    "MinIOStorageProvider",
    "AliyunOSSProvider",
    # Factory functions
    "get_storage_config",
    "get_storage_manager",
    "clear_storage_cache",
]
