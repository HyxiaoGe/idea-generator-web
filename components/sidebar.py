"""
Sidebar component with settings and configuration.
"""
import os
import time
import streamlit as st
from i18n import LANGUAGES, Translator
from services import get_persistence, HealthCheckService, get_auth_service


def render_auth_section(t: Translator) -> bool:
    """
    Render the authentication section in the sidebar.
    Login is optional - users can use all features without logging in.

    Returns:
        True if user is authenticated, False otherwise
    """
    auth = get_auth_service()

    # If auth is not available (not configured), skip this section entirely
    if not auth.is_available:
        return False

    st.subheader(t("sidebar.auth.title"))

    if auth.is_authenticated():
        # Show logged in user info
        user = auth.get_current_user()
        if user:
            col1, col2 = st.columns([1, 3])
            with col1:
                if user.avatar_url:
                    st.image(user.avatar_url, width=40)
                else:
                    st.markdown("👤")
            with col2:
                st.markdown(f"**{user.display_name}**")
                st.caption(f"@{user.login}")

        # Logout button
        if st.button(t("sidebar.auth.logout_btn"), key="sidebar_logout", use_container_width=True):
            auth.logout()
            st.rerun()

        return True
    else:
        # Show login button (optional, not required)
        st.caption(t("sidebar.auth.login_benefits"))

        if auth.render_login_button(t("sidebar.auth.login_btn")):
            st.rerun()

        return False


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
            if st.button(t("sidebar.api_key.validate_btn"), width="stretch"):
                if api_key_input:
                    with st.spinner(t("sidebar.api_key.validating")):
                        from services import ImageGenerator
                        is_valid, message = ImageGenerator.validate_api_key(api_key_input)

                    if is_valid:
                        st.session_state.user_api_key = api_key_input
                        st.session_state.api_key_valid = True
                        st.session_state.api_key_source = "user"
                        st.session_state.api_key_changed = True
                        # Save to browser storage for persistence
                        persistence = get_persistence()
                        persistence.save_api_key(api_key_input)
                        st.toast(t("sidebar.api_key.valid"), icon="✅")
                        st.rerun()
                    else:
                        st.toast(f"{t('sidebar.api_key.invalid')}: {message}", icon="❌")
                else:
                    st.toast(t("sidebar.api_key.empty"), icon="⚠️")

        with col2:
            if st.button(t("sidebar.api_key.clear_btn"), width="stretch"):
                st.session_state.user_api_key = ""
                st.session_state.api_key_valid = has_env_key
                st.session_state.api_key_source = "env" if has_env_key else "user"
                st.session_state.api_key_changed = True
                # Clear from browser storage
                persistence = get_persistence()
                persistence.clear_api_key()
                st.rerun()

        # Link to get API key
        st.markdown(f"[{t('sidebar.api_key.get_key')}](https://aistudio.google.com/app/apikey)")

    return st.session_state.api_key_valid


def render_health_check_section(t: Translator, api_key: str):
    """
    Render the API health check status section.

    Args:
        t: Translator instance
        api_key: Current API key to check
    """
    if not api_key:
        return

    HealthCheckService.init_session_state()

    # Get current status
    emoji, status_text = HealthCheckService.get_status_indicator()
    result = HealthCheckService.get_last_result()

    # Display status with check button
    col1, col2 = st.columns([3, 1])

    with col1:
        st.caption(f"{t('sidebar.health.title')}: {emoji} {status_text}")

    with col2:
        # Manual check button
        if st.button("🔄", key="health_check_btn", help=t("sidebar.health.check_btn")):
            with st.spinner(t("sidebar.health.checking")):
                HealthCheckService.run_check(api_key)
            st.rerun()

    # Don't auto-check on page load - only check when user clicks the button
    # This avoids blocking the initial page render with an API call

    # Show last check time
    if result.timestamp > 0:
        elapsed = time.time() - result.timestamp
        if elapsed < 60:
            time_ago = f"{int(elapsed)}s"
        else:
            time_ago = f"{int(elapsed / 60)}m"
        st.caption(f"_{t('sidebar.health.last_check')}: {time_ago} {t('sidebar.health.ago')}_")


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

        # Authentication section (optional - show if available)
        auth_service = get_auth_service()
        user_authenticated = render_auth_section(t)
        if auth_service.is_available:
            st.divider()

        # API Key section
        api_key_valid = render_api_key_section(t)

        # Health check section (only show if API key is valid)
        if api_key_valid:
            render_health_check_section(t, get_current_api_key())

        st.divider()

        # Language selection
        st.subheader(t("sidebar.language"))
        lang_options = list(LANGUAGES.keys())

        def _on_language_change():
            """Handle language change - save to persistence."""
            new_lang = st.session_state.language_selector
            st.session_state.language = new_lang
            persistence = get_persistence()
            persistence.save_language(new_lang)

        current_lang_idx = lang_options.index(st.session_state.get("language", "en"))
        selected_lang = st.selectbox(
            t("sidebar.language"),
            options=lang_options,
            format_func=lambda x: LANGUAGES[x],
            index=current_lang_idx,
            key="language_selector",
            on_change=_on_language_change,
            label_visibility="collapsed"
        )

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

        # Get saved mode or default to "basic"
        mode_options = list(modes.keys())
        saved_mode = st.session_state.get("saved_mode", "basic")
        default_mode_idx = mode_options.index(saved_mode) if saved_mode in mode_options else 0

        selected_mode = st.radio(
            t("sidebar.mode"),
            options=mode_options,
            format_func=lambda x: modes[x],
            index=default_mode_idx,
            key="mode_selector",
            label_visibility="collapsed"
        )

        # Save mode when changed (using on_change would require restructuring)
        if selected_mode != st.session_state.get("saved_mode"):
            st.session_state.saved_mode = selected_mode
            get_persistence().save_mode(selected_mode)

        st.divider()

        # Parameters - load saved settings if available
        st.subheader(t("sidebar.params.title"))

        saved_settings = st.session_state.get("saved_settings", {})

        # Initialize widget values from saved settings on first load
        if "settings_initialized" not in st.session_state:
            st.session_state.settings_initialized = True
            # Pre-populate widget keys with saved values
            if "aspect_ratio" in saved_settings:
                st.session_state["widget_aspect_ratio"] = saved_settings["aspect_ratio"]
            if "resolution" in saved_settings:
                st.session_state["widget_resolution"] = saved_settings["resolution"]
            if "enable_thinking" in saved_settings:
                st.session_state["widget_enable_thinking"] = saved_settings["enable_thinking"]
            if "enable_search" in saved_settings:
                st.session_state["widget_enable_search"] = saved_settings["enable_search"]
            if "safety_level" in saved_settings:
                st.session_state["widget_safety_level"] = saved_settings["safety_level"]

        # Aspect ratio
        aspect_options = ["1:1", "16:9", "9:16", "4:3", "3:4"]
        default_aspect = st.session_state.get("widget_aspect_ratio", saved_settings.get("aspect_ratio", "16:9"))
        aspect_index = aspect_options.index(default_aspect) if default_aspect in aspect_options else 1

        aspect_ratio = st.selectbox(
            t("sidebar.params.aspect_ratio"),
            options=aspect_options,
            index=aspect_index,
            key="widget_aspect_ratio"
        )

        # Resolution
        resolution_options = ["1K", "2K", "4K"]
        default_resolution = st.session_state.get("widget_resolution", saved_settings.get("resolution", "1K"))
        resolution_index = resolution_options.index(default_resolution) if default_resolution in resolution_options else 0

        resolution = st.selectbox(
            t("sidebar.params.resolution"),
            options=resolution_options,
            index=resolution_index,
            key="widget_resolution"
        )

        enable_thinking = st.checkbox(
            t("sidebar.params.thinking"),
            value=st.session_state.get("widget_enable_thinking", saved_settings.get("enable_thinking", False)),
            key="widget_enable_thinking"
        )

        enable_search = st.checkbox(
            t("sidebar.params.search"),
            value=st.session_state.get("widget_enable_search", saved_settings.get("enable_search", False)),
            key="widget_enable_search"
        )

        st.divider()

        # Safety Settings
        st.subheader(t("sidebar.safety.title"))

        safety_levels = {
            "strict": t("sidebar.safety.levels.strict"),
            "moderate": t("sidebar.safety.levels.moderate"),
            "relaxed": t("sidebar.safety.levels.relaxed"),
            "none": t("sidebar.safety.levels.none"),
        }

        safety_options = list(safety_levels.keys())
        default_safety = st.session_state.get("widget_safety_level", saved_settings.get("safety_level", "moderate"))
        safety_index = safety_options.index(default_safety) if default_safety in safety_options else 1

        safety_level = st.selectbox(
            t("sidebar.safety.level_label"),
            options=safety_options,
            format_func=lambda x: safety_levels[x],
            index=safety_index,
            key="widget_safety_level",
            help=t("sidebar.safety.help"),
        )

        # Show warning for "none" level
        if safety_level == "none":
            st.warning(t("sidebar.safety.none_warning"))

        st.divider()

        # About section
        with st.expander(t("sidebar.about")):
            st.write(t("sidebar.about_text"))
            st.caption(t("app.footer"))

    # Build current settings
    current_settings = {
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "enable_thinking": enable_thinking,
        "enable_search": enable_search,
        "safety_level": safety_level,
    }

    # Save settings if changed (skip on first load to avoid unnecessary save)
    if st.session_state.get("settings_initialized") and current_settings != saved_settings:
        st.session_state.saved_settings = current_settings
        persistence = get_persistence()
        if persistence.save_settings(current_settings):
            st.toast(t("sidebar.settings_saved"), icon="💾")

    return {
        "language": selected_lang,
        "mode": selected_mode,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "enable_thinking": enable_thinking,
        "enable_search": enable_search,
        "safety_level": safety_level,
        "api_key_valid": api_key_valid,
        "is_authenticated": user_authenticated,
    }
