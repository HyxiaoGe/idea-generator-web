"""
Image generation history component.
"""
import base64
from io import BytesIO
from datetime import datetime
import streamlit as st
from PIL import Image
from i18n import Translator
from services import get_storage, get_history_sync


def _image_to_base64(image: Image.Image) -> str:
    """Convert PIL Image to base64 string."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _render_clickable_image(image: Image.Image, key: str):
    """
    Render an image that opens fullscreen when clicked/double-clicked.

    Args:
        image: PIL Image to display
        key: Unique key for the component
    """
    img_base64 = _image_to_base64(image)

    html = f"""
    <style>
    .clickable-img-{key} {{
        cursor: pointer;
        border-radius: 8px;
        width: 100%;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    .clickable-img-{key}:hover {{
        transform: scale(1.02);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }}
    .fullscreen-overlay-{key} {{
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.95);
        z-index: 999999;
        justify-content: center;
        align-items: center;
        cursor: zoom-out;
    }}
    .fullscreen-overlay-{key}.active {{
        display: flex;
    }}
    .fullscreen-img-{key} {{
        max-width: 95vw;
        max-height: 95vh;
        object-fit: contain;
    }}
    .close-btn-{key} {{
        position: fixed;
        top: 15px;
        right: 25px;
        color: white;
        font-size: 35px;
        cursor: pointer;
        z-index: 1000000;
        font-weight: bold;
        opacity: 0.8;
        transition: opacity 0.2s;
    }}
    .close-btn-{key}:hover {{
        opacity: 1;
    }}
    .hint-{key} {{
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        color: white;
        font-size: 13px;
        opacity: 0.6;
    }}
    </style>

    <img class="clickable-img-{key}"
         src="data:image/png;base64,{img_base64}"
         onclick="openFullscreen_{key}()"
         title="Click to view fullscreen">

    <div class="fullscreen-overlay-{key}" id="overlay_{key}" onclick="closeFullscreen_{key}()">
        <span class="close-btn-{key}" onclick="closeFullscreen_{key}()">×</span>
        <img class="fullscreen-img-{key}" src="data:image/png;base64,{img_base64}">
        <div class="hint-{key}">Click anywhere or press ESC to close</div>
    </div>

    <script>
    function openFullscreen_{key}() {{
        document.getElementById('overlay_{key}').classList.add('active');
        document.body.style.overflow = 'hidden';
    }}
    function closeFullscreen_{key}() {{
        document.getElementById('overlay_{key}').classList.remove('active');
        document.body.style.overflow = 'auto';
    }}
    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            var overlay = document.getElementById('overlay_{key}');
            if (overlay) {{
                overlay.classList.remove('active');
                document.body.style.overflow = 'auto';
            }}
        }}
    }});
    </script>
    """

    # Calculate height based on image aspect ratio
    width, height = image.size
    aspect = height / width
    container_height = int(300 * aspect) + 10  # Base width ~300px
    container_height = min(max(container_height, 150), 400)  # Clamp between 150-400

    st.components.v1.html(html, height=container_height)


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
                    # Image with click-to-fullscreen
                    if item.get("image"):
                        _render_clickable_image(item["image"], key=f"hist_{item_idx}")

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
