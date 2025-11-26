"""
Sidebar component with settings and configuration.
"""
import os
import streamlit as st
from i18n import LANGUAGES, Translator


def render_api_key_section(t: Translator) -> bool:
    """
    Render the API key configuration section.

    Returns:
        True if API key is configured, False otherwise
    """
    st.subheader(t("sidebar.api_key.title"))

    # Check if API key exists in environment
    env_api_key = os.getenv("GOOGLE_API_KEY")
    has_env_key = bool(env_api_key)

    # Initialize session state for API key
    if "user_api_key" not in st.session_state:
        st.session_state.user_api_key = ""
    if "api_key_valid" not in st.session_state:
        st.session_state.api_key_valid = has_env_key
    if "api_key_source" not in st.session_state:
        st.session_state.api_key_source = "env" if has_env_key else "user"

    # Show current status
    if st.session_state.api_key_valid:
        if st.session_state.api_key_source == "env":
            st.success(t("sidebar.api_key.env_configured"))
        else:
            st.success(t("sidebar.api_key.user_configured"))

    # API key input
    with st.expander(t("sidebar.api_key.configure"), expanded=not st.session_state.api_key_valid):
        st.caption(t("sidebar.api_key.help"))

        api_key_input = st.text_input(
            t("sidebar.api_key.input_label"),
            type="password",
            placeholder="AIza...",
            key="api_key_input",
            value=st.session_state.user_api_key
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button(t("sidebar.api_key.validate_btn"), use_container_width=True):
                if api_key_input:
                    with st.spinner(t("sidebar.api_key.validating")):
                        from services import ImageGenerator
                        is_valid, message = ImageGenerator.validate_api_key(api_key_input)

                    if is_valid:
                        st.session_state.user_api_key = api_key_input
                        st.session_state.api_key_valid = True
                        st.session_state.api_key_source = "user"
                        st.session_state.api_key_changed = True
                        st.success(t("sidebar.api_key.valid"))
                        st.rerun()
                    else:
                        st.error(f"{t('sidebar.api_key.invalid')}: {message}")
                else:
                    st.warning(t("sidebar.api_key.empty"))

        with col2:
            if st.button(t("sidebar.api_key.clear_btn"), use_container_width=True):
                st.session_state.user_api_key = ""
                st.session_state.api_key_valid = has_env_key
                st.session_state.api_key_source = "env" if has_env_key else "user"
                st.session_state.api_key_changed = True
                st.rerun()

        # Link to get API key
        st.markdown(f"[{t('sidebar.api_key.get_key')}](https://aistudio.google.com/app/apikey)")

    return st.session_state.api_key_valid


def get_current_api_key() -> str:
    """Get the current API key from session state or environment."""
    if st.session_state.get("user_api_key"):
        return st.session_state.user_api_key
    return os.getenv("GOOGLE_API_KEY", "")


def render_sidebar(t: Translator) -> dict:
    """
    Render the sidebar with all settings.

    Args:
        t: Translator instance

    Returns:
        Dictionary with all selected settings
    """
    with st.sidebar:
        st.title(t("sidebar.title"))

        # API Key section
        api_key_valid = render_api_key_section(t)

        st.divider()

        # Language selection
        st.subheader(t("sidebar.language"))
        lang_options = list(LANGUAGES.keys())

        current_lang_idx = lang_options.index(st.session_state.get("language", "en"))
        selected_lang = st.selectbox(
            t("sidebar.language"),
            options=lang_options,
            format_func=lambda x: LANGUAGES[x],
            index=current_lang_idx,
            key="language_selector",
            label_visibility="collapsed"
        )

        # Update language in session state
        if selected_lang != st.session_state.get("language"):
            st.session_state.language = selected_lang
            st.rerun()

        st.divider()

        # Mode selection
        st.subheader(t("sidebar.mode"))
        modes = {
            "basic": t("sidebar.modes.basic"),
            "chat": t("sidebar.modes.chat"),
            "batch": t("sidebar.modes.batch"),
            "blend": t("sidebar.modes.blend"),
            "search": t("sidebar.modes.search"),
            "templates": t("sidebar.modes.templates"),
            "history": t("sidebar.modes.history"),
        }

        selected_mode = st.radio(
            t("sidebar.mode"),
            options=list(modes.keys()),
            format_func=lambda x: modes[x],
            index=0,
            key="mode_selector",
            label_visibility="collapsed"
        )

        st.divider()

        # Parameters
        st.subheader(t("sidebar.params.title"))

        aspect_ratio = st.selectbox(
            t("sidebar.params.aspect_ratio"),
            options=["1:1", "16:9", "9:16", "4:3", "3:4"],
            index=1,
            key="aspect_ratio"
        )

        resolution = st.selectbox(
            t("sidebar.params.resolution"),
            options=["1K", "2K", "4K"],
            index=0,
            key="resolution"
        )

        enable_thinking = st.checkbox(
            t("sidebar.params.thinking"),
            value=False,
            key="enable_thinking"
        )

        enable_search = st.checkbox(
            t("sidebar.params.search"),
            value=False,
            key="enable_search"
        )

        st.divider()

        # About section
        with st.expander(t("sidebar.about")):
            st.write(t("sidebar.about_text"))
            st.caption(t("app.footer"))

    return {
        "language": selected_lang,
        "mode": selected_mode,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "enable_thinking": enable_thinking,
        "enable_search": enable_search,
        "api_key_valid": api_key_valid,
    }
