import asyncio
import traceback
import os
import json
from datetime import datetime
from typing import Optional, Tuple
from loguru import logger
from vvr_scraper.job_models import JobManifest
from vvr_scraper.db import DatabaseManager

class JobWorker:
    def __init__(self, db_manager: Optional[DatabaseManager]):
        self.queue = asyncio.Queue(maxsize=100)
        self.db = db_manager
        self._loop_task = None

    async def enqueue_job(self, job_id: int, job: JobManifest):
        await self.queue.put((job_id, job))
        logger.info(f"Enqueued job {job_id}: {job.task}")

    async def start(self):
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self.worker_loop())
            logger.info("JobWorker started.")

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
                job_id, job = await self.queue.get()
                try:
                    await self.execute_job(job_id, job)
                except Exception as e:
                    # execute_job already handles its own errors, 
                    # this is for unexpected failures outside execute_job
                    logger.error(f"Worker loop catch-all for job {job_id}: {e}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop encountered unexpected error: {e}")

    async def execute_job(self, job_id: str, job: JobManifest):
        """Dispatches the job to the appropriate executor."""
        logger.info(f"Executing job {job_id}: {job.task}")
        
        # Update status to running
        if self.db:
            await self.db.update_job_status(job_id, "running", progress=0.0)

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
                await self.db.update_job_status(job_id, "success", progress=100.0)
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
                await self.db.update_job_status(
                    job_id, 
                    "failed", 
                    error_summary=str(exc),
                    error_log_path=log_path
                )
        except Exception as e:
            logger.error(f"Failed to write error log for job {job_id}: {e}")
