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
                    await self.execute_job(job)
                    if self.db:
                        await self.db.update_job_status(job_id, "completed", progress=100.0)
                except Exception as e:
                    logger.error(f"Error executing job {job_id}: {e}")
                    await self.handle_job_error(job_id, job, e)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop encountered unexpected error: {e}")

    async def execute_job(self, job: JobManifest):
        # Implementation will call actual scrapers/servers
        logger.info(f"Executing job: {job.task} with payload {job.payload}")
        # For now, just a placeholder
        await asyncio.sleep(0.1)

    async def handle_job_error(self, job_id: int, job: JobManifest, exc: Exception):
        # Implementation in Task 3
        pass
