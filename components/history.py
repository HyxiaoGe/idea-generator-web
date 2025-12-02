"""
Image generation history component with pagination and search.
"""
import math
from io import BytesIO
from datetime import datetime, date, timedelta
import streamlit as st
import requests
from i18n import Translator
from services import (
    get_current_user_storage,
    get_current_user_history_sync,
    get_history_sync,
    is_authenticated,
)


# Pagination settings
DEFAULT_PER_PAGE = 8
PER_PAGE_OPTIONS = [4, 8, 12, 16]

# Available generation modes for filtering
GENERATION_MODES = ["basic", "chat", "batch", "blend", "style", "search", "template"]

# Sort options
SORT_OPTIONS = ["newest", "oldest", "fastest", "slowest"]

# Grid columns options
GRID_COLS_OPTIONS = [2, 3, 4]
DEFAULT_GRID_COLS = 4

# Data source options
DATA_SOURCE_OPTIONS = ["personal", "shared"]


def _get_mode_label(mode: str, t: Translator) -> str:
    """Get translated label for generation mode."""
    mode_labels = {
        "basic": t("sidebar.modes.basic"),
        "chat": t("sidebar.modes.chat"),
        "batch": t("sidebar.modes.batch"),
        "blend": t("sidebar.modes.blend"),
        "style": t("sidebar.modes.style"),
        "search": t("sidebar.modes.search"),
        "template": t("sidebar.modes.templates"),
    }
    return mode_labels.get(mode, mode)


def _init_history_state():
    """Initialize history-related session state with defaults."""
    defaults = {
        "history_page": 1,
        "history_search": "",
        "history_filter_mode": "all",
        "history_per_page": DEFAULT_PER_PAGE,
        "history_sort": "newest",
        "history_date_range": "all",
        "history_grid_cols": DEFAULT_GRID_COLS,
        "history_data_source": "personal" if is_authenticated() else "shared",
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

    # Validate per_page value (fix corrupted state)
    if st.session_state.get("history_per_page") not in PER_PAGE_OPTIONS:
        st.session_state["history_per_page"] = DEFAULT_PER_PAGE
    
    # Sync widget key with actual value
    if "history_per_page_widget" not in st.session_state:
        st.session_state["history_per_page_widget"] = st.session_state["history_per_page"]


def _filter_history(
    history: list,
    search_query: str,
    mode_filter: str,
    date_range: str,
    sort_by: str
) -> list:
    """Filter and sort history items."""
    filtered = history

    # Search filter
    if search_query.strip():
        query_lower = search_query.lower()
        filtered = [
            item for item in filtered
            if query_lower in item.get("prompt", "").lower()
        ]

    # Mode filter
    if mode_filter != "all":
        filtered = [
            item for item in filtered
            if item.get("mode", "basic") == mode_filter
        ]

    # Date range filter
    if date_range != "all":
        today = date.today()
        if date_range == "today":
            start_date = today
        elif date_range == "week":
            start_date = today - timedelta(days=7)
        elif date_range == "month":
            start_date = today - timedelta(days=30)
        else:
            start_date = None

        if start_date:
            filtered = [
                item for item in filtered
                if _get_item_date(item) and _get_item_date(item) >= start_date
            ]

    # Sort
    if sort_by == "newest":
        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    elif sort_by == "oldest":
        filtered.sort(key=lambda x: x.get("created_at", ""))
    elif sort_by == "fastest":
        filtered.sort(key=lambda x: x.get("duration", 999))
    elif sort_by == "slowest":
        filtered.sort(key=lambda x: x.get("duration", 0), reverse=True)

    return filtered


def _get_item_date(item: dict) -> date | None:
    """Extract date from history item."""
    created_at = item.get("created_at", "")
    if created_at:
        try:
            return datetime.fromisoformat(created_at).date()
        except (ValueError, TypeError):
            pass
    return None


def _get_paginated_items(items: list, page: int, per_page: int) -> tuple:
    """Get paginated subset of items."""
    total_items = len(items)
    total_pages = max(1, math.ceil(total_items / per_page))
    
    # Clamp page to valid range and update session state
    valid_page = max(1, min(page, total_pages))
    if valid_page != page:
        st.session_state.history_page = valid_page
        page = valid_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    return items[start_idx:end_idx], total_pages


# Callbacks for filter changes - avoids manual rerun checks
def _on_filter_change():
    """Reset to page 1 when any filter changes."""
    st.session_state.history_page = 1


def _on_per_page_change():
    """Handle per_page change - sync widget value to session state."""
    st.session_state.history_per_page = st.session_state.history_per_page_widget
    st.session_state.history_page = 1


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

    # Prompt (use st.code for easy copy)
    prompt_text = item.get("prompt", "")
    st.markdown(f"**{t('history.prompt_label')}:**")
    if prompt_text:
        st.code(prompt_text, language=None, wrap_lines=True)
    else:
        st.text("N/A")

    # Settings
    settings = item.get("settings", {})
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t("sidebar.params.aspect_ratio"), settings.get("aspect_ratio", "N/A"))
    with col2:
        st.metric(t("sidebar.params.resolution"), settings.get("resolution", "N/A"))
    with col3:
        st.metric(t("sidebar.mode"), _get_mode_label(item.get("mode", "basic"), t))

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


def _on_data_source_change():
    """Handle data source change - clear and reload history."""
    st.session_state.history_page = 1
    st.session_state.history = []  # Clear current history
    st.session_state["_history_needs_reload"] = True


def render_history(t: Translator):
    """Render the image generation history with pagination and search."""
    _init_history_state()

    st.header(t("history.title"))
    st.caption(t("history.description"))

    # Data source selector (only show if user is logged in)
    user_logged_in = is_authenticated()
    if user_logged_in:
        data_source_labels = {
            "personal": t("history.data_source_personal"),
            "shared": t("history.data_source_shared"),
        }
        st.segmented_control(
            t("history.data_source"),
            options=DATA_SOURCE_OPTIONS,
            format_func=lambda x: data_source_labels.get(x, x),
            key="history_data_source",
            default="personal",
            selection_mode="single",
            on_change=_on_data_source_change,
        )

    # Determine which history sync to use based on data source
    data_source = st.session_state.get("history_data_source", "shared")
    if user_logged_in and data_source == "personal":
        history_sync = get_current_user_history_sync()
        history_key = "_history_personal"
    else:
        history_sync = get_history_sync(user_id=None)  # Shared storage
        history_key = "_history_shared"

    # Reload history when data source changes or first load
    needs_reload = st.session_state.get("_history_needs_reload", False)
    history_loaded_key = f"{history_key}_loaded"

    if needs_reload or not st.session_state.get(history_loaded_key):
        with st.spinner(t("history.loading")):
            history_sync.sync_from_disk(force=True)
        st.session_state[history_loaded_key] = True
        st.session_state["_history_needs_reload"] = False

    full_history = st.session_state.get("history", [])

    # Search and filter controls - Row 1
    col_search, col_filter = st.columns([3, 2])

    with col_search:
        st.text_input(
            t("history.search_placeholder"),
            placeholder=t("history.search_placeholder"),
            key="history_search",
            on_change=_on_filter_change,
            label_visibility="collapsed"
        )

    with col_filter:
        mode_options = ["all"] + GENERATION_MODES
        mode_labels = {
            "all": t("history.filter_all"),
            "basic": t("sidebar.modes.basic"),
            "chat": t("sidebar.modes.chat"),
            "batch": t("sidebar.modes.batch"),
            "blend": t("sidebar.modes.blend"),
            "style": t("sidebar.modes.style"),
            "search": t("sidebar.modes.search"),
            "template": t("sidebar.modes.templates"),
        }

        st.selectbox(
            t("history.filter_mode"),
            options=mode_options,
            format_func=lambda x: mode_labels.get(x, x),
            key="history_filter_mode",
            on_change=_on_filter_change,
            label_visibility="collapsed"
        )

    # Filter controls - Row 2: Sort, Date Range, Per Page
    col_sort, col_date, col_per_page = st.columns([2, 2, 1])

    with col_sort:
        sort_labels = {
            "newest": t("history.sort_newest"),
            "oldest": t("history.sort_oldest"),
            "fastest": t("history.sort_fastest"),
            "slowest": t("history.sort_slowest"),
        }

        st.selectbox(
            t("history.sort_label"),
            options=SORT_OPTIONS,
            format_func=lambda x: sort_labels.get(x, x),
            key="history_sort",
            on_change=_on_filter_change,
            label_visibility="collapsed"
        )

    with col_date:
        date_options = ["all", "today", "week", "month"]
        date_labels = {
            "all": t("history.date_all"),
            "today": t("history.date_today"),
            "week": t("history.date_week"),
            "month": t("history.date_month"),
        }

        st.selectbox(
            t("history.date_label"),
            options=date_options,
            format_func=lambda x: date_labels.get(x, x),
            key="history_date_range",
            on_change=_on_filter_change,
            label_visibility="collapsed"
        )

    with col_per_page:
        # Get current value from session state, ensure it's valid
        current_per_page = st.session_state.get("history_per_page", DEFAULT_PER_PAGE)
        if current_per_page not in PER_PAGE_OPTIONS:
            current_per_page = DEFAULT_PER_PAGE
            st.session_state.history_per_page = current_per_page
        
        current_idx = PER_PAGE_OPTIONS.index(current_per_page)
        st.selectbox(
            t("history.per_page"),
            options=PER_PAGE_OPTIONS,
            index=current_idx,
            key="history_per_page_widget",  # Use separate widget key
            on_change=_on_per_page_change,
            label_visibility="collapsed"
        )

    # Refresh button + Grid columns selector
    col_refresh, col_grid, col_spacer = st.columns([1, 1, 3])
    with col_refresh:
        if st.button(f"🔄 {t('history.refresh_btn')}", width="stretch"):
            with st.spinner(t("history.loading")):
                history_sync.sync_from_disk(force=True)
            st.session_state.history_page = 1

    with col_grid:
        st.segmented_control(
            t("history.grid_cols"),
            options=GRID_COLS_OPTIONS,
            format_func=lambda x: str(x),
            key="history_grid_cols",
            default=DEFAULT_GRID_COLS,
            selection_mode="single",
            label_visibility="collapsed"
        )

    # col_spacer is empty - storage path shown elsewhere if needed

    # Filter history - use widget keys directly from session_state
    filtered_history = _filter_history(
        full_history,
        st.session_state.get("history_search", ""),
        st.session_state.get("history_filter_mode", "all"),
        st.session_state.get("history_date_range", "all"),
        st.session_state.get("history_sort", "newest")
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

    # Pagination - only load current page items (lazy loading)
    # Ensure per_page is a valid value from options
    per_page = st.session_state.get("history_per_page", DEFAULT_PER_PAGE)
    if per_page not in PER_PAGE_OPTIONS:
        per_page = DEFAULT_PER_PAGE
    
    print(f"[History Debug] items={len(filtered_history)}, per_page={per_page}, page={st.session_state.history_page}")
    
    paginated_items, total_pages = _get_paginated_items(
        filtered_history,
        st.session_state.history_page,
        per_page
    )

    # Display history items in grid
    cols_per_row = st.session_state.get("history_grid_cols") or DEFAULT_GRID_COLS
    for row_idx in range(0, len(paginated_items), cols_per_row):
        cols = st.columns(cols_per_row)

        for col_idx, col in enumerate(cols):
            item_idx = row_idx + col_idx
            if item_idx >= len(paginated_items):
                break

            item = paginated_items[item_idx]
            with col:
                _render_history_item(t, item, item_idx)

    # Pagination controls (only at bottom, only if more than 1 page)
    if total_pages > 1:
        st.divider()
        _render_pagination_controls(t, total_pages)



def _on_prev_page():
    """Go to previous page."""
    if st.session_state.history_page > 1:
        st.session_state.history_page -= 1


def _on_next_page(total_pages: int):
    """Go to next page."""
    if st.session_state.history_page < total_pages:
        st.session_state.history_page += 1


def _render_pagination_controls(t: Translator, total_pages: int, key_suffix: str = ""):
    """Render pagination controls."""
    current_page = st.session_state.history_page
    
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        st.button(
            f"◀ {t('history.prev_btn')}",
            disabled=current_page <= 1,
            width="stretch",
            key=f"prev_btn{key_suffix}",
            on_click=_on_prev_page
        )

    with col2:
        st.markdown(
            f"<div style='text-align: center; padding: 8px;'>"
            f"{t('history.page_info', current=current_page, total=total_pages)}"
            f"</div>",
            unsafe_allow_html=True
        )

    with col3:
        st.button(
            f"{t('history.next_btn')} ▶",
            disabled=current_page >= total_pages,
            width="stretch",
            key=f"next_btn{key_suffix}",
            on_click=_on_next_page,
            args=(total_pages,)
        )


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

        # Prompt (single line with CSS ellipsis)
        prompt_text = item.get('prompt', 'N/A')
        st.markdown(
            f"""<p style="font-size: 0.875rem; color: rgba(49, 51, 63, 0.6); 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin: 0;">
            <strong>{t('history.prompt_label')}:</strong> {prompt_text}</p>""",
            unsafe_allow_html=True
        )

        # Settings info
        settings = item.get("settings", {})
        mode_label = _get_mode_label(item.get("mode", "basic"), t)
        st.caption(f"{settings.get('aspect_ratio', 'N/A')} | {settings.get('resolution', 'N/A')} | {mode_label}")

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
