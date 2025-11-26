"""
Cloudflare R2 storage service for cloud image persistence.
R2 is S3-compatible, so we use boto3 for the client.
"""
import os
import json
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image

# Try to import streamlit for secrets
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Try to import boto3 for R2 support
try:
    import boto3
    from botocore.config import Config
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


def get_config_value(key: str, default: str = "") -> str:
    """
    Get configuration value from multiple sources.
    Priority: st.secrets > os.environ > default
    """
    # Try Streamlit secrets first (for Streamlit Cloud)
    if HAS_STREAMLIT:
        try:
            if hasattr(st, 'secrets') and key in st.secrets:
                return str(st.secrets[key])
        except Exception:
            pass

    # Fall back to environment variables
    return os.getenv(key, default)


class R2Storage:
    """Service for storing and retrieving images from Cloudflare R2."""

    def __init__(self):
        """Initialize the R2 storage service."""
        # Hardcode R2_ENABLED=true for debugging
        # Note: Set to True directly to bypass config issues
        self.enabled = True  # Hardcoded for debugging
        self.account_id = get_config_value("R2_ACCOUNT_ID", "")
        self.access_key_id = get_config_value("R2_ACCESS_KEY_ID", "")
        self.secret_access_key = get_config_value("R2_SECRET_ACCESS_KEY", "")
        self.bucket_name = get_config_value("R2_BUCKET_NAME", "nano-banana-images")
        self.public_url = get_config_value("R2_PUBLIC_URL", "")

        # Debug output
        print(f"[R2 Debug] enabled={self.enabled}")
        print(f"[R2 Debug] account_id={'***' if self.account_id else 'EMPTY'}")
        print(f"[R2 Debug] access_key_id={'***' if self.access_key_id else 'EMPTY'}")
        print(f"[R2 Debug] secret_access_key={'***' if self.secret_access_key else 'EMPTY'}")
        print(f"[R2 Debug] bucket_name={self.bucket_name}")
        print(f"[R2 Debug] BOTO3_AVAILABLE={BOTO3_AVAILABLE}")

        self._client = None
        self._metadata_cache = None

        if self.enabled and BOTO3_AVAILABLE:
            self._init_client()
            print(f"[R2 Debug] Client initialized: {self._client is not None}")

    def _init_client(self):
        """Initialize the S3-compatible client for R2."""
        if not all([self.account_id, self.access_key_id, self.secret_access_key]):
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
        except Exception as e:
            print(f"Failed to initialize R2 client: {e}")
            self.enabled = False
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if R2 storage is available and configured."""
        return self.enabled and self._client is not None

    def _get_date_prefix(self) -> str:
        """Get date-based folder prefix (YYYY/MM/DD)."""
        now = datetime.now()
        return f"{now.year}/{now.month:02d}/{now.day:02d}"

    def _generate_filename(self, mode: str, prompt: str) -> str:
        """
        Generate a descriptive filename based on mode and prompt.

        Format: {mode}_{timestamp}_{prompt_slug}.png
        """
        timestamp = datetime.now().strftime("%H%M%S")

        # Create a slug from prompt (first 30 chars, alphanumeric only)
        prompt_slug = "".join(c if c.isalnum() else "_" for c in prompt[:30])
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

            # Prepare metadata
            metadata = {
                "prompt": prompt[:256],  # R2 metadata has size limits
                "mode": mode,
                "duration": str(round(duration, 2)),
                "aspect_ratio": settings.get("aspect_ratio", "16:9"),
                "resolution": settings.get("resolution", "1K"),
                "created_at": datetime.now().isoformat(),
            }

            # Upload to R2
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=img_buffer.getvalue(),
                ContentType="image/png",
                Metadata=metadata
            )

            # Also save/update the history index
            self._update_history_index(key, prompt, settings, duration, mode, text_response, thinking)

            return key

        except Exception as e:
            print(f"Failed to save image to R2: {e}")
            return None

    def _update_history_index(
        self,
        key: str,
        prompt: str,
        settings: dict,
        duration: float,
        mode: str,
        text_response: Optional[str],
        thinking: Optional[str]
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

            history.insert(0, record)

            # Keep only last 100 records
            history = history[:100]

            # Save updated history
            self._client.put_object(
                Bucket=self.bucket_name,
                Key="history.json",
                Body=json.dumps(history, ensure_ascii=False, indent=2),
                ContentType="application/json"
            )

            self._metadata_cache = history

        except Exception as e:
            print(f"Failed to update history index: {e}")

    def _load_history_index(self) -> List[Dict[str, Any]]:
        """Load the history index from R2."""
        if self._metadata_cache is not None:
            return self._metadata_cache

        try:
            response = self._client.get_object(
                Bucket=self.bucket_name,
                Key="history.json"
            )
            content = response["Body"].read().decode("utf-8")
            self._metadata_cache = json.loads(content)
            return self._metadata_cache
        except self._client.exceptions.NoSuchKey:
            return []
        except Exception as e:
            print(f"Failed to load history index: {e}")
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
            print(f"Failed to load image from R2: {e}")
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
            print(f"Failed to delete image from R2: {e}")
            return False

    def clear_history(self):
        """Clear all images and history from R2."""
        if not self.is_available:
            return

        try:
            # List and delete all objects
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name):
                if "Contents" in page:
                    objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                    if objects:
                        self._client.delete_objects(
                            Bucket=self.bucket_name,
                            Delete={"Objects": objects}
                        )

            self._metadata_cache = None
        except Exception as e:
            print(f"Failed to clear R2 history: {e}")


# Global instance
_r2_storage_instance: Optional[R2Storage] = None


def get_r2_storage() -> R2Storage:
    """Get or create the global R2 storage instance."""
    global _r2_storage_instance
    if _r2_storage_instance is None:
        _r2_storage_instance = R2Storage()
    return _r2_storage_instance
