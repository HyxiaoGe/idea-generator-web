"""
WebSocket router for real-time updates.

Endpoint:
- WS /api/ws - WebSocket connection
"""

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from core.auth import _to_app_user, get_validator
from services.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def authenticate_websocket(token: str | None) -> tuple[str | None, str | None]:
    """
    Authenticate a WebSocket connection.

    Returns (user_id, error_message).
    """
    if not token:
        return None, None  # Anonymous connection allowed

    try:
        validator = get_validator()
        auth_user = await validator.verify_async(token)
        app_user = _to_app_user(auth_user)
        return app_user.user_folder_id, None
    except Exception as e:
        logger.warning(f"WebSocket auth error: {e}")
        return None, str(e)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
):
    """
    WebSocket endpoint for real-time updates.

    Authentication:
    - Pass JWT token as query parameter: /api/ws?token=xxx
    - Anonymous connections are allowed but with limited functionality

    Message Protocol:
    - Client sends JSON messages with "type" and "payload" fields
    - Server responds with JSON messages with "type", "payload", and "timestamp" fields

    Client -> Server Messages:
    - {"type": "ping"} - Heartbeat
    - {"type": "subscribe", "payload": {"channel": "task", "task_id": "xxx"}}
    - {"type": "unsubscribe", "payload": {"channel": "task", "task_id": "xxx"}}

    Server -> Client Messages:
    - {"type": "connected", "payload": {"connection_id": "...", "user_id": "..."}}
    - {"type": "pong", "payload": {"server_time": 1234567890}}
    - {"type": "task:progress", "payload": {...}}
    - {"type": "task:complete", "payload": {...}}
    - {"type": "notification", "payload": {...}}
    - {"type": "quota:warning", "payload": {...}}
    """
    ws_manager = get_websocket_manager()

    # Authenticate
    user_id, auth_error = await authenticate_websocket(token)
    if auth_error:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "payload": {
                    "code": "auth_error",
                    "message": auth_error,
                },
            }
        )
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Connect
    connection_id = await ws_manager.connect(websocket, user_id)

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await ws_manager.send_to_connection(
                    connection_id,
                    {
                        "type": "error",
                        "payload": {
                            "code": "invalid_json",
                            "message": "Invalid JSON message",
                        },
                    },
                )
                continue

            # Handle message
            await ws_manager.handle_message(connection_id, message)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await ws_manager.disconnect(connection_id)
