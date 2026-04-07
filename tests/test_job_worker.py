import pytest
import asyncio
from vvr_scraper.job_worker import JobWorker
from vvr_scraper.job_models import ScrapeJob, ScrapePayload

@pytest.mark.asyncio
async def test_job_worker_basic():
    worker = JobWorker(None) # Pass None for db for now
    job = ScrapeJob(payload=ScrapePayload(slug="test-slug", formats=["epub"]))
    await worker.enqueue_job(1, job) # Using (id, job)
    assert worker.queue.qsize() == 1
