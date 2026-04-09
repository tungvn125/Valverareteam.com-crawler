import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.job_models import JobManifest, RenderJob, RenderPayload, ScrapeJob, ScrapePayload
from vvr_scraper.job_worker import JobWorker


class MockCursor:
    def __init__(self, fetchall_value=None):
        self.fetchall = AsyncMock(return_value=fetchall_value or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def __await__(self):
        async def _f():
            return self

        return _f().__await__()


@pytest.mark.asyncio
async def test_job_priority_queue_order():
    db = AsyncMock()
    worker = JobWorker(db)
    worker.heavy_semaphore = asyncio.Semaphore(1)
    worker.crawl_semaphore = asyncio.Semaphore(1)

    executed_order = []

    async def mock_execute(job_id, job):
        executed_order.append(job_id)
        await asyncio.sleep(0.01)

    with patch.object(worker, "execute_job", side_effect=mock_execute):
        job3 = JobManifest(root=ScrapeJob(payload=ScrapePayload(slug="crawl", formats=["epub"]), priority=3))
        job2 = JobManifest(root=ScrapeJob(payload=ScrapePayload(slug="audio", formats=["epub"]), priority=2))
        job1 = JobManifest(root=RenderJob(payload=RenderPayload(manifest_path="m", output_path="o"), priority=1))

        await worker.enqueue_job("job3", job3)
        await worker.enqueue_job("job2", job2)
        await worker.enqueue_job("job1", job1)

        task = asyncio.create_task(worker.worker_loop())
        await asyncio.sleep(0.2)
        task.cancel()

        assert executed_order == ["job1", "job2", "job3"]


@pytest.mark.asyncio
async def test_job_worker_semaphores():
    db = AsyncMock()
    worker = JobWorker(db)

    running_heavy = 0
    max_running_heavy = 0
    running_crawl = 0
    max_running_crawl = 0

    async def mock_execute(job_id, job):
        nonlocal running_heavy, max_running_heavy, running_crawl, max_running_crawl
        is_heavy = job.task == "render" or "ad-mp3" in (getattr(job.payload, "formats", []) or [])
        if is_heavy:
            running_heavy += 1
            max_running_heavy = max(max_running_heavy, running_heavy)
        else:
            running_crawl += 1
            max_running_crawl = max(max_running_crawl, running_crawl)
        await asyncio.sleep(0.05)
        if is_heavy:
            running_heavy -= 1
        else:
            running_crawl -= 1

    with patch.object(worker, "execute_job", side_effect=mock_execute):
        job_h1 = JobManifest(root=RenderJob(payload=RenderPayload(manifest_path="m1", output_path="o1"), priority=1))
        job_h2 = JobManifest(root=RenderJob(payload=RenderPayload(manifest_path="m2", output_path="o2"), priority=1))
        crawl_jobs = [
            JobManifest(root=ScrapeJob(payload=ScrapePayload(slug=f"c{i}", formats=["epub"]), priority=3))
            for i in range(5)
        ]
        await worker.enqueue_job("h1", job_h1)
        await worker.enqueue_job("h2", job_h2)
        for i, cj in enumerate(crawl_jobs):
            await worker.enqueue_job(f"c{i}", cj)
        task = asyncio.create_task(worker.worker_loop())
        await asyncio.sleep(0.5)
        task.cancel()
        assert max_running_heavy <= 1
        assert max_running_crawl <= 3


@pytest.mark.asyncio
async def test_job_worker_recovery():
    db = AsyncMock()
    pending_jobs = [
        {
            "id": "p1",
            "task_type": "crawl",
            "payload": '{"slug": "p1", "formats": ["epub"]}',
            "priority": 3,
            "alias_id": "alias_p1",
            "batch_id": "batch_1",
            "depends_on": "dep1,dep2",
        },
    ]
    running_jobs = [
        {"id": "r1", "task_type": "render", "payload": '{"manifest_path": "m", "output_path": "o"}', "priority": 1},
    ]

    db.get_db = AsyncMock()
    mock_conn = AsyncMock()
    db.get_db.return_value = mock_conn

    def mock_execute(query, *args):
        if "IN ('pending', 'waiting')" in query:
            return MockCursor(pending_jobs)
        if "status = 'running'" in query:
            return MockCursor(running_jobs)
        return MockCursor()

    # Use MagicMock for execute so it returns the MockCursor object directly
    mock_conn.execute = MagicMock(side_effect=mock_execute)
    worker = JobWorker(db)

    with patch.object(worker, "worker_loop", return_value=asyncio.sleep(0)):
        await worker.start()

    db.update_job_status.assert_any_call("r1", "failed", error_summary="Hệ thống bị ngắt quãng")
    assert worker.queue.qsize() == 1
    priority, job_id, job = await worker.queue.get()
    assert job_id == "p1"
    assert priority == 3
    assert job.root.alias_id == "alias_p1"
    assert job.root.depends_on == ["dep1", "dep2"]


@pytest.mark.asyncio
async def test_recursive_cancellation():
    db = AsyncMock()
    worker = JobWorker(db)
    dependents = {"%,job1,%": [{"id": "job2"}], "%,job2,%": [{"id": "job3"}], "%,job3,%": []}

    def mock_execute(query, params=None):
        if query and "FROM jobs WHERE ',' || depends_on || ',' LIKE ?" in query:
            pattern = params[0]
            return MockCursor(dependents.get(pattern, []))
        return MockCursor()

    mock_conn = AsyncMock()
    # Use MagicMock for execute
    mock_conn.execute = MagicMock(side_effect=mock_execute)
    db.get_db.return_value = mock_conn

    await worker.cancel_dependents("job1")

    db.update_job_status.assert_any_call("job2", "cancelled", error_summary="Phụ thuộc vào job job1 bị lỗi")
    db.update_job_status.assert_any_call("job3", "cancelled", error_summary="Phụ thuộc vào job job2 bị lỗi")
