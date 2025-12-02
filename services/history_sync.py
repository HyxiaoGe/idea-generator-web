"""
History synchronization service.
Handles concurrent writes and cross-tab synchronization.
Supports user-isolated storage when authentication is enabled.
"""
import json
import time
import threading
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image
import streamlit as st

from .image_storage import get_storage


class HistorySyncManager:
    """
    Manages history synchronization across tabs and sessions.
    Uses file-based locking for concurrent write protection.
    """

    LOCK_TIMEOUT = 10.0  # seconds
    SYNC_INTERVAL = 5.0  # seconds between syncs
    PRELOAD_COUNT = 4  # Number of images to preload ahead

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize the sync manager.

        Args:
            user_id: Optional user ID for data isolation.
        """
        self.user_id = user_id
        self._storage = get_storage(user_id=user_id)
        self._lock_file = self._storage.base_output_dir / ".history.lock"
        self._local_lock = threading.Lock()
        self._image_cache: Dict[str, Image.Image] = {}  # In-memory image cache

    def _acquire_file_lock(self, timeout: float = None) -> bool:
        """
        Acquire a file-based lock for concurrent write protection.

        Args:
            timeout: Maximum time to wait for lock

        Returns:
            True if lock acquired, False if timeout
        """
        timeout = timeout or self.LOCK_TIMEOUT
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Try to create lock file exclusively
                if not self._lock_file.exists():
                    self._lock_file.write_text(str(time.time()))
                    return True

                # Check if lock is stale (older than timeout)
                lock_time = float(self._lock_file.read_text())
                if time.time() - lock_time > self.LOCK_TIMEOUT:
                    # Stale lock, take over
                    self._lock_file.write_text(str(time.time()))
                    return True

                time.sleep(0.1)
            except Exception:
                time.sleep(0.1)

        return False

    def _release_file_lock(self):
        """Release the file-based lock."""
        try:
            if self._lock_file.exists():
                self._lock_file.unlink()
        except Exception:
            pass

    def save_to_history(
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
        Save an image to history with proper locking.

        Args:
            image: PIL Image to save
            prompt: The generation prompt
            settings: Generation settings
            duration: Generation duration
            mode: Generation mode
            text_response: Optional text response
            thinking: Optional thinking process

        Returns:
            Filename if saved successfully, None otherwise
        """
        with self._local_lock:
            if not self._acquire_file_lock():
                # Could not acquire lock, try anyway
                pass

            try:
                # Save to storage
                filename, r2_url = self._storage.save_image(
                    image=image,
                    prompt=prompt,
                    settings=settings,
                    duration=duration,
                    mode=mode,
                    text_response=text_response,
                    thinking=thinking,
                )

                # Update session state history
                self._update_session_history(
                    filename=filename,
                    r2_url=r2_url,
                    image=image,
                    prompt=prompt,
                    settings=settings,
                    duration=duration,
                    mode=mode,
                    text_response=text_response,
                    thinking=thinking,
                )

                return filename

            finally:
                self._release_file_lock()

        return None

    def _update_session_history(
        self,
        filename: str,
        r2_url: Optional[str],
        image: Image.Image,
        prompt: str,
        settings: Dict[str, Any],
        duration: float,
        mode: str,
        text_response: Optional[str],
        thinking: Optional[str],
    ):
        """Update the session state history."""
        if "history" not in st.session_state:
            st.session_state.history = []

        record = {
            "prompt": prompt,
            "image": image,
            "r2_url": r2_url,  # CDN URL for fast loading (passed from save_image)
            "text": text_response,
            "thinking": thinking,
            "duration": duration,
            "settings": settings.copy(),
            "mode": mode,
            "filename": filename,
            "created_at": datetime.now().isoformat(),
        }

        st.session_state.history.insert(0, record)

        # Keep only last 50 in memory
        if len(st.session_state.history) > 50:
            st.session_state.history = st.session_state.history[:50]

    def _get_cached_image(self, file_key: str) -> Optional[Image.Image]:
        """
        Get image from cache or load from storage.
        Uses bytes caching to avoid Streamlit media file issues.

        Args:
            file_key: The file key/path to load

        Returns:
            PIL Image or None if not found
        """
        from io import BytesIO

        # Check memory cache first (PIL Image objects)
        if file_key in self._image_cache:
            return self._image_cache[file_key]

        # Check session state bytes cache
        cache_key = f"_img_bytes_{file_key}"
        if cache_key in st.session_state:
            # Convert bytes back to PIL Image
            img_bytes = st.session_state[cache_key]
            image = Image.open(BytesIO(img_bytes))
            # Also store in memory cache for faster subsequent access
            self._image_cache[file_key] = image
            return image

        # Load from storage
        image = self._storage.load_image(file_key)
        if image:
            # Cache as bytes in session state (avoids Streamlit media file issues)
            img_buffer = BytesIO()
            image.save(img_buffer, format="PNG")
            st.session_state[cache_key] = img_buffer.getvalue()
            # Also cache PIL Image in memory for faster access
            self._image_cache[file_key] = image

        return image

    def _load_single_image(self, key: str) -> tuple:
        """
        Load a single image and return (key, image_bytes, image).
        Used for parallel loading.
        """
        from io import BytesIO

        try:
            image = self._storage.load_image(key)
            if image:
                img_buffer = BytesIO()
                image.save(img_buffer, format="PNG")
                return (key, img_buffer.getvalue(), image)
        except Exception as e:
            print(f"Failed to load image {key}: {e}")
        return (key, None, None)

    def preload_images(self, file_keys: List[str]):
        """
        Preload images into cache using parallel loading.

        Args:
            file_keys: List of file keys to preload
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Filter out already cached keys
        keys_to_load = []
        for key in file_keys[: self.PRELOAD_COUNT]:
            if key not in self._image_cache:
                cache_key = f"_img_bytes_{key}"
                if cache_key not in st.session_state:
                    keys_to_load.append(key)

        if not keys_to_load:
            return

        # Parallel load using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(keys_to_load))) as executor:
            futures = {
                executor.submit(self._load_single_image, key): key
                for key in keys_to_load
            }

            for future in as_completed(futures):
                key, img_bytes, image = future.result()
                if img_bytes and image:
                    cache_key = f"_img_bytes_{key}"
                    st.session_state[cache_key] = img_bytes
                    self._image_cache[key] = image

    def sync_from_disk(self, force: bool = False) -> bool:
        """
        Synchronize history from disk storage.
        Uses caching to avoid redundant image loads.

        Args:
            force: Force sync even if recently synced

        Returns:
            True if synced, False if skipped
        """
        # Check if sync is needed
        last_sync_key = "_history_last_sync"
        last_sync = st.session_state.get(last_sync_key, 0)

        if not force and time.time() - last_sync < self.SYNC_INTERVAL:
            return False

        try:
            disk_history = self._storage.get_history(limit=50)

            if disk_history:
                # Build a set of existing filenames in session
                session_filenames = set()
                if "history" in st.session_state:
                    for item in st.session_state.history:
                        if item.get("filename"):
                            session_filenames.add(item["filename"])

                # Collect keys for preloading
                keys_to_preload = []

                # Load missing items from disk
                for record in disk_history:
                    # Use 'key' for R2 storage, 'filename' for local storage
                    file_key = record.get("key") or record.get("filename")
                    filename = record.get("filename", file_key)

                    if filename not in session_filenames:
                        # Build R2 URL if we have the key and public URL is configured
                        r2_url = None
                        if file_key and self._storage.r2_enabled:
                            r2_url = self._storage._r2.get_public_url(file_key)

                        # If we have R2 URL, we can skip loading the image
                        # The browser will load it directly from CDN
                        image = None
                        if not r2_url:
                            # Fall back to loading image if no CDN URL
                            image = self._get_cached_image(file_key)

                        if r2_url or image:
                            if "history" not in st.session_state:
                                st.session_state.history = []

                            st.session_state.history.append({
                                "prompt": record.get("prompt", ""),
                                "image": image,
                                "r2_url": r2_url,  # CDN URL for fast loading
                                "text": record.get("text_response"),
                                "thinking": record.get("thinking"),
                                "duration": record.get("duration", 0),
                                "settings": record.get("settings", {}),
                                "mode": record.get("mode", "basic"),
                                "filename": filename,
                                "created_at": record.get("created_at"),
                            })
                    else:
                        # Collect for potential preloading
                        keys_to_preload.append(file_key)

                # Sort by created_at (newest first)
                if "history" in st.session_state:
                    st.session_state.history.sort(
                        key=lambda x: x.get("created_at", ""),
                        reverse=True
                    )

                # Preload next batch of images
                if keys_to_preload:
                    self.preload_images(keys_to_preload)

            st.session_state[last_sync_key] = time.time()
            return True

        except Exception as e:
            print(f"History sync error: {e}")
            return False

    def get_disk_history_hash(self) -> str:
        """
        Get a hash of the disk history for change detection.

        Returns:
            Hash string of current disk history
        """
        try:
            metadata_file = self._storage.metadata_file
            if metadata_file.exists():
                content = metadata_file.read_text()
                return hashlib.md5(content.encode()).hexdigest()[:8]
        except Exception:
            pass
        return ""


# Cache for user-specific sync managers
_sync_managers: Dict[Optional[str], HistorySyncManager] = {}


def get_history_sync(user_id: Optional[str] = None) -> HistorySyncManager:
    """
    Get or create a history sync manager for the given user.

    Args:
        user_id: Optional user ID for data isolation.
                 If None, returns shared sync manager.

    Returns:
        HistorySyncManager instance for the user (or shared if no user_id)
    """
    global _sync_managers

    # Use the user_id as key (None for shared)
    if user_id not in _sync_managers:
        _sync_managers[user_id] = HistorySyncManager(user_id=user_id)

    return _sync_managers[user_id]


def get_current_user_history_sync() -> HistorySyncManager:
    """
    Get history sync manager for the currently authenticated user.
    Falls back to shared manager if no user is authenticated.
    """
    from .auth import get_user_id
    user_id = get_user_id()
    return get_history_sync(user_id=user_id)
