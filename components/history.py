"""
Image generation history component.
"""
from io import BytesIO
from datetime import datetime
import streamlit as st
from i18n import Translator
from services import get_storage


def load_history_from_disk():
    """Load history from disk storage if session state is empty."""
    storage = get_storage()
    disk_history = storage.get_history(limit=50)

    if disk_history:
        loaded_history = []
        for record in disk_history:
            image = storage.load_image(record["filename"])
            if image:
                loaded_history.append({
                    "prompt": record.get("prompt", ""),
                    "image": image,
                    "text": record.get("text_response"),
                    "thinking": record.get("thinking"),
                    "duration": record.get("duration", 0),
                    "settings": record.get("settings", {}),
                    "filename": record["filename"],
                    "created_at": record.get("created_at"),
                })
        return loaded_history
    return []


def render_history(t: Translator):
    """
    Render the image generation history.

    Args:
        t: Translator instance
    """
    st.header(t("history.title"))
    st.caption(t("history.description"))

    # Load from disk if session state is empty
    if "history" not in st.session_state or not st.session_state.history:
        st.session_state.history = load_history_from_disk()

    # Check if history exists
    if not st.session_state.history:
        st.info(t("history.empty"))

        # Show storage location hint
        storage = get_storage()
        st.caption(f"📁 {t('history.storage_path')}: `{storage.output_dir}`")
        return

    # Clear history button
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button(t("history.clear_btn"), type="secondary"):
            st.session_state.show_clear_confirm = True

    with col2:
        # Show storage info
        storage = get_storage()
        st.caption(f"📁 `{storage.output_dir}`")

    # Confirmation dialog
    if st.session_state.get("show_clear_confirm"):
        with st.container():
            st.warning(t("history.clear_confirm"))
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                if st.button("Yes", type="primary"):
                    # Clear both session state and disk storage
                    storage = get_storage()
                    storage.clear_history()
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
                    prompt_text = item.get('prompt', 'N/A')
                    if len(prompt_text) > 100:
                        prompt_text = prompt_text[:100] + "..."
                    st.caption(f"**{t('history.prompt_label')}:** {prompt_text}")

                    # Settings info
                    settings = item.get("settings", {})
                    settings_str = f"{settings.get('aspect_ratio', 'N/A')} | {settings.get('resolution', 'N/A')}"
                    st.caption(settings_str)

                    # Duration and filename
                    duration = item.get("duration", 0)
                    info_parts = [f"⏱️ {duration:.2f}s"]
                    if item.get("filename"):
                        info_parts.append(f"📄 {item['filename']}")
                    st.caption(" | ".join(info_parts))

                    # Download button
                    if item.get("image"):
                        buf = BytesIO()
                        item["image"].save(buf, format="PNG")
                        filename = item.get("filename", f"history_{item_idx}.png")
                        st.download_button(
                            t("history.download_btn"),
                            data=buf.getvalue(),
                            file_name=filename,
                            mime="image/png",
                            key=f"download_history_{item_idx}",
                            use_container_width=True
                        )
