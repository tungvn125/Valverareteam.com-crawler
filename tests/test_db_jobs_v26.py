import json
import os

import pytest

from vvr_scraper.db import DatabaseManager
from vvr_scraper.job_models import JobManifest, ScrapePayload


@pytest.fixture
async def db_manager():
    db_path = "test_jobs_v26.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    manager = DatabaseManager(db_path)
    await manager.init_db()
    yield manager
    await manager.close()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_db_schema_v26(db_manager):
    db = await db_manager.get_db()
    cursor = await db.execute("PRAGMA table_info(jobs)")
    columns = {row[1]: row[2] for row in await cursor.fetchall()}

    assert "alias_id" in columns
    assert "batch_id" in columns
    assert "depends_on" in columns
    assert "priority" in columns
    assert "from_chapter" in columns
    assert "to_chapter" in columns


@pytest.mark.asyncio
async def test_create_job_v26(db_manager):
    payload = {"slug": "test-novel", "formats": ["epub"]}
    job_id = await db_manager.create_job(
        task_type="crawl",
        payload=json.dumps(payload),
        alias_id="job-1",
        batch_id="batch-123",
        depends_on=json.dumps(["other-job"]),
        priority=10,
        from_chapter=1,
        to_chapter=10,
    )

    job = await db_manager.get_job_status(job_id)
    assert job["alias_id"] == "job-1"
    assert job["batch_id"] == "batch-123"
    assert job["depends_on"] == json.dumps(["other-job"])
    assert job["priority"] == 10
    assert job["from_chapter"] == 1
    assert job["to_chapter"] == 10


def test_scrape_payload_v26():
    payload = ScrapePayload(slug="test", from_chapter=1, to_chapter=5, grouping=10, skip_illustrations=True)
    assert payload.from_chapter == 1
    assert payload.to_chapter == 5
    assert payload.grouping == 10
    assert payload.skip_illustrations is True
    assert payload.formats == ["epub", "pdf", "cinema"]


def test_job_manifest_list_v26():
    manifest_data = [
        {"task": "crawl", "payload": {"slug": "novel-1"}, "alias_id": "job-1", "priority": 5},
        {"task": "crawl", "payload": {"slug": "novel-2"}, "alias_id": "job-2", "depends_on": ["job-1"]},
    ]
    manifest = JobManifest.model_validate(manifest_data)
    assert isinstance(manifest.root, list)
    assert len(manifest.root) == 2
    assert manifest.root[0].alias_id == "job-1"
    assert manifest.root[1].depends_on == ["job-1"]
