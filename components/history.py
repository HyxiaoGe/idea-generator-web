"""
Image generation history component with pagination and search.
"""
import math
from io import BytesIO
from datetime import datetime
import streamlit as st
from i18n import Translator
from services import get_current_user_storage, get_current_user_history_sync


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
    """
    Filter history items based on search query and mode.

    Args:
        history: List of history items
        search_query: Search string to filter by prompt
        mode_filter: Generation mode to filter by ("all" for no filter)

    Returns:
        Filtered list of history items
    """
    filtered = history

    # Filter by search query
    if search_query.strip():
        query_lower = search_query.lower()
        filtered = [
            item for item in filtered
            if query_lower in item.get("prompt", "").lower()
        ]

    # Filter by mode
    if mode_filter != "all":
        filtered = [
            item for item in filtered
            if item.get("mode", "basic") == mode_filter
        ]

    return filtered


def _get_paginated_items(items: list, page: int, per_page: int) -> tuple:
    """
    Get paginated subset of items.

    Args:
        items: Full list of items
        page: Current page number (1-indexed)
        per_page: Items per page

    Returns:
        Tuple of (paginated_items, total_pages)
    """
    total_items = len(items)
    total_pages = max(1, math.ceil(total_items / per_page))

    # Ensure page is within bounds
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    return items[start_idx:end_idx], total_pages


def render_history(t: Translator):
    """
    Render the image generation history with pagination and search.

    Args:
        t: Translator instance
    """
    # Initialize state
    _init_history_state()

    st.header(t("history.title"))
    st.caption(t("history.description"))

    # Get history sync manager
    history_sync = get_current_user_history_sync()

    # Sync from disk on load or refresh
    if "history" not in st.session_state or not st.session_state.history:
        with st.spinner(t("history.loading")):
            history_sync.sync_from_disk(force=True)

    # Get full history
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
            st.session_state.history_page = 1  # Reset to page 1 on search
            st.rerun()

    with col_filter:
        mode_options = ["all"] + GENERATION_MODES
        mode_labels = {
            "all": t("history.filter_all"),
            "basic": t("sidebar.modes.basic"),
            "chat": t("sidebar.modes.chat"),
            "batch": t("sidebar.modes.batch"),
            "blend": t("sidebar.modes.blend"),
            "style": t("sidebar.modes.blend"),  # Style is part of blend
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

    # Action buttons row
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

    with col1:
        if st.button(f"🔄 {t('history.refresh_btn')}", use_container_width=True):
            with st.spinner(t("history.loading")):
                history_sync.sync_from_disk(force=True)
            st.session_state.history_page = 1
            st.rerun()

    with col2:
        if st.button(t("history.clear_btn"), type="secondary", use_container_width=True):
            st.session_state.show_clear_confirm = True

    with col3:
        storage = get_current_user_storage()
        status_icon = "☁️" if storage.r2_enabled else "💾"
        st.caption(f"{status_icon} `{storage.base_output_dir}`")

    # Filter history
    filtered_history = _filter_history(
        full_history,
        st.session_state.history_search,
        st.session_state.history_filter_mode
    )

    # Show count
    if len(filtered_history) != len(full_history):
        st.caption(f"📊 {t('history.count', count=len(filtered_history))} / {len(full_history)} total")
    elif len(full_history) > 0:
        st.caption(f"📊 {t('history.count', count=len(full_history))}")

    # Check if history exists after filtering
    if not filtered_history:
        if full_history:
            st.info(t("history.no_results"))
        else:
            # Enhanced empty state
            _render_empty_state(t)
        return

    # Confirmation dialog for clear
    if st.session_state.get("show_clear_confirm"):
        with st.container():
            st.warning(t("history.clear_confirm"))
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                if st.button(t("history.yes_btn"), type="primary"):
                    storage = get_current_user_storage()
                    storage.clear_history()
                    st.session_state.history = []
                    st.session_state.show_clear_confirm = False
                    st.session_state.history_page = 1
                    st.toast(t("history.cleared"), icon="🗑️")
                    st.rerun()
            with col2:
                if st.button(t("history.no_btn")):
                    st.session_state.show_clear_confirm = False
                    st.rerun()

    # Render preview dialog if active
    _render_preview_dialog(t)

    st.divider()

    # Pagination
    paginated_items, total_pages = _get_paginated_items(
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
            use_container_width=True,
            key=f"prev_btn{key_suffix}"
        ):
            st.session_state.history_page -= 1
            st.rerun()

    with col2:
        st.markdown(
            f"<div style='text-align: center; padding: 8px;'>{t('history.page_info', current=st.session_state.history_page, total=total_pages)}</div>",
            unsafe_allow_html=True
        )

    with col3:
        if st.button(
            f"{t('history.next_btn')} ▶",
            disabled=st.session_state.history_page >= total_pages,
            use_container_width=True,
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
    """Render a single history item with preview capability."""
    with st.container(border=True):
        # Image with click hint
        if item.get("image"):
            # Store item for preview dialog
            preview_key = f"preview_{idx}_{st.session_state.history_page}"
            if st.button(
                "🔍",
                key=preview_key,
                help=t("history.preview_btn"),
                use_container_width=False,
            ):
                st.session_state.preview_item = item
                st.session_state.show_preview = True
                st.rerun()

            st.image(item["image"], use_container_width=True)

        # Prompt
        prompt_text = item.get('prompt', 'N/A')
        if len(prompt_text) > 100:
            prompt_text = prompt_text[:100] + "..."
        st.caption(f"**{t('history.prompt_label')}:** {prompt_text}")

        # Settings info
        settings = item.get("settings", {})
        mode = item.get("mode", "basic")
        settings_str = f"{settings.get('aspect_ratio', 'N/A')} | {settings.get('resolution', 'N/A')} | {mode}"
        st.caption(settings_str)

        # Duration and time
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
        if item.get("image"):
            buf = BytesIO()
            item["image"].save(buf, format="PNG")
            filename = item.get("filename", f"history_{idx}.png")
            if "/" in filename:
                filename = filename.split("/")[-1]
            st.download_button(
                f"⬇️ {t('history.download_btn')}",
                data=buf.getvalue(),
                file_name=filename,
                mime="image/png",
                key=f"download_history_{idx}_{st.session_state.history_page}",
                use_container_width=True
            )


def _render_preview_dialog(t: Translator):
    """Render image preview dialog/modal."""
    if not st.session_state.get("show_preview") or not st.session_state.get("preview_item"):
        return

    item = st.session_state.preview_item

    # Use expander as a pseudo-modal since st.dialog may not be available in all versions
    with st.container():
        st.markdown("---")
        st.subheader(f"🖼️ {t('history.fullscreen_title')}")

        # Close button
        if st.button(f"✕ {t('history.close_btn')}", key="close_preview"):
            st.session_state.show_preview = False
            st.session_state.preview_item = None
            st.rerun()

        # Full-size image
        if item.get("image"):
            st.image(item["image"], use_container_width=True)

        # Full prompt
        st.markdown(f"**{t('history.prompt_label')}:**")
        st.text(item.get("prompt", "N/A"))

        # Settings details
        settings = item.get("settings", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Aspect Ratio", settings.get("aspect_ratio", "N/A"))
        with col2:
            st.metric("Resolution", settings.get("resolution", "N/A"))
        with col3:
            st.metric("Mode", item.get("mode", "basic"))

        # Download in preview
        if item.get("image"):
            buf = BytesIO()
            item["image"].save(buf, format="PNG")
            filename = item.get("filename", "preview.png")
            if "/" in filename:
                filename = filename.split("/")[-1]
            st.download_button(
                f"⬇️ {t('history.download_btn')}",
                data=buf.getvalue(),
                file_name=filename,
                mime="image/png",
                key="download_preview",
                use_container_width=True
            )

        st.markdown("---")
