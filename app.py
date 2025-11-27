"""
Nano Banana Lab - Streamlit Web UI
AI Image Generation Playground powered by Google Gemini.
"""
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page config must be first Streamlit command
st.set_page_config(
    page_title="Nano Banana Lab",
    page_icon="🍌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide Streamlit's default image toolbar (fullscreen button on hover)
st.markdown(
    """
    <style>
    button[title="View fullscreen"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Import components and services
from i18n import Translator, LANGUAGES
from components import (
    render_sidebar,
    render_basic_generation,
    render_chat_generation,
    render_history,
    render_style_transfer,
    render_search_generation,
    render_templates,
    render_batch_generation,
)
from components.sidebar import get_current_api_key
from services import ImageGenerator, ChatSession, init_from_persistence, init_auth, get_auth_service


def init_services(api_key: str = None):
    """Initialize or reinitialize services with optional API key."""
    key = api_key or get_current_api_key()

    if not key:
        st.session_state.generator = None
        st.session_state.chat_session = None
        return False

    try:
        st.session_state.generator = ImageGenerator(api_key=key)
        st.session_state.chat_session = ChatSession(api_key=key)
        st.session_state.api_error = None
        return True
    except ValueError as e:
        st.session_state.generator = None
        st.session_state.chat_session = None
        st.session_state.api_error = str(e)
        return False


def init_session_state():
    """Initialize session state variables."""
    # Initialize authentication
    init_auth()

    # Load persisted values first (API key, language, settings)
    init_from_persistence()

    if "language" not in st.session_state:
        st.session_state.language = "en"

    if "history" not in st.session_state:
        st.session_state.history = []

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Delay service initialization - only mark as needing init
    # Actual init happens lazily when needed
    if "generator" not in st.session_state:
        st.session_state.generator = None
        st.session_state.chat_session = None
        st.session_state._services_need_init = True


def handle_api_key_change():
    """Handle API key changes from the sidebar."""
    if st.session_state.get("api_key_changed"):
        st.session_state.api_key_changed = False
        api_key = get_current_api_key()
        if api_key:
            init_services(api_key)
        else:
            st.session_state.generator = None
            st.session_state.chat_session = None


def main():
    """Main application entry point."""
    # Initialize session state
    init_session_state()

    # Handle API key changes from sidebar
    handle_api_key_change()

    # Create translator for current language
    t = Translator(st.session_state.language)

    # Render sidebar and get settings
    settings = render_sidebar(t)

    # Header
    st.title(f"🍌 {t('app.title')}")
    st.caption(t("app.subtitle"))

    # Check authentication if required
    auth_service = get_auth_service()
    if auth_service.is_auth_required and not settings.get("is_authenticated"):
        st.warning(t("sidebar.auth.login_required"))
        st.info(t("sidebar.auth.login_help"))
        return

    # Check if API key is valid
    if not settings.get("api_key_valid"):
        st.warning(t("errors.api_key_required"))
        st.info(t("errors.api_key_help"))
        return

    # Render main content based on mode
    mode = settings["mode"]

    # History mode doesn't need generator/chat_session
    if mode == "history":
        render_history(t)
        return

    # Lazy init services only when actually needed
    if st.session_state.get("_services_need_init"):
        init_services()
        st.session_state._services_need_init = False

    # Get services from session state
    generator = st.session_state.generator
    chat_session = st.session_state.chat_session

    if mode == "basic":
        render_basic_generation(t, settings, generator)
    elif mode == "chat":
        render_chat_generation(t, settings, chat_session)
    elif mode == "batch":
        render_batch_generation(t, settings, generator)
    elif mode == "blend":
        render_style_transfer(t, settings, generator)
    elif mode == "search":
        render_search_generation(t, settings, generator)
    elif mode == "templates":
        render_templates(t, settings, generator)


if __name__ == "__main__":
    main()
