import pytest
from vvr_scraper.db import DatabaseManager
import os
from datetime import datetime

@pytest.mark.asyncio
async def test_job_status_update():
    db_path = "test_jobs.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    db = DatabaseManager(db_path)
    await db.init_db()
    
    # Insert a dummy job
    conn = await db.get_db()
    await conn.execute("INSERT INTO jobs (task_type, status, payload, created_at) VALUES (?, ?, ?, ?)", 
                      ("scrape", "pending", '{"slug": "test"}', datetime.now().isoformat()))
    await conn.commit()
    
    # Update it
    await db.update_job_status(1, "failed", error_summary="Test error")
    
    async with conn.execute("SELECT status, error_summary FROM jobs WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        assert row["status"] == "failed"
        assert row["error_summary"] == "Test error"
        
    await db.close()
    if os.path.exists(db_path):
        os.remove(db_path)
