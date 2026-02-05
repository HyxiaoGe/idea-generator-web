"""
Async helper utilities for Streamlit.
Handles event loop management to avoid "Event loop is closed" errors.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_async(coro: Coroutine) -> Any:
    """
    Run an async coroutine safely in Streamlit.

    Always creates a new event loop to avoid "Event loop is closed" errors.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    # Always create a fresh event loop - most reliable approach
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
