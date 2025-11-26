"""
Image storage service for persisting generated images.
Supports both local storage and Cloudflare R2 cloud storage.
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image

from .r2_storage import get_r2_storage


class ImageStorage:
    """Service for storing and retrieving generated images."""

    def __init__(self, output_dir: str = "outputs/web"):
        """
        Initialize the image storage service.

        Args:
            output_dir: Base directory for local storage
        """
        self.base_output_dir = Path(output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.base_output_dir / "history.json"
        self._load_metadata()

        # Initialize R2 storage
        self._r2 = get_r2_storage()

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
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except (json.JSONDecodeError, IOError):
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
        settings: Dict[str, Any],
        duration: float = 0.0,
        mode: str = "basic",
        text_response: Optional[str] = None,
        thinking: Optional[str] = None,
    ) -> str:
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

        Returns:
            The filename of the saved image
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

        # Save to R2 if enabled
        if self._r2.is_available:
            r2_key = self._r2.save_image(
                image=image,
                prompt=prompt,
                settings=settings,
                duration=duration,
                mode=mode,
                text_response=text_response,
                thinking=thinking,
            )
            if r2_key:
                record["r2_key"] = r2_key
                record["r2_url"] = self._r2.get_public_url(r2_key)

        self.metadata["images"].insert(0, record)

        # Keep only last 100 records in metadata
        if len(self.metadata["images"]) > 100:
            self.metadata["images"] = self.metadata["images"][:100]

        self._save_metadata()

        return filename

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get image history with metadata.
        Tries R2 first if available, falls back to local.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of image metadata records
        """
        # Try R2 first if available
        if self._r2.is_available:
            r2_history = self._r2.get_history(limit=limit)
            if r2_history:
                return r2_history

        # Fall back to local storage
        history = []
        for record in self.metadata["images"][:limit]:
            filepath = self.base_output_dir / record["filename"]
            if filepath.exists():
                record_copy = record.copy()
                record_copy["filepath"] = str(filepath)
                history.append(record_copy)
        return history

    def load_image(self, filename: str) -> Optional[Image.Image]:
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

    def get_image_path(self, filename: str) -> Optional[Path]:
        """Get the full path to a local image file."""
        filepath = self.base_output_dir / filename
        if filepath.exists():
            return filepath
        return None

    def get_download_filename(self, record: Dict[str, Any]) -> str:
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


# Global instance for easy access
_storage_instance: Optional[ImageStorage] = None


def get_storage() -> ImageStorage:
    """Get or create the global storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = ImageStorage()
    return _storage_instance
