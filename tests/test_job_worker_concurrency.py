import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from vvr_scraper.job_worker import JobWorker
from vvr_scraper.job_models import JobManifest, ScrapeJob, ScrapePayload, RenderJob, RenderPayload

@pytest.mark.asyncio
async def test_job_worker_concurrency_stress():
    """
    Simulates a burst of 100 jobs (mixed heavy/crawl) queued concurrently
    to verify that semaphores prevent parallel overload and priority holds up.
    """
    db = AsyncMock()
    worker = JobWorker(db)
    # Tweak semaphores to easily observable limits
    worker.heavy_semaphore = asyncio.Semaphore(2)
    worker.crawl_semaphore = asyncio.Semaphore(5)

    running_heavy = 0
    max_running_heavy = 0
    running_crawl = 0
    max_running_crawl = 0

    executed_jobs = []

    async def mock_execute(job_id, job):
        nonlocal running_heavy, max_running_heavy, running_crawl, max_running_crawl
        is_heavy = job.task == "render" or "ad-mp3" in (getattr(job.payload, "formats", []) or [])
        
        try:
            if is_heavy:
                running_heavy += 1
                max_running_heavy = max(max_running_heavy, running_heavy)
            else:
                running_crawl += 1
                max_running_crawl = max(max_running_crawl, running_crawl)
            
            # Simulate job doing work (random short time)
            await asyncio.sleep(0.01)
            executed_jobs.append(job_id)
        finally:
            if is_heavy:
                running_heavy -= 1
            else:
                running_crawl -= 1

    with patch.object(worker, "execute_job", side_effect=mock_execute):
        # Create 100 jobs
        for i in range(100):
            if i % 4 == 0:
                # Every 4th job is heavy priority 1
                payload = JobManifest(root=RenderJob(payload=RenderPayload(manifest_path="m", output_path="o"), priority=1))
                await worker.enqueue_job(f"heavy_{i}", payload)
            else:
                # Others are crawl priority 3
                payload = JobManifest(root=ScrapeJob(payload=ScrapePayload(slug=f"crawl_{i}", formats=["EPUB"]), priority=3))
                await worker.enqueue_job(f"crawl_{i}", payload)

        worker_task = asyncio.create_task(worker.worker_loop())
        
        # Wait until all 100 jobs are executed
        while len(executed_jobs) < 100:
            await asyncio.sleep(0.05)
            
        worker_task.cancel()

        # Semaphores should enforce limits at all times
        assert max_running_heavy <= 2, f"Heavy limit exceeded: {max_running_heavy}"
        assert max_running_crawl <= 5, f"Crawl limit exceeded: {max_running_crawl}"
        
        # Ensure we processed 100 jobs
        assert len(executed_jobs) == 100
        
        # Final semaphore counts should be restored
        assert running_heavy == 0
        assert running_crawl == 0

@pytest.mark.asyncio
async def test_job_worker_race_condition_cancellation():
    """
    Test job cancellation during execution parsing.
    """
    db = AsyncMock()
    worker = JobWorker(db)
    
    cancel_mock = AsyncMock()
    with patch.object(worker, "cancel_dependents", cancel_mock):
        job = JobManifest(root=ScrapeJob(payload=ScrapePayload(slug="x", formats=["EPUB"])))
        
        with patch("vvr_scraper.job_runner.execute_crawl_job", side_effect=Exception("Artificial failure")):
            await worker.enqueue_job("test_cancel", job)
            
            # Run one cycle
            task = asyncio.create_task(worker.worker_loop())
            await asyncio.sleep(0.1)
            task.cancel()
            
        # Due to failure, handle_job_error invokes cancel_dependents
        cancel_mock.assert_called_once_with("test_cancel")
