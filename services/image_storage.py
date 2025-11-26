"""
Image storage service for persisting generated images.
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image


class ImageStorage:
    """Service for storing and retrieving generated images."""

    def __init__(self, output_dir: str = "outputs/web"):
        """
        Initialize the image storage service.

        Args:
            output_dir: Directory to store generated images
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.output_dir / "history.json"
        self._load_metadata()

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
        Save an image to disk and record metadata.

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
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        counter = len(self.metadata["images"]) + 1
        filename = f"{mode}_{timestamp}_{counter:04d}.png"
        filepath = self.output_dir / filename

        # Save image
        image.save(filepath, format="PNG")

        # Record metadata
        record = {
            "filename": filename,
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

        self.metadata["images"].insert(0, record)

        # Keep only last 100 records in metadata
        if len(self.metadata["images"]) > 100:
            self.metadata["images"] = self.metadata["images"][:100]

        self._save_metadata()

        return filename

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get image history with metadata.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of image metadata records
        """
        history = []
        for record in self.metadata["images"][:limit]:
            filepath = self.output_dir / record["filename"]
            if filepath.exists():
                record_copy = record.copy()
                record_copy["filepath"] = str(filepath)
                history.append(record_copy)
        return history

    def load_image(self, filename: str) -> Optional[Image.Image]:
        """
        Load an image from disk.

        Args:
            filename: Name of the image file

        Returns:
            PIL Image or None if not found
        """
        filepath = self.output_dir / filename
        if filepath.exists():
            return Image.open(filepath)
        return None

    def clear_history(self):
        """Clear all stored images and metadata."""
        # Remove all image files
        for record in self.metadata["images"]:
            filepath = self.output_dir / record["filename"]
            if filepath.exists():
                filepath.unlink()

        # Clear metadata
        self.metadata = {"images": []}
        self._save_metadata()

    def get_image_path(self, filename: str) -> Optional[Path]:
        """Get the full path to an image file."""
        filepath = self.output_dir / filename
        if filepath.exists():
            return filepath
        return None


# Global instance for easy access
_storage_instance: Optional[ImageStorage] = None


def get_storage() -> ImageStorage:
    """Get or create the global storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = ImageStorage()
    return _storage_instance
