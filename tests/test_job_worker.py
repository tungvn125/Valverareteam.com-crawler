import pytest

from vvr_scraper.job_models import JobManifest, ScrapeJob, ScrapePayload
from vvr_scraper.job_worker import JobWorker


@pytest.mark.asyncio
async def test_job_worker_basic():
    worker = JobWorker(None)  # Pass None for db for now
    job = JobManifest(root=ScrapeJob(payload=ScrapePayload(slug="test-slug", formats=["epub"])))
    await worker.enqueue_job(1, job)  # Using (id, job)
    assert worker.queue.qsize() == 1


@pytest.mark.asyncio
async def test_job_worker_error_reporting():
    # Need a mock db to capture updates
    class MockDB:
        def __init__(self):
            self.updates = []

        async def update_job_status(self, *args, **kwargs):
            self.updates.append((args, kwargs))

    db = MockDB()
    worker = JobWorker(db)

    job_manifest = ScrapeJob(payload=ScrapePayload(slug="fail", formats=[]))

    # Manually trigger error handler
    try:
        raise ValueError("Simulated failure")
    except Exception as e:
        await worker.handle_job_error(1, job_manifest, e)

    assert len(db.updates) == 1
    # args is db.updates[0][0], kwargs is db.updates[0][1]
    # update_job_status(job_id, status, ...)
    assert db.updates[0][0][1] == "failed"

    # Check if log file exists
    log_path = db.updates[0][1]["error_log_path"]
    import os

    assert os.path.exists(log_path)
    with open(log_path) as f:
        content = f.read()
        assert "JOB MANIFEST" in content
        assert "Simulated failure" in content
        assert "STACK TRACE" in content

    # Cleanup
    if os.path.exists(log_path):
        os.remove(log_path)
