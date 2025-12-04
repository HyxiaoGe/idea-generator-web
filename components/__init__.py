"""
UI Components for Nano Banana Lab.
"""
from .sidebar import render_sidebar
from .basic_generation import render_basic_generation
from .chat_generation import render_chat_generation
from .history import render_history
from .style_transfer import render_style_transfer
from .search_generation import render_search_generation
from .batch_generation import render_batch_generation
from .trial_quota_display import (
    render_quota_status_compact,
    render_quota_status_detailed,
    check_and_show_quota_warning,
    consume_quota_after_generation,
)

__all__ = [
    "render_sidebar",
    "render_basic_generation",
    "render_chat_generation",
    "render_history",
    "render_style_transfer",
    "render_search_generation",
    "render_batch_generation",
    "render_quota_status_compact",
    "render_quota_status_detailed",
    "check_and_show_quota_warning",
    "consume_quota_after_generation",
]
