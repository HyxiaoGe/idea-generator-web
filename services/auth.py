"""
GitHub OAuth authentication service for Nano Banana Lab.
Uses streamlit-oauth for GitHub OAuth2 integration.
"""
import os
import hashlib
from dataclasses import dataclass
from typing import Optional, Dict, Any

import streamlit as st

# Try to import streamlit-oauth
try:
    from streamlit_oauth import OAuth2Component
    OAUTH_AVAILABLE = True
except ImportError:
    OAUTH_AVAILABLE = False
    OAuth2Component = None


def get_config_value(key: str, default: str = "") -> str:
    """
    Get configuration value from multiple sources.
    Priority: st.secrets > os.environ > default
    """
    try:
        if hasattr(st, 'secrets') and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


@dataclass
class GitHubUser:
    """Represents an authenticated GitHub user."""
    id: str
    login: str
    name: Optional[str]
    email: Optional[str]
    avatar_url: Optional[str]

    @property
    def display_name(self) -> str:
        """Get the best display name for the user."""
        return self.name or self.login

    @property
    def user_folder_id(self) -> str:
        """
        Get a safe folder identifier for the user.
        Uses MD5 hash of user ID for privacy and filesystem safety.
        """
        return hashlib.md5(f"github_{self.id}".encode()).hexdigest()[:16]


class AuthService:
    """Service for handling GitHub OAuth authentication."""

    # GitHub OAuth endpoints
    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_API_URL = "https://api.github.com/user"

    def __init__(self):
        """Initialize the authentication service."""
        self.client_id = get_config_value("GITHUB_CLIENT_ID", "")
        self.client_secret = get_config_value("GITHUB_CLIENT_SECRET", "")
        self.redirect_uri = get_config_value("GITHUB_REDIRECT_URI", "")

        # Check if auth is enabled
        self.enabled = get_config_value("AUTH_ENABLED", "false").lower() == "true"

        self._oauth_component = None

        if self.enabled and OAUTH_AVAILABLE and self._is_configured():
            self._init_oauth_component()

    def _is_configured(self) -> bool:
        """Check if OAuth is properly configured."""
        return bool(self.client_id and self.client_secret)

    def _init_oauth_component(self):
        """Initialize the OAuth2 component."""
        try:
            self._oauth_component = OAuth2Component(
                client_id=self.client_id,
                client_secret=self.client_secret,
                authorize_endpoint=self.GITHUB_AUTHORIZE_URL,
                token_endpoint=self.GITHUB_TOKEN_URL,
            )
        except Exception as e:
            print(f"[Auth] Failed to initialize OAuth component: {e}")
            self._oauth_component = None

    @property
    def is_available(self) -> bool:
        """Check if authentication is available and configured."""
        return self.enabled and OAUTH_AVAILABLE and self._oauth_component is not None

    @property
    def is_auth_required(self) -> bool:
        """Check if authentication is required (enabled in config)."""
        return self.enabled

    def init_session_state(self):
        """Initialize authentication-related session state."""
        if "auth_token" not in st.session_state:
            st.session_state.auth_token = None
        if "auth_user" not in st.session_state:
            st.session_state.auth_user = None

    def is_authenticated(self) -> bool:
        """Check if the current user is authenticated."""
        return st.session_state.get("auth_token") is not None

    def get_current_user(self) -> Optional[GitHubUser]:
        """Get the currently authenticated user."""
        user_data = st.session_state.get("auth_user")
        if user_data:
            return GitHubUser(
                id=str(user_data.get("id", "")),
                login=user_data.get("login", ""),
                name=user_data.get("name"),
                email=user_data.get("email"),
                avatar_url=user_data.get("avatar_url"),
            )
        return None

    def get_user_id(self) -> Optional[str]:
        """Get the current user's folder ID for storage isolation."""
        user = self.get_current_user()
        if user:
            return user.user_folder_id
        return None

    def render_login_button(self, button_text: str = "Login with GitHub") -> bool:
        """
        Render the GitHub login button.

        Args:
            button_text: Text to display on the button

        Returns:
            True if login was successful, False otherwise
        """
        if not self.is_available:
            return False

        # Determine redirect URI
        redirect_uri = self.redirect_uri
        if not redirect_uri:
            # Auto-detect based on current URL
            redirect_uri = self._get_default_redirect_uri()

        try:
            result = self._oauth_component.authorize_button(
                name=button_text,
                redirect_uri=redirect_uri,
                scope="read:user user:email",
                key="github_oauth_btn",
                icon="https://github.githubassets.com/favicons/favicon.svg",
            )

            if result and "token" in result:
                token = result["token"]
                st.session_state.auth_token = token

                # Fetch user info
                user_info = self._fetch_user_info(token.get("access_token"))
                if user_info:
                    st.session_state.auth_user = user_info
                    return True

        except Exception as e:
            print(f"[Auth] Login error: {e}")

        return False

    def _get_default_redirect_uri(self) -> str:
        """Get the default redirect URI based on environment."""
        # For local development
        return "http://localhost:8501/component/streamlit_oauth.authorize_button"

    def _fetch_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Fetch user information from GitHub API."""
        try:
            import urllib.request
            import json

            req = urllib.request.Request(
                self.GITHUB_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "NanoBananaLab/1.0",
                }
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode())

        except Exception as e:
            print(f"[Auth] Failed to fetch user info: {e}")
            return None

    def logout(self):
        """Log out the current user."""
        st.session_state.auth_token = None
        st.session_state.auth_user = None

    def render_user_info(self, t=None):
        """
        Render the current user's information.

        Args:
            t: Translator instance for i18n (optional)
        """
        user = self.get_current_user()
        if not user:
            return

        col1, col2 = st.columns([1, 3])

        with col1:
            if user.avatar_url:
                st.image(user.avatar_url, width=40)
            else:
                st.write("👤")

        with col2:
            st.write(f"**{user.display_name}**")
            if user.email:
                st.caption(user.email)

    def render_logout_button(self, button_text: str = "Logout") -> bool:
        """
        Render a logout button.

        Args:
            button_text: Text to display on the button

        Returns:
            True if logout was clicked, False otherwise
        """
        if st.button(button_text, key="github_logout_btn", use_container_width=True):
            self.logout()
            return True
        return False


# Global instance
_auth_service_instance: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create the global auth service instance."""
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance


def init_auth():
    """Initialize authentication in session state."""
    auth = get_auth_service()
    auth.init_session_state()


def is_authenticated() -> bool:
    """Check if current user is authenticated."""
    auth = get_auth_service()
    return auth.is_authenticated()


def get_current_user() -> Optional[GitHubUser]:
    """Get the currently authenticated user."""
    auth = get_auth_service()
    return auth.get_current_user()


def get_user_id() -> Optional[str]:
    """Get current user's storage folder ID."""
    auth = get_auth_service()
    return auth.get_user_id()


def require_auth() -> bool:
    """
    Check if authentication is required.
    Returns True if auth is required but user is not authenticated.
    """
    auth = get_auth_service()
    if auth.is_auth_required and not auth.is_authenticated():
        return True
    return False
