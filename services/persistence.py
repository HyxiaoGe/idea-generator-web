"""
Browser-side persistence service for storing user preferences.
Uses cookies for cross-session persistence.
Optimized for single-read initialization.
"""
import os
import json
import base64
import streamlit as st
from typing import Optional
from datetime import datetime

# Try to import extra_streamlit_components for cookie support
try:
    import extra_streamlit_components as stx

    COOKIES_AVAILABLE = True
except ImportError:
    COOKIES_AVAILABLE = False


def _get_cookie_manager():
    """Get CookieManager instance, cached in session_state."""
    if not COOKIES_AVAILABLE:
        return None

    # Cache in session_state to avoid recreating on every rerun
    if "_cookie_manager" not in st.session_state:
        st.session_state._cookie_manager = stx.CookieManager(key="nbl_cookie_manager")
    return st.session_state._cookie_manager


class PersistenceService:
    """Service for persisting user preferences across browser sessions."""

    # Single key for all data (reduces cookie reads)
    KEY_ALL_DATA = "nbl_data"

    # Legacy keys (for migration)
    KEY_API_KEY = "nbl_api_key"
    KEY_LANGUAGE = "nbl_language"
    KEY_SETTINGS = "nbl_settings"
    KEY_MODE = "nbl_mode"

    def __init__(self):
        """Initialize the persistence service."""
        self._cookie_manager = _get_cookie_manager()
        self._cache: Optional[dict] = None  # In-memory cache for current session

    @property
    def is_available(self) -> bool:
        """Check if persistence is available."""
        return COOKIES_AVAILABLE and self._cookie_manager is not None

    def _obfuscate(self, value: str) -> str:
        """Simple obfuscation for API key (not encryption, just obscurity)."""
        if not value:
            return ""
        encoded = base64.b64encode(value.encode()).decode()
        return encoded[::-1]

    def _deobfuscate(self, value: str) -> str:
        """Reverse the obfuscation."""
        if not value:
            return ""
        try:
            reversed_val = value[::-1]
            return base64.b64decode(reversed_val.encode()).decode()
        except Exception:
            return ""

    def _get_defaults(self) -> dict:
        """Get default values for all settings."""
        return {
            "api_key": None,
            "language": os.getenv("DEFAULT_LANGUAGE", "en"),
            "mode": "basic",
            "settings": {
                "aspect_ratio": os.getenv("DEFAULT_ASPECT_RATIO", "16:9"),
                "resolution": os.getenv("DEFAULT_RESOLUTION", "1K"),
                "safety_level": os.getenv("DEFAULT_SAFETY_LEVEL", "moderate"),
                "enable_thinking": False,
                "enable_search": False,
            },
            "auth_token": None,
            "auth_user": None,
        }

    def load_all(self) -> dict:
        """
        Load all persisted data in a single read.
        Returns merged data with defaults.
        """
        # Return from cache if available
        if self._cache is not None:
            return self._cache

        defaults = self._get_defaults()

        if not self.is_available:
            self._cache = defaults
            return defaults

        try:
            # Try new unified format first
            data_json = self._cookie_manager.get(self.KEY_ALL_DATA)
            if data_json:
                data = json.loads(data_json)
                # Deobfuscate API key
                if data.get("api_key"):
                    data["api_key"] = self._deobfuscate(data["api_key"])
                # Merge with defaults
                result = defaults.copy()
                result.update(data)
                if "settings" in data:
                    result["settings"] = {**defaults["settings"], **data["settings"]}
                self._cache = result
                return result

            # Fall back to legacy format (migration)
            result = self._migrate_legacy_data(defaults)
            self._cache = result
            return result

        except Exception:
            self._cache = defaults
            return defaults

    def _migrate_legacy_data(self, defaults: dict) -> dict:
        """Migrate from legacy separate cookies to unified format."""
        result = defaults.copy()

        try:
            # Load legacy API key
            obfuscated = self._cookie_manager.get(self.KEY_API_KEY)
            if obfuscated:
                result["api_key"] = self._deobfuscate(obfuscated)

            # Load legacy language
            lang = self._cookie_manager.get(self.KEY_LANGUAGE)
            if lang:
                result["language"] = lang

            # Load legacy mode
            mode = self._cookie_manager.get(self.KEY_MODE)
            if mode:
                result["mode"] = mode

            # Load legacy settings
            settings_json = self._cookie_manager.get(self.KEY_SETTINGS)
            if settings_json:
                saved_settings = json.loads(settings_json)
                result["settings"] = {**defaults["settings"], **saved_settings}

            # Save in new unified format for future loads
            if result != defaults:
                self._save_all_internal(result)

        except Exception:
            pass

        return result

    def _save_all_internal(self, data: dict) -> bool:
        """Internal method to save all data."""
        if not self.is_available:
            return False

        try:
            # Obfuscate API key before saving
            save_data = data.copy()
            if save_data.get("api_key"):
                save_data["api_key"] = self._obfuscate(save_data["api_key"])

            data_json = json.dumps(save_data)
            self._cookie_manager.set(
                self.KEY_ALL_DATA,
                data_json,
                key=f"set_{self.KEY_ALL_DATA}",
                expires_at=datetime(2030, 1, 1),
            )
            return True
        except Exception:
            return False

    def save_all(self, data: dict) -> bool:
        """Save all data and update cache."""
        self._cache = data
        return self._save_all_internal(data)

    # Convenience methods for individual fields
    def save_api_key(self, api_key: str) -> bool:
        """Save API key."""
        data = self.load_all()
        data["api_key"] = api_key
        return self.save_all(data)

    def load_api_key(self) -> Optional[str]:
        """Load API key."""
        return self.load_all().get("api_key")

    def clear_api_key(self) -> bool:
        """Clear stored API key."""
        data = self.load_all()
        data["api_key"] = None
        return self.save_all(data)

    def save_language(self, language: str) -> bool:
        """Save language preference."""
        data = self.load_all()
        data["language"] = language
        return self.save_all(data)

    def load_language(self) -> Optional[str]:
        """Load language preference."""
        return self.load_all().get("language")

    def save_settings(self, settings: dict) -> bool:
        """Save user settings."""
        data = self.load_all()
        data["settings"] = settings
        return self.save_all(data)

    def load_settings(self) -> dict:
        """Load user settings."""
        return self.load_all().get("settings", self._get_defaults()["settings"])

    def save_mode(self, mode: str) -> bool:
        """Save current mode/page preference."""
        data = self.load_all()
        data["mode"] = mode
        return self.save_all(data)

    def load_mode(self) -> Optional[str]:
        """Load mode preference."""
        return self.load_all().get("mode")

    def save_auth(self, token: dict, user: dict) -> bool:
        """Save authentication token and user info."""
        data = self.load_all()
        data["auth_token"] = token
        data["auth_user"] = user
        return self.save_all(data)

    def load_auth(self) -> tuple:
        """Load authentication token and user info."""
        data = self.load_all()
        return data.get("auth_token"), data.get("auth_user")

    def clear_auth(self) -> bool:
        """Clear stored authentication data."""
        data = self.load_all()
        data["auth_token"] = None
        data["auth_user"] = None
        return self.save_all(data)


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
    Optimized: single cookie read for all data.
    """
    # Skip if already initialized this session
    if st.session_state.get("_persistence_initialized"):
        return

    persistence = get_persistence()

    # Single read for all data
    data = persistence.load_all()

    # Load language
    if "language" not in st.session_state:
        st.session_state.language = data.get("language", "en")

    # Load API key
    if "user_api_key" not in st.session_state or not st.session_state.user_api_key:
        saved_key = data.get("api_key")
        if saved_key:
            st.session_state.user_api_key = saved_key
            st.session_state.api_key_valid = True
            st.session_state.api_key_source = "saved"

    # Load settings
    if "saved_settings_loaded" not in st.session_state:
        st.session_state.saved_settings = data.get(
            "settings", persistence._get_defaults()["settings"]
        )
        st.session_state.saved_settings_loaded = True

    # Load mode
    if "saved_mode" not in st.session_state:
        saved_mode = data.get("mode")
        if saved_mode:
            st.session_state.saved_mode = saved_mode

    st.session_state._persistence_initialized = True
