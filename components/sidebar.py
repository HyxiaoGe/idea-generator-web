"""
Sidebar component with settings and configuration.
"""
import streamlit as st
from i18n import LANGUAGES, Translator


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

        # Language selection
        st.subheader(t("sidebar.language"))
        lang_options = list(LANGUAGES.keys())
        lang_labels = list(LANGUAGES.values())

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
    }
