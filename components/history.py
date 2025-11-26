"""
Image generation history component.
"""
from io import BytesIO
from datetime import datetime
import streamlit as st
from i18n import Translator
from services import get_storage, get_history_sync


def render_history(t: Translator):
    """
    Render the image generation history.

    Args:
        t: Translator instance
    """
    st.header(t("history.title"))
    st.caption(t("history.description"))

    # Get history sync manager
    history_sync = get_history_sync()

    # Sync from disk on load or refresh
    if "history" not in st.session_state or not st.session_state.history:
        with st.spinner(t("history.loading")):
            history_sync.sync_from_disk(force=True)

    # Header row with actions
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

    with col1:
        # Refresh button to sync from disk
        if st.button(f"🔄 {t('history.refresh_btn')}", use_container_width=True):
            with st.spinner(t("history.loading")):
                history_sync.sync_from_disk(force=True)
            st.rerun()

    with col2:
        if st.button(t("history.clear_btn"), type="secondary", use_container_width=True):
            st.session_state.show_clear_confirm = True

    with col3:
        # Show storage info and R2 status
        storage = get_storage()
        status_icon = "☁️" if storage.r2_enabled else "💾"
        st.caption(f"{status_icon} `{storage.base_output_dir}`")

    # Show count
    history_count = len(st.session_state.get("history", []))
    if history_count > 0:
        st.caption(f"📊 {t('history.count', count=history_count)}")

    # Check if history exists
    if not st.session_state.get("history"):
        st.info(t("history.empty"))
        return

    # Confirmation dialog for clear
    if st.session_state.get("show_clear_confirm"):
        with st.container():
            st.warning(t("history.clear_confirm"))
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                if st.button(t("history.yes_btn"), type="primary"):
                    storage = get_storage()
                    storage.clear_history()
                    st.session_state.history = []
                    st.session_state.show_clear_confirm = False
                    st.toast(t("history.cleared"), icon="🗑️")
                    st.rerun()
            with col2:
                if st.button(t("history.no_btn")):
                    st.session_state.show_clear_confirm = False
                    st.rerun()

    st.divider()

    # Display history items
    history = st.session_state.history

    # Use columns for grid layout
    cols_per_row = 2
    for row_idx in range(0, len(history), cols_per_row):
        cols = st.columns(cols_per_row)

        for col_idx, col in enumerate(cols):
            item_idx = row_idx + col_idx
            if item_idx >= len(history):
                break

            item = history[item_idx]

            with col:
                with st.container(border=True):
                    # Image
                    if item.get("image"):
                        st.image(item["image"], use_container_width=True)

                    # Prompt
                    prompt_text = item.get('prompt', 'N/A')
                    if len(prompt_text) > 100:
                        prompt_text = prompt_text[:100] + "..."
                    st.caption(f"**{t('history.prompt_label')}:** {prompt_text}")

                    # Settings info
                    settings = item.get("settings", {})
                    settings_str = f"{settings.get('aspect_ratio', 'N/A')} | {settings.get('resolution', 'N/A')}"
                    st.caption(settings_str)

                    # Duration and time
                    duration = item.get("duration", 0)
                    created_at = item.get("created_at", "")
                    if created_at:
                        try:
                            dt = datetime.fromisoformat(created_at)
                            time_str = dt.strftime("%m/%d %H:%M")
                        except:
                            time_str = ""
                    else:
                        time_str = ""

                    info_parts = [f"⏱️ {duration:.2f}s"]
                    if time_str:
                        info_parts.append(f"📅 {time_str}")
                    st.caption(" | ".join(info_parts))

                    # Download button
                    if item.get("image"):
                        buf = BytesIO()
                        item["image"].save(buf, format="PNG")
                        filename = item.get("filename", f"history_{item_idx}.png")
                        if "/" in filename:
                            filename = filename.split("/")[-1]
                        st.download_button(
                            f"⬇️ {t('history.download_btn')}",
                            data=buf.getvalue(),
                            file_name=filename,
                            mime="image/png",
                            key=f"download_history_{item_idx}",
                            use_container_width=True
                        )
