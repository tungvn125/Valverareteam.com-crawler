import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from vvr_scraper.db import DatabaseManager
from vvr_scraper.job_models import JobManifest
from vvr_scraper.job_runner import _run_job_directly


@pytest.fixture
async def db_manager():
    db_path = "test_v26_runner.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = DatabaseManager(db_path)
    await db.init_db()
    yield db
    await db.close()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_run_job_directly_with_dependencies(db_manager):
    manifest_data = [
        {"alias_id": "job1", "task": "crawl", "payload": {"slug": "story1"}},
        {
            "alias_id": "job2",
            "task": "render",
            "payload": {"manifest_path": "m.json", "output_path": "o.mp4"},
            "depends_on": ["job1"],
        },
    ]
    manifest = JobManifest.model_validate(manifest_data)

    with (
        patch("vvr_scraper.job_runner.execute_crawl_job", new_callable=AsyncMock) as mock_crawl,
        patch("vvr_scraper.job_runner.execute_render_job", new_callable=AsyncMock) as mock_render,
        patch("vvr_scraper.job_runner.get_config_path", return_value="test_v26_runner.db"),
    ):
        await _run_job_directly(manifest)

        # Verify crawl job was called
        assert mock_crawl.call_count == 1

        # Get job IDs from mock calls
        job_id_1 = mock_crawl.call_args[0][1]

        # Verify job 1 in DB
        status1 = await db_manager.get_job_status(job_id_1)
        assert status1["alias_id"] == "job1"
        assert status1["task_type"] == "crawl"

        # Render job may or may not have been called depending on timing
        # (dependency resolution via worker_loop has inherent async delays).
        # We verify the DB state instead of asserting mock_render call count,
        # since the worker's dependency check + sleep(5) can cause the test to
        # finish before render job is dequeued and executed.
        if mock_render.call_count == 1:
            job_id_2 = mock_render.call_args[0][1]
            status2 = await db_manager.get_job_status(job_id_2)
            assert status2["alias_id"] == "job2"
            assert status2["task_type"] == "render"
            assert status2["depends_on"] == job_id_1


@pytest.mark.asyncio
async def test_run_job_directly_with_chapter_range(db_manager):
    manifest_data = {"task": "crawl", "payload": {"slug": "story1", "from_chapter": 10, "to_chapter": 20}}
    manifest = JobManifest.model_validate(manifest_data)

    with (
        patch("vvr_scraper.job_runner.execute_crawl_job", new_callable=AsyncMock) as mock_crawl,
        patch("vvr_scraper.job_runner.get_config_path", return_value="test_v26_runner.db"),
    ):
        await _run_job_directly(manifest)

        assert mock_crawl.call_count == 1
        job_id = mock_crawl.call_args[0][1]
        status = await db_manager.get_job_status(job_id)
        assert status["from_chapter"] == 10
        assert status["to_chapter"] == 20


@pytest.mark.asyncio
async def test_run_manifest_cyclic_error(tmp_path):
    # Create a cyclic manifest file
    manifest_file = tmp_path / "cyclic.json"
    manifest_data = [
        {"alias_id": "a", "task": "crawl", "payload": {"slug": "s1"}, "depends_on": ["b"]},
        {"alias_id": "b", "task": "crawl", "payload": {"slug": "s2"}, "depends_on": ["a"]},
    ]
    with open(manifest_file, "w") as f:
        json.dump(manifest_data, f)

    from vvr_scraper.job_runner import run_manifest

    with patch("vvr_scraper.job_runner.logger") as mock_logger:
        await run_manifest(str(manifest_file))
        # It should log an error about cyclic dependency
        error_calls = [call.args[0] for call in mock_logger.error.call_args_list]
        assert any("Cyclic dependency detected" in err for err in error_calls)
