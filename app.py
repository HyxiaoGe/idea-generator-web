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

# Import components and services
from i18n import Translator, LANGUAGES
from components import (
    render_sidebar,
    render_basic_generation,
    render_chat_generation,
    render_history,
)
from services import ImageGenerator, ChatSession


def init_session_state():
    """Initialize session state variables."""
    if "language" not in st.session_state:
        st.session_state.language = "en"

    if "history" not in st.session_state:
        st.session_state.history = []

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    if "generator" not in st.session_state:
        try:
            st.session_state.generator = ImageGenerator()
        except ValueError as e:
            st.session_state.generator = None
            st.session_state.api_error = str(e)

    if "chat_session" not in st.session_state:
        try:
            st.session_state.chat_session = ChatSession()
        except ValueError as e:
            st.session_state.chat_session = None


def main():
    """Main application entry point."""
    # Initialize session state
    init_session_state()

    # Create translator for current language
    t = Translator(st.session_state.language)

    # Render sidebar and get settings
    settings = render_sidebar(t)

    # Header
    st.title(f"🍌 {t('app.title')}")
    st.caption(t("app.subtitle"))

    # Check for API key error
    if st.session_state.get("api_error"):
        st.error(t("errors.api_key_missing"))
        st.info("Please create a `.env` file with your `GOOGLE_API_KEY`.")
        st.code("GOOGLE_API_KEY=your_api_key_here", language="bash")
        return

    # Get services from session state
    generator = st.session_state.generator
    chat_session = st.session_state.chat_session

    # Render main content based on mode
    mode = settings["mode"]

    if mode == "basic":
        render_basic_generation(t, settings, generator)
    elif mode == "chat":
        render_chat_generation(t, settings, chat_session)
    elif mode == "history":
        render_history(t)


if __name__ == "__main__":
    main()
