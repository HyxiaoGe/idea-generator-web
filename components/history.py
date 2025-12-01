"""
Image generation history component with pagination and search.
"""
import math
from io import BytesIO
from datetime import datetime
import streamlit as st
import requests
from i18n import Translator
from services import get_storage, get_history_sync


# Pagination settings
DEFAULT_PER_PAGE = 8
PER_PAGE_OPTIONS = [4, 8, 12, 16]

# Available generation modes for filtering
GENERATION_MODES = ["basic", "chat", "batch", "blend", "style", "search", "template"]


def _init_history_state():
    """Initialize history-related session state."""
    if "history_page" not in st.session_state:
        st.session_state.history_page = 1
    if "history_search" not in st.session_state:
        st.session_state.history_search = ""
    if "history_filter_mode" not in st.session_state:
        st.session_state.history_filter_mode = "all"
    if "history_per_page" not in st.session_state:
        st.session_state.history_per_page = DEFAULT_PER_PAGE


def _filter_history(history: list, search_query: str, mode_filter: str) -> list:
    """Filter history items based on search query and mode."""
    filtered = history

    if search_query.strip():
        query_lower = search_query.lower()
        filtered = [
            item for item in filtered
            if query_lower in item.get("prompt", "").lower()
        ]

    if mode_filter != "all":
        filtered = [
            item for item in filtered
            if item.get("mode", "basic") == mode_filter
        ]

    return filtered


def _get_paginated_items(items: list, page: int, per_page: int) -> tuple:
    """Get paginated subset of items."""
    total_items = len(items)
    total_pages = max(1, math.ceil(total_items / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    return items[start_idx:end_idx], total_pages


def _preload_next_page(items: list, current_page: int, per_page: int):
    """Preload images for the next page."""
    history_sync = get_history_sync()
    next_start = current_page * per_page
    next_end = next_start + per_page
    next_items = items[next_start:next_end]

    keys_to_preload = []
    for item in next_items:
        file_key = item.get("key") or item.get("filename")
        if file_key:
            keys_to_preload.append(file_key)

    if keys_to_preload:
        history_sync.preload_images(keys_to_preload)


def _get_image_source(item: dict):
    """Get the best image source (CDN URL or PIL Image)."""
    if item.get("r2_url"):
        return item["r2_url"]
    return item.get("image")


def _get_download_data(item: dict) -> tuple:
    """
    Get download data for an image.
    Returns (bytes_data, filename, mime_type)
    """
    filename = item.get("filename", "image.png")
    if "/" in filename:
        filename = filename.split("/")[-1]

    # If we have R2 URL, fetch the image
    if item.get("r2_url"):
        try:
            response = requests.get(item["r2_url"], timeout=10)
            if response.status_code == 200:
                return response.content, filename, "image/png"
        except Exception:
            pass

    # Fall back to PIL Image
    if item.get("image"):
        buf = BytesIO()
        item["image"].save(buf, format="PNG")
        return buf.getvalue(), filename, "image/png"

    return None, filename, "image/png"


@st.dialog("🖼️", width="large")
def _open_preview_dialog(item: dict, t: Translator):
    """Modal dialog for image preview."""
    # Title
    st.subheader(t("history.fullscreen_title"))

    # Full-size image
    image_source = _get_image_source(item)
    if image_source:
        st.image(image_source, width="stretch")

    # Prompt
    st.markdown(f"**{t('history.prompt_label')}:**")
    st.text(item.get("prompt", "N/A"))

    # Settings
    settings = item.get("settings", {})
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t("sidebar.params.aspect_ratio"), settings.get("aspect_ratio", "N/A"))
    with col2:
        st.metric(t("sidebar.params.resolution"), settings.get("resolution", "N/A"))
    with col3:
        st.metric(t("sidebar.mode"), item.get("mode", "basic"))

    # Duration and time
    duration = item.get("duration", 0)
    created_at = item.get("created_at", "")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            time_str = "N/A"
    else:
        time_str = "N/A"

    st.caption(f"⏱️ {duration:.2f} {t('basic.seconds')} | 📅 {time_str}")

    # Download button
    data, filename, mime = _get_download_data(item)
    if data:
        st.download_button(
            f"⬇️ {t('history.download_btn')}",
            data=data,
            file_name=filename,
            mime=mime,
            width="stretch",
        )


def render_history(t: Translator):
    """Render the image generation history with pagination and search."""
    _init_history_state()

    st.header(t("history.title"))
    st.caption(t("history.description"))

    history_sync = get_history_sync()

    # Sync from disk on load
    if "history" not in st.session_state or not st.session_state.history:
        with st.spinner(t("history.loading")):
            history_sync.sync_from_disk(force=True)

    full_history = st.session_state.get("history", [])

    # Search and filter controls
    col_search, col_filter, col_per_page = st.columns([3, 2, 1])

    with col_search:
        search_query = st.text_input(
            t("history.search_placeholder"),
            value=st.session_state.history_search,
            placeholder=t("history.search_placeholder"),
            key="history_search_input",
            label_visibility="collapsed"
        )
        if search_query != st.session_state.history_search:
            st.session_state.history_search = search_query
            st.session_state.history_page = 1
            st.rerun()

    with col_filter:
        mode_options = ["all"] + GENERATION_MODES
        mode_labels = {
            "all": t("history.filter_all"),
            "basic": t("sidebar.modes.basic"),
            "chat": t("sidebar.modes.chat"),
            "batch": t("sidebar.modes.batch"),
            "blend": t("sidebar.modes.blend"),
            "style": t("sidebar.modes.blend"),
            "search": t("sidebar.modes.search"),
            "template": t("sidebar.modes.templates"),
        }
        current_filter_idx = mode_options.index(st.session_state.history_filter_mode) if st.session_state.history_filter_mode in mode_options else 0

        filter_mode = st.selectbox(
            t("history.filter_mode"),
            options=mode_options,
            format_func=lambda x: mode_labels.get(x, x),
            index=current_filter_idx,
            key="history_filter_select",
            label_visibility="collapsed"
        )
        if filter_mode != st.session_state.history_filter_mode:
            st.session_state.history_filter_mode = filter_mode
            st.session_state.history_page = 1
            st.rerun()

    with col_per_page:
        per_page = st.selectbox(
            t("history.per_page"),
            options=PER_PAGE_OPTIONS,
            index=PER_PAGE_OPTIONS.index(st.session_state.history_per_page) if st.session_state.history_per_page in PER_PAGE_OPTIONS else 1,
            key="history_per_page_select",
            label_visibility="collapsed"
        )
        if per_page != st.session_state.history_per_page:
            st.session_state.history_per_page = per_page
            st.session_state.history_page = 1
            st.rerun()

    # Refresh button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button(f"🔄 {t('history.refresh_btn')}", width="stretch"):
            with st.spinner(t("history.loading")):
                history_sync.sync_from_disk(force=True)
            st.session_state.history_page = 1
            st.rerun()

    # Filter history
    filtered_history = _filter_history(
        full_history,
        st.session_state.history_search,
        st.session_state.history_filter_mode
    )

    # Show count
    if len(filtered_history) != len(full_history):
        st.caption(f"📊 {t('history.count', count=len(filtered_history))} / {t('history.total_count', count=len(full_history))}")
    elif len(full_history) > 0:
        st.caption(f"📊 {t('history.count', count=len(full_history))}")

    # Empty state
    if not filtered_history:
        if full_history:
            st.info(t("history.no_results"))
        else:
            _render_empty_state(t)
        return

    st.divider()

    # Pagination
    paginated_items, total_pages = _get_paginated_items(
        filtered_history,
        st.session_state.history_page,
        st.session_state.history_per_page
    )

    # Preload next page
    if st.session_state.history_page < total_pages:
        _preload_next_page(
            filtered_history,
            st.session_state.history_page,
            st.session_state.history_per_page
        )

    # Pagination controls (top)
    if total_pages > 1:
        _render_pagination_controls(t, total_pages)

    # Display history items in grid
    cols_per_row = 2
    for row_idx in range(0, len(paginated_items), cols_per_row):
        cols = st.columns(cols_per_row)

        for col_idx, col in enumerate(cols):
            item_idx = row_idx + col_idx
            if item_idx >= len(paginated_items):
                break

            item = paginated_items[item_idx]
            with col:
                _render_history_item(t, item, item_idx)

    # Pagination controls (bottom)
    if total_pages > 1:
        st.divider()
        _render_pagination_controls(t, total_pages, key_suffix="_bottom")



def _render_pagination_controls(t: Translator, total_pages: int, key_suffix: str = ""):
    """Render pagination controls."""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button(
            f"◀ {t('history.prev_btn')}",
            disabled=st.session_state.history_page <= 1,
            width="stretch",
            key=f"prev_btn{key_suffix}"
        ):
            st.session_state.history_page -= 1
            st.rerun()

    with col2:
        st.markdown(
            f"<div style='text-align: center; padding: 8px;'>"
            f"{t('history.page_info', current=st.session_state.history_page, total=total_pages)}"
            f"</div>",
            unsafe_allow_html=True
        )

    with col3:
        if st.button(
            f"{t('history.next_btn')} ▶",
            disabled=st.session_state.history_page >= total_pages,
            width="stretch",
            key=f"next_btn{key_suffix}"
        ):
            st.session_state.history_page += 1
            st.rerun()


def _render_empty_state(t: Translator):
    """Render enhanced empty state for history."""
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 40px 20px;">
                <div style="font-size: 64px; margin-bottom: 16px;">🎨</div>
                <h3 style="margin-bottom: 8px;">{t("history.empty")}</h3>
                <p style="color: #888; margin-bottom: 24px;">{t("history.empty_hint")}</p>
            </div>
            """,
            unsafe_allow_html=True
        )


def _render_history_item(t: Translator, item: dict, idx: int):
    """Render a single history item with click-to-preview."""
    with st.container(border=True):
        image_source = _get_image_source(item)

        if image_source:
            # Click image to preview - button overlays the image area
            if st.button(
                f"🔍 {t('history.preview_btn')}",
                key=f"preview_{idx}_{st.session_state.history_page}",
                width="stretch",
                type="secondary",
            ):
                _open_preview_dialog(item, t)

            st.image(image_source, width="stretch")

        # Prompt (truncated)
        prompt_text = item.get('prompt', 'N/A')
        if len(prompt_text) > 80:
            prompt_text = prompt_text[:80] + "..."
        st.caption(f"**{t('history.prompt_label')}:** {prompt_text}")

        # Settings info
        settings = item.get("settings", {})
        mode = item.get("mode", "basic")
        st.caption(f"{settings.get('aspect_ratio', 'N/A')} | {settings.get('resolution', 'N/A')} | {mode}")

        # Time info
        duration = item.get("duration", 0)
        created_at = item.get("created_at", "")
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                time_str = dt.strftime("%m/%d %H:%M")
            except (ValueError, TypeError):
                time_str = ""
        else:
            time_str = ""

        info_parts = [f"⏱️ {duration:.2f}s"]
        if time_str:
            info_parts.append(f"📅 {time_str}")
        st.caption(" | ".join(info_parts))

        # Download button
        data, filename, mime = _get_download_data(item)
        if data:
            st.download_button(
                f"⬇️ {t('history.download_btn')}",
                data=data,
                file_name=filename,
                mime=mime,
                key=f"download_{idx}_{st.session_state.history_page}",
                width="stretch",
            )
