"""
Cloudflare R2 storage service for cloud image persistence.
R2 is S3-compatible, so we use boto3 for the client.
"""

import os
import json
import logging
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Dict, Any

from PIL import Image

# Try to import boto3 for R2 support
try:
    import boto3
    from botocore.config import Config
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_config_value(key: str, default: str = "") -> str:
    """
    Get configuration value from environment variables.

    For FastAPI, we use environment variables directly.
    The core.config module handles loading from .env files.
    """
    return os.getenv(key, default)


class R2Storage:
    """Service for storing and retrieving images from Cloudflare R2."""

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize the R2 storage service.

        Args:
            user_id: Optional user ID for data isolation.
                     If provided, all data will be stored under users/{user_id}/ prefix.
        """
        self.user_id = user_id

        self.enabled = get_config_value("R2_ENABLED", "true").lower() == "true"
        self.account_id = get_config_value("R2_ACCOUNT_ID", "")
        self.access_key_id = get_config_value("R2_ACCESS_KEY_ID", "")
        self.secret_access_key = get_config_value("R2_SECRET_ACCESS_KEY", "")
        self.bucket_name = get_config_value("R2_BUCKET_NAME", "nano-banana-images")
        self.public_url = get_config_value("R2_PUBLIC_URL", "")

        self._client = None
        self._metadata_cache = None

        if self.enabled and BOTO3_AVAILABLE:
            self._init_client()

    def _init_client(self):
        """Initialize the S3-compatible client for R2."""
        if not all([self.account_id, self.access_key_id, self.secret_access_key]):
            logger.warning("R2 credentials not fully configured, disabling R2 storage")
            self.enabled = False
            return

        try:
            endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"

            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"}
                )
            )
            logger.info(f"R2 client initialized for bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize R2 client: {e}")
            self.enabled = False
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if R2 storage is available and configured."""
        return self.enabled and self._client is not None

    def _get_user_prefix(self) -> str:
        """Get user-specific prefix for data isolation."""
        if self.user_id:
            return f"users/{self.user_id}"
        return ""  # No prefix for anonymous users (backward compatible)

    def _get_date_prefix(self) -> str:
        """Get date-based folder prefix (YYYY/MM/DD) with user prefix."""
        now = datetime.now()
        user_prefix = self._get_user_prefix()
        date_path = f"{now.year}/{now.month:02d}/{now.day:02d}"
        if user_prefix:
            return f"{user_prefix}/{date_path}"
        return date_path

    def _get_history_key(self) -> str:
        """Get the history.json key for the current user."""
        user_prefix = self._get_user_prefix()
        if user_prefix:
            return f"{user_prefix}/history.json"
        return "history.json"

    def _generate_filename(self, mode: str, prompt: str) -> str:
        """
        Generate a descriptive filename based on mode and prompt.

        Format: {mode}_{timestamp}_{prompt_slug}.png
        """
        timestamp = datetime.now().strftime("%H%M%S")

        # Create a slug from prompt (ASCII alphanumeric only for URL safety)
        prompt_slug = "".join(c if c.isascii() and c.isalnum() else "_" for c in prompt[:30])
        prompt_slug = prompt_slug.strip("_")[:20]  # Trim and limit length

        if not prompt_slug:
            prompt_slug = "image"

        return f"{mode}_{timestamp}_{prompt_slug}.png"

    def save_image(
        self,
        image: Image.Image,
        prompt: str,
        settings: Dict[str, Any],
        duration: float = 0.0,
        mode: str = "basic",
        text_response: Optional[str] = None,
        thinking: Optional[str] = None,
        session_id: Optional[str] = None,
        chat_index: Optional[int] = None,
    ) -> Optional[str]:
        """
        Save an image to R2 storage.

        Args:
            image: PIL Image to save
            prompt: The prompt used to generate the image
            settings: Generation settings
            duration: Generation duration in seconds
            mode: Generation mode (basic, chat, batch, etc.)
            text_response: Optional text response from model
            thinking: Optional thinking process
            session_id: Optional chat session ID for grouping
            chat_index: Optional index within chat session

        Returns:
            The R2 key (path) of the saved image, or None if failed
        """
        if not self.is_available:
            return None

        try:
            # Generate path with date organization
            date_prefix = self._get_date_prefix()
            filename = self._generate_filename(mode, prompt)
            key = f"{date_prefix}/{filename}"

            # Convert image to bytes
            img_buffer = BytesIO()
            image.save(img_buffer, format="PNG")
            img_buffer.seek(0)

            # Prepare metadata (S3 metadata only supports ASCII, so we encode non-ASCII)
            import urllib.parse
            metadata = {
                "prompt": urllib.parse.quote(prompt[:256], safe=""),  # URL-encode for non-ASCII
                "mode": mode,
                "duration": str(round(duration, 2)),
                "aspect_ratio": settings.get("aspect_ratio", "16:9"),
                "resolution": settings.get("resolution", "1K"),
                "created_at": datetime.now().isoformat(),
            }

            if session_id:
                metadata["session_id"] = session_id
            if chat_index is not None:
                metadata["chat_index"] = str(chat_index)

            # Upload to R2 with safe cache policy
            # Browser: no cache (max-age=0) - allows immediate purge
            # CDN: 1 day cache (s-maxage=86400) - saves R2 egress cost
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=img_buffer.getvalue(),
                ContentType="image/png",
                CacheControl="public, max-age=0, s-maxage=86400",
                Metadata=metadata
            )

            # Also save/update the history index
            self._update_history_index(
                key, prompt, settings, duration, mode,
                text_response, thinking, session_id, chat_index
            )

            logger.debug(f"Image saved to R2: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to save image to R2: {e}")
            return None

    def _update_history_index(
        self,
        key: str,
        prompt: str,
        settings: dict,
        duration: float,
        mode: str,
        text_response: Optional[str],
        thinking: Optional[str],
        session_id: Optional[str] = None,
        chat_index: Optional[int] = None,
    ):
        """Update the history index file in R2."""
        try:
            # Load existing history
            history = self._load_history_index()

            # Add new record
            record = {
                "key": key,
                "filename": key.split("/")[-1],
                "prompt": prompt[:500],
                "settings": {
                    "aspect_ratio": settings.get("aspect_ratio", "16:9"),
                    "resolution": settings.get("resolution", "1K"),
                },
                "duration": round(duration, 2),
                "mode": mode,
                "created_at": datetime.now().isoformat(),
            }

            if text_response:
                record["text_response"] = text_response[:500]
            if thinking:
                record["thinking"] = thinking[:500]
            if session_id:
                record["session_id"] = session_id
            if chat_index is not None:
                record["chat_index"] = chat_index

            history.insert(0, record)

            # Keep only last 100 records
            history = history[:100]

            # Save updated history
            history_key = self._get_history_key()
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=history_key,
                Body=json.dumps(history, ensure_ascii=False, indent=2),
                ContentType="application/json"
            )

            self._metadata_cache = history

        except Exception as e:
            logger.error(f"Failed to update history index: {e}")

    def _load_history_index(self) -> List[Dict[str, Any]]:
        """Load the history index from R2."""
        if self._metadata_cache is not None:
            return self._metadata_cache

        try:
            history_key = self._get_history_key()
            response = self._client.get_object(
                Bucket=self.bucket_name,
                Key=history_key
            )
            content = response["Body"].read().decode("utf-8")
            self._metadata_cache = json.loads(content)
            return self._metadata_cache
        except self._client.exceptions.NoSuchKey:
            return []
        except Exception as e:
            logger.error(f"Failed to load history index: {e}")
            return []

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get image history from R2.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of image metadata records
        """
        if not self.is_available:
            return []

        history = self._load_history_index()
        return history[:limit]

    def load_image(self, key: str) -> Optional[Image.Image]:
        """
        Load an image from R2.

        Args:
            key: The R2 key (path) of the image

        Returns:
            PIL Image or None if not found
        """
        if not self.is_available:
            return None

        try:
            response = self._client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            image_data = response["Body"].read()
            return Image.open(BytesIO(image_data))
        except Exception as e:
            logger.error(f"Failed to load image from R2: {e}")
            return None

    def load_image_bytes(self, key: str) -> Optional[bytes]:
        """
        Load image bytes from R2.

        Args:
            key: The R2 key (path) of the image

        Returns:
            Image bytes or None if not found
        """
        if not self.is_available:
            return None

        try:
            response = self._client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return response["Body"].read()
        except Exception as e:
            logger.error(f"Failed to load image bytes from R2: {e}")
            return None

    def get_public_url(self, key: str) -> Optional[str]:
        """
        Get the public URL for an image.

        Args:
            key: The R2 key (path) of the image

        Returns:
            Public URL if configured, None otherwise
        """
        if self.public_url:
            return f"{self.public_url.rstrip('/')}/{key}"
        return None

    def delete_image(self, key: str) -> bool:
        """Delete an image from R2."""
        if not self.is_available:
            return False

        try:
            self._client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete image from R2: {e}")
            return False

    def delete_from_history(self, key: str) -> bool:
        """Delete an image record from history index."""
        if not self.is_available:
            return False

        try:
            history = self._load_history_index()
            history = [r for r in history if r.get("key") != key]

            history_key = self._get_history_key()
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=history_key,
                Body=json.dumps(history, ensure_ascii=False, indent=2),
                ContentType="application/json"
            )
            self._metadata_cache = history
            return True
        except Exception as e:
            logger.error(f"Failed to delete from history: {e}")
            return False

    def clear_history(self):
        """Clear all images and history from R2 for the current user."""
        if not self.is_available:
            return

        try:
            # Only delete objects under the current user's prefix
            user_prefix = self._get_user_prefix()

            # List and delete all objects under user prefix
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=user_prefix):
                if "Contents" in page:
                    objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                    if objects:
                        self._client.delete_objects(
                            Bucket=self.bucket_name,
                            Delete={"Objects": objects}
                        )

            self._metadata_cache = None
            logger.info(f"Cleared R2 history for prefix: {user_prefix}")
        except Exception as e:
            logger.error(f"Failed to clear R2 history: {e}")

    def invalidate_cache(self):
        """Invalidate the metadata cache."""
        self._metadata_cache = None


# Cache for user-specific R2 storage instances
_r2_storage_instances: Dict[Optional[str], R2Storage] = {}


def get_r2_storage(user_id: Optional[str] = None) -> R2Storage:
    """
    Get or create an R2 storage instance for the given user.

    Args:
        user_id: Optional user ID for data isolation.
                 If None, returns shared storage instance.

    Returns:
        R2Storage instance for the user (or shared if no user_id)
    """
    global _r2_storage_instances

    # Use the user_id as key (None for shared storage)
    if user_id not in _r2_storage_instances:
        _r2_storage_instances[user_id] = R2Storage(user_id=user_id)

    return _r2_storage_instances[user_id]


def clear_r2_storage_cache():
    """Clear all cached R2 storage instances."""
    global _r2_storage_instances
    _r2_storage_instances = {}
