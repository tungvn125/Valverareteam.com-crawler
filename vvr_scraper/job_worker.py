import asyncio
import json
import os
import traceback
from datetime import datetime

from loguru import logger

from vvr_scraper.db import DatabaseManager
from vvr_scraper.job_models import JobManifest

from .enums import JobStatus


class JobWorker:
    def __init__(self, db_manager: DatabaseManager | None):
        self.queue = asyncio.PriorityQueue(maxsize=100)
        self.db = db_manager
        self._loop_task = None
        self.crawl_semaphore = asyncio.Semaphore(3)
        self.heavy_semaphore = asyncio.Semaphore(1)

    async def enqueue_job(self, job_id: str, job: JobManifest):
        # Access priority from the root job object
        priority = getattr(job.root, "priority", 3)
        # PriorityQueue expects (priority, job_id, job)
        await self.queue.put((priority, job_id, job))
        logger.info(f"Enqueued job {job_id}: {job.task} with priority {priority}")

    async def start(self):
        if self._loop_task is None:
            # Persistence Recovery
            if self.db:
                await self.recover_jobs()

            self._loop_task = asyncio.create_task(self.worker_loop())
            logger.info("JobWorker started.")

    async def recover_jobs(self):
        """Recovers pending/waiting jobs and marks running jobs as failed."""
        if not self.db:
            return

        db = await self.db.get_db()

        # 1. Mark 'running' jobs as failed
        try:
            async with db.execute("SELECT id FROM jobs WHERE status = ?", (JobStatus.RUNNING.value,)) as cursor:
                running_jobs = await cursor.fetchall()
                for row in running_jobs:
                    job_id = row[0] if not hasattr(row, "keys") else row["id"]
                    await self.db.update_job_status(job_id, JobStatus.FAILED, error_summary="Hệ thống bị ngắt quãng")
                    logger.warning(f"Marked running job {job_id} as failed due to restart.")
                    # Also cancel its dependents recursively
                    await self.cancel_dependents(job_id)
        except Exception as e:
            logger.error(f"Error recovering running jobs: {e}")

        # 2. Re-enqueue 'pending' and 'waiting' jobs
        try:
            async with db.execute("SELECT * FROM jobs WHERE status IN (?, ?)", (JobStatus.PENDING.value, JobStatus.WAITING.value)) as cursor:
                pending_rows = await cursor.fetchall()
                for row in pending_rows:
                    row_dict = dict(row) if hasattr(row, "keys") else None
                    # Fallback for tuple rows if row_factory is not sqlite3.Row
                    if row_dict is None:
                        # Assuming schema: id, task_type, status, payload, progress, error_summary, error_log_path, created_at, updated_at, alias_id, batch_id, depends_on, priority, from_chapter, to_chapter
                        # This is risky, but we try to be robust.
                        # Usually our DatabaseManager sets row_factory = aiosqlite.Row
                        pass

                    if not row_dict:
                        continue

                    job_id = row_dict["id"]
                    try:
                        payload_dict = json.loads(row_dict["payload"])
                        # Use JobManifest to validate full job object (backward compatible)
                        if "task" not in payload_dict and "root" not in payload_dict:
                            from vvr_scraper.job_models import ScrapeJob, ScrapePayload

                            # Restore depends_on from DB (comma-separated string → list)
                            depends_on_raw = row_dict.get("depends_on")
                            depends_on_list = depends_on_raw.split(",") if depends_on_raw else None

                            job_data = ScrapeJob(
                                payload=ScrapePayload.model_validate(payload_dict),
                                priority=row_dict.get("priority") or 3,
                                alias_id=row_dict.get("alias_id"),
                                batch_id=row_dict.get("batch_id"),
                                depends_on=depends_on_list,
                            )
                            job_obj = JobManifest(root=job_data)
                        else:
                            job_obj = JobManifest.model_validate(payload_dict)

                        await self.enqueue_job(job_id, job_obj)
                    except Exception as e:
                        logger.error(f"Failed to recover job {job_id}: {e}")
        except Exception as e:
            logger.error(f"Error recovering pending jobs: {e}")

    async def stop(self):
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
            logger.info("JobWorker stopped.")

    async def worker_loop(self):
        while True:
            try:
                priority, job_id, job = await self.queue.get()

                # Dependency Check: If job has dependencies, check their status first
                if job.root.depends_on:
                    all_success = True
                    for dep_uuid in job.root.depends_on:
                        dep_status = await self.db.get_job_status(dep_uuid)
                        if not dep_status or dep_status["status"] != JobStatus.SUCCESS:
                            all_success = False
                            if dep_status and dep_status["status"] in (JobStatus.FAILED, JobStatus.CANCELLED):
                                await self.db.update_job_status(
                                    job_id, JobStatus.CANCELLED, error_summary=f"Dependency {dep_uuid} failed/cancelled"
                                )
                                await self.cancel_dependents(job_id)
                                break

                    if not all_success:
                        # Check current status to avoid infinite loop if cancelled above
                        current_job = await self.db.get_job_status(job_id)
                        if current_job and current_job["status"] not in (JobStatus.CANCELLED, JobStatus.FAILED):
                            await self.db.update_job_status(job_id, JobStatus.WAITING)
                            # Put back to queue after a short delay
                            await asyncio.sleep(5)
                            await self.queue.put((priority, job_id, job))
                        self.queue.task_done()
                        continue

                # Run job with semaphore in a background task to allow concurrency
                asyncio.create_task(self.run_job_with_resource_control(job_id, job))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop encountered unexpected error: {e}")

    async def run_job_with_resource_control(self, job_id: str, job: JobManifest):
        """Executes a job while respecting resource limits (semaphores)."""
        is_heavy = False
        if job.task == "render":
            is_heavy = True
        elif job.task == "crawl":
            payload = job.payload
            formats = getattr(payload, "formats", [])
            if formats:
                # Normalize formats to lower case for comparison
                lower_formats = [f.lower() for f in formats]
                if any(f in lower_formats for f in ["ad-mp3", "mp4", "cinema"]):
                    is_heavy = True

        sem = self.heavy_semaphore if is_heavy else self.crawl_semaphore

        async with sem:
            try:
                await self.execute_job(job_id, job)
            except Exception as e:
                logger.error(f"Error in job {job_id} execution: {e}")
            finally:
                self.queue.task_done()

    async def execute_job(self, job_id: str, job: JobManifest):
        """Dispatches the job to the appropriate executor."""
        logger.info(f"Executing job {job_id}: {job.task}")

        # Update status to running
        if self.db:
            await self.db.update_job_status(job_id, JobStatus.RUNNING, progress=0.0)

        try:
            if job.task == "crawl":
                from vvr_scraper.job_runner import execute_crawl_job

                await execute_crawl_job(job.payload, job_id, self.db)
            elif job.task == "render":
                from vvr_scraper.job_runner import execute_render_job

                await execute_render_job(job.payload, job_id, self.db)
            elif job.task == "server":
                # Server is special as it might run forever
                from vvr_scraper.job_runner import start_server_from_job

                await start_server_from_job(job.payload)

            if self.db:
                await self.db.update_job_status(job_id, JobStatus.SUCCESS, progress=100.0)
            logger.success(f"Job {job_id} completed successfully.")

        except Exception as e:
            logger.error(f"Error executing job {job_id}: {e}")
            await self.handle_job_error(job_id, job, e)

    async def handle_job_error(self, job_id: str, job: JobManifest, exc: Exception):
        """Creates an error log file and updates the database."""
        error_dir = "error-logs"
        os.makedirs(error_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"job_{job_id}_{timestamp}.log"
        log_path = os.path.join(error_dir, log_filename)

        stack_trace = traceback.format_exc()

        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("=== JOB MANIFEST ===\n")
                f.write(job.model_dump_json(indent=2))
                f.write("\n\n=== STACK TRACE ===\n")
                f.write(stack_trace)

            logger.info(f"Detailed error log saved to: {log_path}")

            if self.db:
                await self.db.update_job_status(job_id, JobStatus.FAILED, error_summary=str(exc), error_log_path=log_path)
                # Recursive Cancellation
                await self.cancel_dependents(job_id)
        except Exception as e:
            logger.error(f"Failed to write error log for job {job_id}: {e}")

    async def cancel_dependents(self, failed_job_id: str):
        """Recursively cancels all jobs that depend on the failed job."""
        if not self.db:
            return

        db = await self.db.get_db()
        # Find jobs where depends_on contains failed_job_id
        # Use SQLite string concatenation to ensure exact match in comma-separated list
        query = "SELECT id FROM jobs WHERE ',' || depends_on || ',' LIKE ?"
        pattern = f"%,{failed_job_id},%"

        try:
            async with db.execute(query, (pattern,)) as cursor:
                dependents = await cursor.fetchall()
                for row in dependents:
                    dep_id = row[0] if not hasattr(row, "keys") else row["id"]
                    await self.db.update_job_status(
                        dep_id, JobStatus.CANCELLED, error_summary=f"Phụ thuộc vào job {failed_job_id} bị lỗi"
                    )
                    logger.warning(f"Cancelled job {dep_id} because it depends on failed job {failed_job_id}")
                    # Recursive call
                    await self.cancel_dependents(dep_id)
        except Exception as e:
            logger.error(f"Error during recursive cancellation for job {failed_job_id}: {e}")
