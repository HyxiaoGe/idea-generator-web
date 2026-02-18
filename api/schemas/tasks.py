"""
Schemas for task management endpoints.
"""

from pydantic import BaseModel


class TaskCancelResponse(BaseModel):
    """Response for task cancellation."""

    task_id: str
    task_type: str  # "batch" or "video"
    previous_status: str
    refunded_count: int
    message: str
