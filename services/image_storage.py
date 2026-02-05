"""
Image storage service for persisting generated images.
Supports both local storage and Cloudflare R2 cloud storage.
Supports user-isolated storage when authentication is enabled.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .r2_storage import get_r2_storage

logger = logging.getLogger(__name__)


class ImageStorage:
    """Service for storing and retrieving generated images."""

    def __init__(self, output_dir: str = "outputs/web", user_id: str | None = None):
        """
        Initialize the image storage service.

        Args:
            output_dir: Base directory for local storage
            user_id: Optional user ID for data isolation (e.g., "abc123def456")
        """
        self.user_id = user_id

        # If user_id is provided, create user-specific directory
        # Otherwise use the base output_dir directly (backward compatible)
        if user_id:
            self.base_output_dir = Path(output_dir) / "users" / user_id
        else:
            self.base_output_dir = Path(output_dir)

        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.base_output_dir / "history.json"
        self._load_metadata()

        # Initialize R2 storage with user_id for isolation
        self._r2 = get_r2_storage(user_id=user_id)

    @property
    def output_dir(self) -> Path:
        """Get the current output directory (with date subfolder)."""
        return self._get_date_folder()

    @property
    def r2_enabled(self) -> bool:
        """Check if R2 cloud storage is enabled."""
        return self._r2.is_available

    def _get_date_folder(self) -> Path:
        """Get or create date-based subfolder (YYYY/MM/DD)."""
        now = datetime.now()
        date_path = self.base_output_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        date_path.mkdir(parents=True, exist_ok=True)
        return date_path

    def _generate_filename(self, mode: str, prompt: str) -> str:
        """
        Generate a descriptive filename based on mode and prompt.

        Format: {mode}_{timestamp}_{prompt_slug}.png
        Example: basic_143052_a_beautiful_sunset.png
        """
        timestamp = datetime.now().strftime("%H%M%S")

        # Create a slug from prompt (alphanumeric and underscores only)
        prompt_clean = prompt.lower().strip()
        prompt_slug = "".join(c if c.isalnum() or c == " " else "" for c in prompt_clean)
        prompt_slug = "_".join(prompt_slug.split())[:30]  # Replace spaces, limit length

        if not prompt_slug:
            prompt_slug = "image"

        return f"{mode}_{timestamp}_{prompt_slug}.png"

    def _load_metadata(self):
        """Load metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except (OSError, json.JSONDecodeError):
                self.metadata = {"images": []}
        else:
            self.metadata = {"images": []}

    def _save_metadata(self):
        """Save metadata to disk."""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def save_image(
        self,
        image: Image.Image,
        prompt: str,
        settings: dict[str, Any],
        duration: float = 0.0,
        mode: str = "basic",
        text_response: str | None = None,
        thinking: str | None = None,
        session_id: str | None = None,
        chat_index: int | None = None,
    ) -> tuple[str, str | None]:
        """
        Save an image to storage (local and optionally R2).

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
            Tuple of (filename, r2_url or None)
        """
        # Generate descriptive filename
        filename = self._generate_filename(mode, prompt)

        # Get date-based folder
        date_folder = self._get_date_folder()
        filepath = date_folder / filename

        # Save image locally
        image.save(filepath, format="PNG")

        # Calculate relative path from base dir for metadata
        relative_path = filepath.relative_to(self.base_output_dir)

        # Record metadata
        record = {
            "filename": str(relative_path),  # Store relative path
            "prompt": prompt[:500],  # Truncate long prompts
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

        # Save to R2 if enabled
        r2_url = None
        if self._r2.is_available:
            r2_key = self._r2.save_image(
                image=image,
                prompt=prompt,
                settings=settings,
                duration=duration,
                mode=mode,
                text_response=text_response,
                thinking=thinking,
                session_id=session_id,
                chat_index=chat_index,
            )
            if r2_key:
                record["r2_key"] = r2_key
                r2_url = self._r2.get_public_url(r2_key)
                record["r2_url"] = r2_url
                logger.debug(f"Image saved to R2: {r2_key}")

        self.metadata["images"].insert(0, record)

        # Keep only last 100 records in metadata
        if len(self.metadata["images"]) > 100:
            self.metadata["images"] = self.metadata["images"][:100]

        self._save_metadata()

        # Return filename and r2_url for immediate use
        return filename, r2_url

    def get_history(
        self,
        limit: int = 50,
        mode: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get image history with metadata.
        Tries R2 first if available, falls back to local.

        Args:
            limit: Maximum number of records to return
            mode: Optional mode filter
            search: Optional search string for prompt

        Returns:
            List of image metadata records
        """
        # Try R2 first if available
        if self._r2.is_available:
            r2_history = self._r2.get_history(limit=limit * 2)  # Get more for filtering
            if r2_history:
                # Apply filters
                filtered = r2_history
                if mode:
                    filtered = [r for r in filtered if r.get("mode") == mode]
                if search:
                    search_lower = search.lower()
                    filtered = [r for r in filtered if search_lower in r.get("prompt", "").lower()]
                return filtered[:limit]

        # Fall back to local storage
        history = []
        for record in self.metadata["images"]:
            # Apply filters
            if mode and record.get("mode") != mode:
                continue
            if search and search.lower() not in record.get("prompt", "").lower():
                continue

            filepath = self.base_output_dir / record["filename"]
            if filepath.exists():
                record_copy = record.copy()
                record_copy["filepath"] = str(filepath)
                history.append(record_copy)

            if len(history) >= limit:
                break

        return history

    def get_history_item(self, item_id: str) -> dict[str, Any] | None:
        """
        Get a single history item by ID (filename or r2_key).

        Args:
            item_id: The filename or R2 key

        Returns:
            History record or None
        """
        # Search in R2 history
        if self._r2.is_available:
            for record in self._r2.get_history(limit=100):
                if record.get("key") == item_id or record.get("filename") == item_id:
                    return record

        # Search in local history
        for record in self.metadata["images"]:
            if record.get("filename") == item_id or record.get("r2_key") == item_id:
                return record

        return None

    def load_image(self, filename: str) -> Image.Image | None:
        """
        Load an image from storage.
        Tries local first, then R2 if available.

        Args:
            filename: Name/path of the image file or R2 key

        Returns:
            PIL Image or None if not found
        """
        # Try local storage first
        filepath = self.base_output_dir / filename
        if filepath.exists():
            return Image.open(filepath)

        # Try R2 if available
        if self._r2.is_available:
            return self._r2.load_image(filename)

        return None

    def load_image_bytes(self, filename: str) -> bytes | None:
        """
        Load image as bytes from storage.

        Args:
            filename: Name/path of the image file or R2 key

        Returns:
            Image bytes or None if not found
        """
        # Try local storage first
        filepath = self.base_output_dir / filename
        if filepath.exists():
            return filepath.read_bytes()

        # Try R2 if available
        if self._r2.is_available:
            return self._r2.load_image_bytes(filename)

        return None

    def delete_image(self, item_id: str) -> bool:
        """
        Delete an image from storage.

        Args:
            item_id: The filename or R2 key

        Returns:
            True if deleted successfully
        """
        deleted = False

        # Delete from local storage
        for i, record in enumerate(self.metadata["images"]):
            if record.get("filename") == item_id or record.get("r2_key") == item_id:
                # Delete file
                filepath = self.base_output_dir / record["filename"]
                if filepath.exists():
                    filepath.unlink()

                # Delete from R2
                if self._r2.is_available and record.get("r2_key"):
                    self._r2.delete_image(record["r2_key"])
                    self._r2.delete_from_history(record["r2_key"])

                # Remove from metadata
                self.metadata["images"].pop(i)
                self._save_metadata()
                deleted = True
                break

        return deleted

    def clear_history(self):
        """Clear all stored images and metadata (local and R2)."""
        # Clear local files
        for record in self.metadata["images"]:
            filepath = self.base_output_dir / record["filename"]
            if filepath.exists():
                filepath.unlink()

        # Clear metadata
        self.metadata = {"images": []}
        self._save_metadata()

        # Clear R2 if available
        if self._r2.is_available:
            self._r2.clear_history()

    def get_image_path(self, filename: str) -> Path | None:
        """Get the full path to a local image file."""
        filepath = self.base_output_dir / filename
        if filepath.exists():
            return filepath
        return None

    def get_download_filename(self, record: dict[str, Any]) -> str:
        """
        Generate a user-friendly download filename.

        Args:
            record: Image metadata record

        Returns:
            Formatted filename for download
        """
        # Use the stored filename if it's already descriptive
        stored_filename = record.get("filename", "")
        if "/" in stored_filename:
            # Extract just the filename part from path
            return stored_filename.split("/")[-1]
        return stored_filename if stored_filename else "generated_image.png"


# Cache for user-specific storage instances
_storage_instances: dict[str | None, ImageStorage] = {}


def get_storage(user_id: str | None = None) -> ImageStorage:
    """
    Get or create a storage instance for the given user.

    Args:
        user_id: Optional user ID for data isolation.
                 If None, returns shared storage instance.

    Returns:
        ImageStorage instance for the user (or shared if no user_id)
    """
    global _storage_instances

    # Use the user_id as key (None for shared storage)
    if user_id not in _storage_instances:
        _storage_instances[user_id] = ImageStorage(user_id=user_id)

    return _storage_instances[user_id]


def clear_storage_cache():
    """Clear all cached storage instances."""
    global _storage_instances
    _storage_instances = {}
