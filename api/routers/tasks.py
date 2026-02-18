"""
Task management router.

Endpoints:
- POST /api/tasks/{task_id}/cancel - Cancel a running task and refund quota
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends

from api.schemas.tasks import TaskCancelResponse
from core.auth import AppUser, get_current_user
from core.exceptions import TaskNotFoundError, ValidationError
from core.redis import get_redis
from services import get_quota_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _get_user_id(user: AppUser | None) -> str:
    if user:
        return user.user_folder_id
    return "anonymous"


@router.post("/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(
    task_id: str,
    user: AppUser | None = Depends(get_current_user),
):
    """
    Cancel a running batch or video task and refund unused quota.

    Returns the number of quota points refunded.
    """
    user_id = _get_user_id(user)
    redis = await get_redis()

    # --- Try batch task (hash at task:{task_id}) ---
    batch_key = f"task:{task_id}"
    batch_data = await redis.hgetall(batch_key)

    if batch_data:
        task_user = batch_data.get("user_id", "")
        if task_user != user_id:
            raise ValidationError(message="You can only cancel your own tasks")

        status = batch_data.get("status", "unknown")
        if status in TERMINAL_STATUSES:
            raise ValidationError(
                message=f"Task is already {status} and cannot be cancelled",
                details={"task_id": task_id, "status": status},
            )

        total = int(batch_data.get("total", 0))
        progress = int(batch_data.get("progress", 0))
        pending_count = max(0, total - progress)

        # Set cancelled flag for the background loop to pick up
        await redis.hset(batch_key, "cancelled", "1")

        # Refund quota for pending items
        refunded = 0
        if pending_count > 0:
            quota_service = get_quota_service(redis)
            refunded = await quota_service.refund_quota(user_id, pending_count)

        return TaskCancelResponse(
            task_id=task_id,
            task_type="batch",
            previous_status=status,
            refunded_count=refunded,
            message=f"Task cancelled. {refunded} quota point(s) refunded.",
        )

    # --- Try video task (JSON string at video_task:{task_id}) ---
    video_key = f"video_task:{task_id}"
    video_json = await redis.get(video_key)

    if video_json:
        video_data = json.loads(video_json)
        task_user = video_data.get("user_id", "")
        if task_user != user_id:
            raise ValidationError(message="You can only cancel your own tasks")

        status = video_data.get("status", "unknown")
        if status in TERMINAL_STATUSES:
            raise ValidationError(
                message=f"Task is already {status} and cannot be cancelled",
                details={"task_id": task_id, "status": status},
            )

        # Update status to cancelled
        video_data["status"] = "cancelled"
        video_data["completed_at"] = datetime.now().isoformat()
        await redis.setex(video_key, 3600 * 24, json.dumps(video_data))

        # Refund 1 point if task was queued or processing
        refunded = 0
        if status in {"queued", "processing"}:
            quota_service = get_quota_service(redis)
            refunded = await quota_service.refund_quota(user_id, 1)

        return TaskCancelResponse(
            task_id=task_id,
            task_type="video",
            previous_status=status,
            refunded_count=refunded,
            message=f"Task cancelled. {refunded} quota point(s) refunded.",
        )

    # --- Neither found ---
    raise TaskNotFoundError()
