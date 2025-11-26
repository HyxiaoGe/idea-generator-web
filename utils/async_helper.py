"""
Async helper utilities for Streamlit.
Handles event loop management to avoid "Event loop is closed" errors.
"""
import asyncio
from typing import Coroutine, Any


def run_async(coro: Coroutine) -> Any:
    """
    Run an async coroutine safely in Streamlit.

    This handles the common "Event loop is closed" error that occurs
    when using asyncio.run() multiple times in Streamlit.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
        # If we're in a running loop, we can't use run_until_complete
        if loop.is_running():
            # Create a new loop in a thread-safe way
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        # Create a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            # Set a new loop for next time
            asyncio.set_event_loop(asyncio.new_event_loop())
