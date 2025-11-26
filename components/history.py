"""
Image generation history component.
"""
from io import BytesIO
from datetime import datetime
import streamlit as st
from i18n import Translator


def render_history(t: Translator):
    """
    Render the image generation history.

    Args:
        t: Translator instance
    """
    st.header(t("history.title"))
    st.caption(t("history.description"))

    # Check if history exists
    if "history" not in st.session_state or not st.session_state.history:
        st.info(t("history.empty"))
        return

    # Clear history button
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button(t("history.clear_btn"), type="secondary"):
            st.session_state.show_clear_confirm = True

    # Confirmation dialog
    if st.session_state.get("show_clear_confirm"):
        with st.container():
            st.warning(t("history.clear_confirm"))
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                if st.button("Yes", type="primary"):
                    st.session_state.history = []
                    st.session_state.show_clear_confirm = False
                    st.rerun()
            with col2:
                if st.button("No"):
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
                    st.caption(f"**{t('history.prompt_label')}:** {item.get('prompt', 'N/A')[:100]}...")

                    # Settings info
                    settings = item.get("settings", {})
                    settings_str = f"{settings.get('aspect_ratio', 'N/A')} | {settings.get('resolution', 'N/A')}"
                    st.caption(settings_str)

                    # Duration
                    duration = item.get("duration", 0)
                    st.caption(f"⏱️ {duration:.2f}s")

                    # Download button
                    if item.get("image"):
                        buf = BytesIO()
                        item["image"].save(buf, format="PNG")
                        st.download_button(
                            t("history.download_btn"),
                            data=buf.getvalue(),
                            file_name=f"history_{item_idx}.png",
                            mime="image/png",
                            key=f"download_history_{item_idx}",
                            use_container_width=True
                        )
