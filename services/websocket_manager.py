"""
WebSocket connection manager for real-time updates.

Handles WebSocket connections, subscriptions, and message broadcasting.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    """Represents a WebSocket connection."""

    id: str
    websocket: WebSocket
    user_id: str | None
    subscriptions: set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.now)
    last_ping: datetime = field(default_factory=datetime.now)


class WebSocketManager:
    """
    Manages WebSocket connections and message routing.

    Features:
    - Connection management (connect/disconnect)
    - Channel subscriptions
    - Message broadcasting
    - Heartbeat/ping-pong
    """

    def __init__(self):
        self._connections: dict[str, Connection] = {}
        self._user_connections: dict[str, set[str]] = {}
        self._channel_subscriptions: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str | None = None,
    ) -> str:
        """
        Accept a new WebSocket connection.

        Returns the connection ID.
        """
        await websocket.accept()

        connection_id = str(uuid4())
        connection = Connection(
            id=connection_id,
            websocket=websocket,
            user_id=user_id,
        )

        async with self._lock:
            self._connections[connection_id] = connection

            if user_id:
                if user_id not in self._user_connections:
                    self._user_connections[user_id] = set()
                self._user_connections[user_id].add(connection_id)

        logger.info(f"WebSocket connected: {connection_id} (user: {user_id})")

        # Send connected message
        await self._send(
            websocket,
            {
                "type": "connected",
                "payload": {
                    "connection_id": connection_id,
                    "user_id": user_id,
                    "server_time": int(time.time() * 1000),
                },
                "timestamp": datetime.now().isoformat(),
            },
        )

        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Disconnect a WebSocket connection."""
        async with self._lock:
            connection = self._connections.pop(connection_id, None)
            if not connection:
                return

            # Remove from user connections
            if connection.user_id and connection.user_id in self._user_connections:
                self._user_connections[connection.user_id].discard(connection_id)
                if not self._user_connections[connection.user_id]:
                    del self._user_connections[connection.user_id]

            # Remove from all channel subscriptions
            for channel in connection.subscriptions:
                if channel in self._channel_subscriptions:
                    self._channel_subscriptions[channel].discard(connection_id)
                    if not self._channel_subscriptions[channel]:
                        del self._channel_subscriptions[channel]

        logger.info(f"WebSocket disconnected: {connection_id}")

    async def subscribe(self, connection_id: str, channel: str) -> bool:
        """Subscribe a connection to a channel."""
        async with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                return False

            connection.subscriptions.add(channel)

            if channel not in self._channel_subscriptions:
                self._channel_subscriptions[channel] = set()
            self._channel_subscriptions[channel].add(connection_id)

        logger.debug(f"Connection {connection_id} subscribed to {channel}")

        # Send confirmation
        await self.send_to_connection(
            connection_id,
            {
                "type": "subscribed",
                "payload": {"channel": channel},
            },
        )

        return True

    async def unsubscribe(self, connection_id: str, channel: str) -> bool:
        """Unsubscribe a connection from a channel."""
        async with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                return False

            connection.subscriptions.discard(channel)

            if channel in self._channel_subscriptions:
                self._channel_subscriptions[channel].discard(connection_id)
                if not self._channel_subscriptions[channel]:
                    del self._channel_subscriptions[channel]

        # Send confirmation
        await self.send_to_connection(
            connection_id,
            {
                "type": "unsubscribed",
                "payload": {"channel": channel},
            },
        )

        return True

    async def send_to_connection(
        self,
        connection_id: str,
        message: dict[str, Any],
    ) -> bool:
        """Send a message to a specific connection."""
        connection = self._connections.get(connection_id)
        if not connection:
            return False

        return await self._send(connection.websocket, message)

    async def send_to_user(
        self,
        user_id: str,
        message: dict[str, Any],
    ) -> int:
        """Send a message to all connections for a user."""
        connection_ids = self._user_connections.get(user_id, set()).copy()
        sent = 0

        for connection_id in connection_ids:
            if await self.send_to_connection(connection_id, message):
                sent += 1

        return sent

    async def broadcast_to_channel(
        self,
        channel: str,
        message: dict[str, Any],
    ) -> int:
        """Broadcast a message to all subscribers of a channel."""
        connection_ids = self._channel_subscriptions.get(channel, set()).copy()
        sent = 0

        for connection_id in connection_ids:
            if await self.send_to_connection(connection_id, message):
                sent += 1

        return sent

    async def broadcast_all(self, message: dict[str, Any]) -> int:
        """Broadcast a message to all connections."""
        connection_ids = list(self._connections.keys())
        sent = 0

        for connection_id in connection_ids:
            if await self.send_to_connection(connection_id, message):
                sent += 1

        return sent

    async def handle_ping(self, connection_id: str) -> None:
        """Handle a ping message from a client."""
        connection = self._connections.get(connection_id)
        if connection:
            connection.last_ping = datetime.now()

        await self.send_to_connection(
            connection_id,
            {
                "type": "pong",
                "payload": {"server_time": int(time.time() * 1000)},
            },
        )

    async def handle_message(
        self,
        connection_id: str,
        message: dict[str, Any],
    ) -> None:
        """Handle an incoming WebSocket message."""
        msg_type = message.get("type")
        payload = message.get("payload", {})

        if msg_type == "ping":
            await self.handle_ping(connection_id)

        elif msg_type == "subscribe":
            channel = payload.get("channel")
            if channel:
                # Build channel name (e.g., "task:abc123")
                task_id = payload.get("task_id")
                if task_id:
                    channel = f"{channel}:{task_id}"
                await self.subscribe(connection_id, channel)

        elif msg_type == "unsubscribe":
            channel = payload.get("channel")
            if channel:
                task_id = payload.get("task_id")
                if task_id:
                    channel = f"{channel}:{task_id}"
                await self.unsubscribe(connection_id, channel)

        else:
            # Unknown message type
            await self.send_to_connection(
                connection_id,
                {
                    "type": "error",
                    "payload": {
                        "code": "unknown_message_type",
                        "message": f"Unknown message type: {msg_type}",
                    },
                },
            )

    async def _send(
        self,
        websocket: WebSocket,
        message: dict[str, Any],
    ) -> bool:
        """Send a message to a WebSocket."""
        try:
            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()

            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send WebSocket message: {e}")
            return False

    # ============ Task Progress ============

    async def send_task_progress(
        self,
        task_id: str,
        progress: int,
        total: int,
        stage: str | None = None,
        message: str | None = None,
    ) -> int:
        """Send task progress update."""
        return await self.broadcast_to_channel(
            f"task:{task_id}",
            {
                "type": "task:progress",
                "payload": {
                    "task_id": task_id,
                    "progress": progress,
                    "total": total,
                    "stage": stage,
                    "message": message,
                },
            },
        )

    async def send_task_complete(
        self,
        task_id: str,
        results: list[dict[str, Any]],
    ) -> int:
        """Send task completion notification."""
        return await self.broadcast_to_channel(
            f"task:{task_id}",
            {
                "type": "task:complete",
                "payload": {
                    "task_id": task_id,
                    "results": results,
                },
            },
        )

    async def send_task_error(
        self,
        task_id: str,
        error: str,
        code: str | None = None,
    ) -> int:
        """Send task error notification."""
        return await self.broadcast_to_channel(
            f"task:{task_id}",
            {
                "type": "task:error",
                "payload": {
                    "task_id": task_id,
                    "error": error,
                    "code": code,
                },
            },
        )

    # ============ Generation Progress ============

    async def send_generate_progress(
        self,
        user_id: str,
        request_id: str,
        stage: str,
        progress: float | None = None,
    ) -> int:
        """Send generation progress update to user."""
        return await self.send_to_user(
            user_id,
            {
                "type": "generate:progress",
                "payload": {
                    "request_id": request_id,
                    "stage": stage,
                    "progress": progress,
                },
            },
        )

    async def send_generate_complete(
        self,
        user_id: str,
        request_id: str,
        image_id: str,
        url: str,
        prompt: str,
        provider: str,
        duration_ms: int,
    ) -> int:
        """Send generation completion notification."""
        return await self.send_to_user(
            user_id,
            {
                "type": "generate:complete",
                "payload": {
                    "request_id": request_id,
                    "image_id": image_id,
                    "url": url,
                    "prompt": prompt,
                    "provider": provider,
                    "duration_ms": duration_ms,
                },
            },
        )

    # ============ Notifications ============

    async def send_notification(
        self,
        user_id: str,
        notification_id: str,
        type: str,
        title: str,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> int:
        """Send a notification to a user."""
        return await self.send_to_user(
            user_id,
            {
                "type": "notification",
                "payload": {
                    "id": notification_id,
                    "type": type,
                    "title": title,
                    "message": message,
                    "data": data or {},
                },
            },
        )

    async def send_quota_warning(
        self,
        user_id: str,
        remaining: int,
        limit: int,
        resets_at: datetime | None = None,
    ) -> int:
        """Send quota warning to user."""
        return await self.send_to_user(
            user_id,
            {
                "type": "quota:warning",
                "payload": {
                    "remaining": remaining,
                    "limit": limit,
                    "resets_at": resets_at.isoformat() if resets_at else None,
                },
            },
        )


# Singleton instance
_ws_manager: WebSocketManager | None = None


def get_websocket_manager() -> WebSocketManager:
    """Get the WebSocket manager singleton."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
