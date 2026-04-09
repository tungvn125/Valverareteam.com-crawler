import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.db import DatabaseManager
from vvr_scraper.job_worker import JobWorker

# We import auto_sync_background_task here, but it doesn't exist yet, so this will fail.
# However, for TDD, we can mock it or wait until we define it.
# Let's write the test assuming it will be in vvr_scraper.web


@pytest.mark.asyncio
async def test_auto_sync_logic():
    # Setup mock DB and Worker
    db = MagicMock(spec=DatabaseManager)
    worker = MagicMock(spec=JobWorker)

    # Mock VVR_AUTO_SYNC environment variable
    with patch.dict(os.environ, {"VVR_AUTO_SYNC": "1"}):
        # We need to import it inside the patch or after it's defined
        from vvr_scraper.web import auto_sync_background_task

        # Mock check_library_updates to do nothing
        with patch("vvr_scraper.web.routes.library.check_library_updates", new_callable=AsyncMock) as mock_check:
            # Mock db.get_all_novels to return one novel with updates
            db.get_all_novels = AsyncMock(
                return_value=[
                    {
                        "slug": "test-novel",
                        "title": "Test Novel",
                        "has_updates": 1,
                        "formats": "epub,pdf",
                        "last_synced_count": 10,
                    }
                ]
            )

            # Mock worker.enqueue_job
            worker.enqueue_job = AsyncMock()
            # Mock db.create_job
            db.create_job = AsyncMock(return_value="mock-job-id")

            # Create a task to run the background loop briefly
            # Mock asyncio.sleep to raise CancelledError to break loop after one iteration
            with patch("asyncio.sleep", side_effect=[asyncio.CancelledError]):
                try:
                    await auto_sync_background_task(db, worker)
                except asyncio.CancelledError:
                    pass

            # Verify check_library_updates was called
            mock_check.assert_called_once()

            # Verify job was created and enqueued
            db.create_job.assert_called_once()
            worker.enqueue_job.assert_called_once()

            # Check payload
            args, kwargs = worker.enqueue_job.call_args
            job_id, job_obj = args
            assert job_id == "mock-job-id"
            assert job_obj.task == "crawl"
            assert job_obj.payload.slug == "test-novel"
            assert "epub" in job_obj.payload.formats
            assert "pdf" in job_obj.payload.formats


@pytest.mark.asyncio
async def test_auto_sync_disabled():
    db = MagicMock(spec=DatabaseManager)
    worker = MagicMock(spec=JobWorker)

    with patch.dict(os.environ, {"VVR_AUTO_SYNC": "0"}):
        from vvr_scraper.web import auto_sync_background_task

        with patch("vvr_scraper.web.routes.library.check_library_updates", new_callable=AsyncMock) as mock_check:
            db.get_all_novels = AsyncMock(return_value=[{"slug": "test", "has_updates": 1}])

            with patch("asyncio.sleep", side_effect=[asyncio.CancelledError]):
                try:
                    await auto_sync_background_task(db, worker)
                except asyncio.CancelledError:
                    pass

            # Verify check_library_updates was NOT called
            mock_check.assert_not_called()
            worker.enqueue_job.assert_not_called()
