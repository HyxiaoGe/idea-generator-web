"""
Background task for chat message processing.

Runs the ChatSession.send_message call outside the HTTP request context
so the endpoint can return a task_id immediately. Modelled after image_task.py.

# TODO: migrate to ARQ for production reliability
"""

import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime

from PIL import Image

from api.schemas.generate import GeneratedImage
from core.redis import get_redis
from database import get_session, is_database_available
from database.repositories import ChatRepository, QuotaRepository

from . import ChatSession, get_friendly_error_message, get_quota_service, get_storage_manager
from .websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


async def execute_chat_task(
    task_id: str,
    session_id: str,
    user_id: str,
    message: str,
    aspect_ratio: str | None,
    safety_level: str,
    enable_thinking: bool,
    api_key: str,
    session_data_json: str,
) -> None:
    """Background task entry point for chat send_message.

    Runs outside FastAPI request context — all services are manually acquired.

    Args:
        task_id: Unique task ID (chat_* prefix).
        session_id: Chat session ID.
        user_id: User ID for quota/storage/websocket.
        message: User message text.
        aspect_ratio: Optional aspect ratio override.
        safety_level: Safety filter level.
        enable_thinking: Whether to enable model thinking.
        api_key: Google API key to use.
        session_data_json: JSON-serialized session data (snapshot at request time).
    """
    redis = await get_redis()
    task_key = f"task:{task_id}"
    ws_manager = get_websocket_manager()

    try:
        session_data = json.loads(session_data_json)
        history_messages = session_data["messages"]

        # 1. Update status → generating
        now = datetime.now().isoformat()
        await redis.hset(
            task_key,
            mapping={
                "status": "generating",
                "stage": "loading_history",
                "progress": "0.1",
                "started_at": now,
            },
        )

        # 2. Load recent history images
        try:
            await ws_manager.send_chat_progress(user_id, session_id, stage="loading_history")
        except Exception:
            pass

        history_images: dict[str, Image.Image] = {}
        history_signatures: dict[str, bytes] = {}
        image_cutoff = max(0, len(history_messages) - ChatSession.IMAGE_HISTORY_TURNS * 2)

        storage = get_storage_manager(user_id=user_id if user_id != "anonymous" else None)
        image_keys_to_load = [
            msg.get("image_key") for msg in history_messages[image_cutoff:] if msg.get("image_key")
        ]

        if image_keys_to_load:
            load_tasks = [storage.load_image(key) for key in image_keys_to_load]
            loaded = await asyncio.gather(*load_tasks, return_exceptions=True)
            for key, img in zip(image_keys_to_load, loaded, strict=True):
                if isinstance(img, Image.Image):
                    history_images[key] = img

        # 3. Load thought_signatures
        for msg in history_messages[image_cutoff:]:
            image_key = msg.get("image_key")
            sig_b64 = msg.get("thought_signature")
            if image_key and sig_b64:
                history_signatures[image_key] = base64.b64decode(sig_b64)

        # 4. Send message (sync SDK call offloaded to thread)
        await redis.hset(task_key, mapping={"stage": "thinking", "progress": "0.3"})
        try:
            await ws_manager.send_chat_progress(user_id, session_id, stage="thinking")
        except Exception:
            pass

        chat_session = ChatSession(api_key=api_key)
        chat_session.aspect_ratio = session_data["aspect_ratio"]

        response = await asyncio.to_thread(
            chat_session.send_message,
            message=message,
            history=history_messages,
            history_images=history_images,
            history_signatures=history_signatures if history_signatures else None,
            aspect_ratio=aspect_ratio,
            safety_level=safety_level,
            enable_thinking=enable_thinking,
        )

        # 5. Handle error
        if response.error:
            logger.error(
                "Chat generation error (task=%s, session=%s): %s",
                task_id,
                session_id,
                response.error,
            )
            await redis.hset(
                task_key,
                mapping={
                    "status": "failed",
                    "error": get_friendly_error_message(response.error),
                    "error_code": "generation_error",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            try:
                await ws_manager.send_chat_error(
                    user_id, session_id, error=response.error, code="generation_error"
                )
            except Exception:
                pass
            # Refund quota
            quota_svc = get_quota_service(redis)
            await quota_svc.refund_quota(user_id, 1)
            return

        # 6. Save image if generated
        await redis.hset(task_key, mapping={"stage": "saving", "progress": "0.7"})
        image_data = None
        if response.image:
            try:
                await ws_manager.send_chat_progress(user_id, session_id, stage="saving")
            except Exception:
                pass

            result = await storage.save_image(
                image=response.image,
                prompt=message,
                settings={
                    "aspect_ratio": aspect_ratio or session_data["aspect_ratio"],
                },
                duration=response.duration,
                mode="chat",
                text_response=response.text,
                thinking=response.thinking,
            )

            if result:
                image_data = GeneratedImage(
                    key=result.key,
                    filename=result.filename,
                    url=result.public_url,
                    width=response.image.width,
                    height=response.image.height,
                )

        # 7. Persist messages to DB
        session_uuid = uuid.UUID(session_id)
        message_count = 0
        if is_database_available():
            try:
                async for db_session in get_session():
                    chat_repo = ChatRepository(db_session)
                    await chat_repo.create_message(
                        session_id=session_uuid,
                        role="user",
                        content=message,
                    )
                    await chat_repo.create_message(
                        session_id=session_uuid,
                        role="assistant",
                        content=response.text or "",
                        image_url=image_data.key if image_data else None,
                        thinking=response.thinking,
                        thought_signature=response.thought_signature,
                    )
                    if image_data:
                        await chat_repo.update_session_latest_image(
                            session_uuid, image_data.url or image_data.key
                        )
                    message_count = await chat_repo.count_messages_by_session(session_uuid)
            except Exception as e:
                logger.warning("Failed to persist chat messages to database: %s", e)

        if message_count == 0:
            # Fallback: estimate from snapshot if DB write failed
            message_count = len(history_messages) + 2

        # 8. Record quota usage
        if is_database_available():
            try:
                async for db_session in get_session():
                    quota_repo = QuotaRepository(db_session)
                    await quota_repo.record_usage(
                        mode="chat",
                        points_used=1,
                        provider="google",
                        media_type="image",
                    )
            except Exception as e:
                logger.warning("Failed to record quota usage to database: %s", e)

        # 9. Build result and finalize
        from api.schemas.chat import SendMessageResponse

        result_obj = SendMessageResponse(
            text=response.text,
            image=image_data,
            thinking=response.thinking,
            duration=response.duration,
            message_count=message_count,
        )
        result_json = result_obj.model_dump_json()

        await redis.hset(
            task_key,
            mapping={
                "status": "completed",
                "progress": "1.0",
                "result_json": result_json,
                "completed_at": datetime.now().isoformat(),
            },
        )

        # 10. WS chat:complete with full result
        elapsed = response.duration
        try:
            await ws_manager.send_chat_complete(
                user_id,
                session_id,
                has_image=image_data is not None,
                duration=round(elapsed, 2),
                message_count=message_count,
                result=result_obj.model_dump(mode="json"),
            )
        except Exception:
            pass

    except Exception:
        logger.exception("Unhandled error in chat task %s (session=%s)", task_id, session_id)
        try:
            await redis.hset(
                task_key,
                mapping={
                    "status": "failed",
                    "error": "Internal server error",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            await ws_manager.send_chat_error(user_id, session_id, error="Internal server error")
            # Refund quota on unexpected failure
            quota_svc = get_quota_service(redis)
            await quota_svc.refund_quota(user_id, 1)
        except Exception:
            logger.exception("Failed to update task status after error for %s", task_id)
