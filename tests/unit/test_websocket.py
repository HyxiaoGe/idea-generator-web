"""
Unit tests for WebSocket manager stale connection cleanup.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from services.websocket_manager import (
    STALE_TIMEOUT,
    Connection,
    WebSocketManager,
)


def _make_connection(conn_id: str, last_ping_offset: float = 0) -> Connection:
    """Create a mock Connection with configurable last_ping time."""
    ws = AsyncMock()
    ws.close = AsyncMock()
    return Connection(
        id=conn_id,
        websocket=ws,
        user_id=f"user_{conn_id}",
        last_ping=datetime.now() - timedelta(seconds=last_ping_offset),
    )


class TestStaleConnectionCleanup:
    """Tests for stale WebSocket connection removal."""

    @pytest.mark.asyncio
    async def test_stale_connection_removed(self):
        """Stale connections (exceeding STALE_TIMEOUT) should be disconnected."""
        manager = WebSocketManager()

        # Add a stale connection (last ping was 120s ago, timeout is 90s)
        stale = _make_connection("stale1", last_ping_offset=STALE_TIMEOUT + 30)
        manager._connections["stale1"] = stale
        manager._user_connections["user_stale1"] = {"stale1"}

        await manager._remove_stale_connections()

        assert "stale1" not in manager._connections
        stale.websocket.close.assert_called_once_with(code=4002, reason="Stale connection")

    @pytest.mark.asyncio
    async def test_active_connection_survives(self):
        """Active connections (within STALE_TIMEOUT) should not be removed."""
        manager = WebSocketManager()

        # Add an active connection (last ping was 10s ago)
        active = _make_connection("active1", last_ping_offset=10)
        manager._connections["active1"] = active
        manager._user_connections["user_active1"] = {"active1"}

        await manager._remove_stale_connections()

        assert "active1" in manager._connections
        active.websocket.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_connections(self):
        """Only stale connections are removed; active ones remain."""
        manager = WebSocketManager()

        stale = _make_connection("stale1", last_ping_offset=STALE_TIMEOUT + 10)
        active = _make_connection("active1", last_ping_offset=5)

        manager._connections["stale1"] = stale
        manager._connections["active1"] = active
        manager._user_connections["user_stale1"] = {"stale1"}
        manager._user_connections["user_active1"] = {"active1"}

        await manager._remove_stale_connections()

        assert "stale1" not in manager._connections
        assert "active1" in manager._connections

    @pytest.mark.asyncio
    async def test_start_stop_cleanup_task(self):
        """Start and stop the cleanup task lifecycle."""
        manager = WebSocketManager()

        await manager.start_stale_cleanup()
        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        await manager.stop_stale_cleanup()
        assert manager._cleanup_task is None

    @pytest.mark.asyncio
    async def test_stop_cleanup_when_not_started(self):
        """Stopping cleanup when not started should be a no-op."""
        manager = WebSocketManager()

        # Should not raise
        await manager.stop_stale_cleanup()
        assert manager._cleanup_task is None

    @pytest.mark.asyncio
    async def test_stale_connection_close_failure(self):
        """Cleanup should continue even if closing a websocket fails."""
        manager = WebSocketManager()

        stale = _make_connection("stale1", last_ping_offset=STALE_TIMEOUT + 30)
        stale.websocket.close = AsyncMock(side_effect=RuntimeError("Already closed"))
        manager._connections["stale1"] = stale
        manager._user_connections["user_stale1"] = {"stale1"}

        # Should not raise
        await manager._remove_stale_connections()

        # Connection should still be removed from manager
        assert "stale1" not in manager._connections
