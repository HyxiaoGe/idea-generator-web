"""
Admin background-task management router.

Endpoints:
- POST /api/admin/tasks/generate-previews — Enqueue preview image generation
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.auth import AppUser, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["admin-tasks"])


@router.post("/generate-previews")
async def trigger_generate_previews(
    request: Request,
    admin: AppUser = Depends(require_admin),
    delay: float = Query(5.0, ge=1.0, le=60.0, description="Seconds between API requests"),
    batch_size: int = Query(0, ge=0, description="Max templates to process (0 = all)"),
):
    """Manually trigger preview image generation for templates missing previews.

    Enqueues the task on the ARQ worker. Returns the job ID for tracking.
    """
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        raise HTTPException(
            status_code=503,
            detail="ARQ task queue not available. Is the worker running?",
        )

    job = await arq_pool.enqueue_job(
        "generate_template_previews",
        delay=delay,
        batch_size=batch_size,
    )

    logger.info(
        "Admin %s triggered preview generation (delay=%.1f, batch_size=%d) -> job %s",
        admin.sub,
        delay,
        batch_size,
        job.job_id,
    )

    return {
        "job_id": job.job_id,
        "status": "enqueued",
        "params": {"delay": delay, "batch_size": batch_size},
    }
