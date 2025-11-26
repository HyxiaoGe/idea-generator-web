"""
Browser-side persistence service for storing user preferences.
Uses cookies for cross-session persistence.
"""
import os
import json
import base64
import hashlib
import streamlit as st
from typing import Any, Optional
from datetime import datetime

# Try to import extra_streamlit_components for cookie support
try:
    import extra_streamlit_components as stx
    COOKIES_AVAILABLE = True
except ImportError:
    COOKIES_AVAILABLE = False


class PersistenceService:
    """Service for persisting user preferences across browser sessions."""

    # Keys for stored data
    KEY_API_KEY = "nbl_api_key"
    KEY_LANGUAGE = "nbl_language"
    KEY_SETTINGS = "nbl_settings"

    def __init__(self):
        """Initialize the persistence service."""
        self._cookie_manager = None
        if COOKIES_AVAILABLE:
            self._cookie_manager = stx.CookieManager(key="nbl_cookie_manager")

    @property
    def is_available(self) -> bool:
        """Check if persistence is available."""
        return COOKIES_AVAILABLE and self._cookie_manager is not None

    def _obfuscate(self, value: str) -> str:
        """Simple obfuscation for API key (not encryption, just obscurity)."""
        if not value:
            return ""
        # Base64 encode with a simple transformation
        encoded = base64.b64encode(value.encode()).decode()
        return encoded[::-1]  # Reverse the string

    def _deobfuscate(self, value: str) -> str:
        """Reverse the obfuscation."""
        if not value:
            return ""
        try:
            reversed_val = value[::-1]
            return base64.b64decode(reversed_val.encode()).decode()
        except Exception:
            return ""

    def save_api_key(self, api_key: str) -> bool:
        """
        Save API key to browser storage.

        Args:
            api_key: The API key to save

        Returns:
            True if saved successfully
        """
        if not self.is_available:
            return False

        try:
            obfuscated = self._obfuscate(api_key)
            self._cookie_manager.set(
                self.KEY_API_KEY,
                obfuscated,
                key=f"set_{self.KEY_API_KEY}",
                expires_at=datetime(2030, 1, 1)  # Long expiry
            )
            return True
        except Exception as e:
            st.warning(f"Failed to save API key: {e}")
            return False

    def load_api_key(self) -> Optional[str]:
        """
        Load API key from browser storage.

        Returns:
            The stored API key or None
        """
        if not self.is_available:
            return None

        try:
            obfuscated = self._cookie_manager.get(self.KEY_API_KEY)
            if obfuscated:
                return self._deobfuscate(obfuscated)
        except Exception:
            pass
        return None

    def clear_api_key(self) -> bool:
        """Clear stored API key."""
        if not self.is_available:
            return False

        try:
            self._cookie_manager.delete(self.KEY_API_KEY, key=f"del_{self.KEY_API_KEY}")
            return True
        except Exception:
            return False

    def save_language(self, language: str) -> bool:
        """Save language preference."""
        if not self.is_available:
            return False

        try:
            self._cookie_manager.set(
                self.KEY_LANGUAGE,
                language,
                key=f"set_{self.KEY_LANGUAGE}",
                expires_at=datetime(2030, 1, 1)
            )
            return True
        except Exception:
            return False

    def load_language(self) -> Optional[str]:
        """Load language preference."""
        if not self.is_available:
            return os.getenv("DEFAULT_LANGUAGE", "en")

        try:
            lang = self._cookie_manager.get(self.KEY_LANGUAGE)
            return lang if lang else os.getenv("DEFAULT_LANGUAGE", "en")
        except Exception:
            return os.getenv("DEFAULT_LANGUAGE", "en")

    def save_settings(self, settings: dict) -> bool:
        """
        Save user settings to browser storage.

        Args:
            settings: Dictionary of settings to save

        Returns:
            True if saved successfully
        """
        if not self.is_available:
            return False

        try:
            settings_json = json.dumps(settings)
            self._cookie_manager.set(
                self.KEY_SETTINGS,
                settings_json,
                key=f"set_{self.KEY_SETTINGS}",
                expires_at=datetime(2030, 1, 1)
            )
            return True
        except Exception:
            return False

    def load_settings(self) -> dict:
        """
        Load user settings from browser storage.

        Returns:
            Dictionary of settings or default values
        """
        defaults = {
            "aspect_ratio": os.getenv("DEFAULT_ASPECT_RATIO", "16:9"),
            "resolution": os.getenv("DEFAULT_RESOLUTION", "1K"),
            "safety_level": os.getenv("DEFAULT_SAFETY_LEVEL", "moderate"),
            "enable_thinking": False,
            "enable_search": False,
        }

        if not self.is_available:
            return defaults

        try:
            settings_json = self._cookie_manager.get(self.KEY_SETTINGS)
            if settings_json:
                saved = json.loads(settings_json)
                # Merge with defaults to ensure all keys exist
                defaults.update(saved)
        except Exception:
            pass

        return defaults


# Global instance
_persistence_instance: Optional[PersistenceService] = None


def get_persistence() -> PersistenceService:
    """Get or create the global persistence service instance."""
    global _persistence_instance
    if _persistence_instance is None:
        _persistence_instance = PersistenceService()
    return _persistence_instance


def init_from_persistence():
    """
    Initialize session state from persisted values.
    Call this early in app.py before other initialization.
    """
    persistence = get_persistence()

    # Load language if not already set
    if "language" not in st.session_state:
        saved_lang = persistence.load_language()
        if saved_lang:
            st.session_state.language = saved_lang

    # Load API key if not already set
    if "user_api_key" not in st.session_state or not st.session_state.user_api_key:
        saved_key = persistence.load_api_key()
        if saved_key:
            st.session_state.user_api_key = saved_key
            st.session_state.api_key_valid = True
            st.session_state.api_key_source = "saved"

    # Load settings
    if "saved_settings_loaded" not in st.session_state:
        saved_settings = persistence.load_settings()
        st.session_state.saved_settings = saved_settings
        st.session_state.saved_settings_loaded = True
