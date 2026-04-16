"""
Job management API routes — CRUD for the Universal Task Runner.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

import vvr_scraper.web.state as state

from ...job_models import JobManifest
from ..deps import get_db
from ..state import active_tasks, active_tasks_futures, task_log_buffers

# Backward-compatible alias for tests/patches that target module-level `worker`
worker = state.worker

router = APIRouter(prefix="/api", tags=["Jobs"])


@router.get("/jobs")
async def list_jobs():
    """Returns the 50 most recent jobs from the database."""
    try:
        db = get_db()
        jobs = await db.get_recent_jobs(limit=50)
        return jobs
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/jobs/{job_id}")
async def get_job_detail(job_id: str):
    """Returns detailed information for a specific job."""
    db = get_db()
    job = await db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.post("/jobs")
async def submit_job(job_manifest: JobManifest):
    """Submits jobs from a manifest to the task runner queue."""

    if worker is None:
        raise HTTPException(status_code=503, detail="JobWorker not initialized")

    try:
        from datetime import datetime

        from ...job_parser import parse_manifest

        db = get_db()

        # 1. Parse and validate dependencies (Topological Sort)
        jobs = parse_manifest(job_manifest)

        alias_to_uuid = {}
        batch_id = f"batch_web_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        submitted_ids = []

        for job in jobs:
            # Resolve depends_on (map alias_id to UUID)
            resolved_deps = []
            if job.depends_on:
                for dep in job.depends_on:
                    if dep in alias_to_uuid:
                        resolved_deps.append(alias_to_uuid[dep])
                    else:
                        resolved_deps.append(dep)

            # 2. Save to DB
            job_id = await db.create_job(
                task_type=job.task,
                payload=JobManifest(root=job).model_dump_json(),
                alias_id=job.alias_id,
                batch_id=job.batch_id or batch_id,
                depends_on=",".join(resolved_deps) if resolved_deps else None,
                priority=job.priority,
                from_chapter=getattr(job.payload, "from_chapter", None),
                to_chapter=getattr(job.payload, "to_chapter", None),
            )

            if job.alias_id:
                alias_to_uuid[job.alias_id] = job_id

            # 3. Enqueue to Worker
            await worker.enqueue_job(job_id, JobManifest(root=job))
            submitted_ids.append(job_id)

        return {"status": "queued", "job_ids": submitted_ids, "batch_id": batch_id}
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str):
    return task_log_buffers.get(task_id, [])


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    if task_id in active_tasks_futures:
        active_tasks_futures[task_id].cancel()
        return {"status": "pausing"}
    return {"status": "not_running"}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    from ..state import download_queue

    if task_id in active_tasks:
        req = active_tasks[task_id]
        await download_queue.add_task(req, task_id)
        return {"status": "resuming"}
    return {"status": "task_not_found", "error": "Task request not found in active_tasks. Cannot resume."}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if task_id in active_tasks_futures:
        active_tasks_futures[task_id].cancel()
    if task_id in active_tasks:
        del active_tasks[task_id]
    if task_id in task_log_buffers:
        del task_log_buffers[task_id]
    return {"status": "cancelled"}
