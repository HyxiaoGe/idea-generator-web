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
                filename = self._storage.save_image(
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

    def sync_from_disk(self, force: bool = False) -> bool:
        """
        Synchronize history from disk storage.

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

                # Load missing items from disk
                for record in disk_history:
                    # Use 'key' for R2 storage, 'filename' for local storage
                    file_key = record.get("key") or record.get("filename")
                    filename = record.get("filename", file_key)

                    if filename not in session_filenames:
                        # Load the image using the full key/path
                        image = self._storage.load_image(file_key)
                        if image:
                            if "history" not in st.session_state:
                                st.session_state.history = []

                            st.session_state.history.append({
                                "prompt": record.get("prompt", ""),
                                "image": image,
                                "text": record.get("text_response"),
                                "thinking": record.get("thinking"),
                                "duration": record.get("duration", 0),
                                "settings": record.get("settings", {}),
                                "mode": record.get("mode", "basic"),
                                "filename": filename,
                                "created_at": record.get("created_at"),
                            })

                # Sort by created_at (newest first)
                if "history" in st.session_state:
                    st.session_state.history.sort(
                        key=lambda x: x.get("created_at", ""),
                        reverse=True
                    )

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
