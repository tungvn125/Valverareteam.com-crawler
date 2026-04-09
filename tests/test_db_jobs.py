import pytest

from vvr_scraper.db import DatabaseManager


@pytest.mark.asyncio
async def test_job_status_update(tmp_path):
    db_path = str(tmp_path / "test_jobs.db")
    db = DatabaseManager(db_path)
    await db.init_db()

    # Use create_job to get a valid ID
    job_id = await db.create_job("scrape", '{"slug": "test"}')

    # Update it
    await db.update_job_status(job_id, "failed", error_summary="Test error")

    row = await db.get_job_status(job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["error_summary"] == "Test error"

    await db.close()
