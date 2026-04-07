import pytest
import os
import json
import shutil
import asyncio
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError

from vvr_scraper.job_models import JobManifest, ScrapeJob, RenderJob
from vvr_scraper.job_worker import JobWorker
from vvr_scraper.db import DatabaseManager

@pytest.fixture
async def db_manager():
    db_path = "test_runner.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = DatabaseManager(db_path)
    await db.init_db()
    yield db
    await db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def job_worker(db_manager):
    return JobWorker(db_manager)

def test_manifest_validation():
    """Kiểm tra xem Pydantic có validate đúng các file manifest JSON hợp lệ và không hợp lệ không."""
    # Valid Scrape Job
    valid_scrape = {
        "task": "crawl",
        "payload": {
            "slug": "test-story",
            "formats": ["epub"]
        }
    }
    manifest = JobManifest.model_validate(valid_scrape)
    assert isinstance(manifest.root, ScrapeJob)
    assert manifest.task == "crawl"
    assert manifest.payload.slug == "test-story"

    # Valid Render Job
    valid_render = {
        "task": "render",
        "payload": {
            "manifest_path": "path/to/manifest.json",
            "output_path": "output.mp4"
        }
    }
    manifest = JobManifest.model_validate(valid_render)
    assert isinstance(manifest.root, RenderJob)
    assert manifest.task == "render"
    assert manifest.payload.manifest_path == "path/to/manifest.json"

    # Invalid Manifest (missing task)
    invalid_manifest = {
        "payload": {"slug": "test"}
    }
    with pytest.raises(ValidationError):
        JobManifest.model_validate(invalid_manifest)

    # Invalid Task Type
    invalid_task = {
        "task": "unknown",
        "payload": {}
    }
    with pytest.raises(ValidationError):
        JobManifest.model_validate(invalid_task)

@pytest.mark.asyncio
async def test_job_dispatching(job_worker, db_manager):
    """Mock các hàm thực thi để kiểm tra xem Orchestrator có gọi đúng hàm dựa trên loại task không."""
    # Mock execute functions in job_runner because JobWorker imports them from there
    with patch("vvr_scraper.job_runner.execute_crawl_job", new_callable=AsyncMock) as mock_crawl, \
         patch("vvr_scraper.job_runner.execute_render_job", new_callable=AsyncMock) as mock_render:
        
        # 1. Test Crawl Job
        scrape_data = {
            "task": "crawl",
            "payload": {"slug": "test-story"}
        }
        scrape_job = JobManifest.model_validate(scrape_data)
        job_id = await db_manager.create_job("crawl", json.dumps(scrape_data))
        
        await job_worker.execute_job(job_id, scrape_job)
        mock_crawl.assert_called_once_with(scrape_job.payload, job_id, db_manager)
        
        # Verify DB success status
        status = await db_manager.get_job_status(job_id)
        assert status["status"] == "success"
        assert status["progress"] == 100.0
        
        # 2. Test Render Job
        render_data = {
            "task": "render",
            "payload": {"manifest_path": "m.json", "output_path": "o.mp4"}
        }
        render_job = JobManifest.model_validate(render_data)
        job_id_2 = await db_manager.create_job("render", json.dumps(render_data))
        
        await job_worker.execute_job(job_id_2, render_job)
        mock_render.assert_called_once_with(render_job.payload, job_id_2, db_manager)

        # Verify DB success status
        status_2 = await db_manager.get_job_status(job_id_2)
        assert status_2["status"] == "success"

@pytest.mark.asyncio
async def test_job_error_logging(job_worker, db_manager):
    """
    Giả lập một job bị lỗi (ném exception).
    Xác nhận file log được tạo trong 'error-logs/' có chứa manifest và stack trace.
    Xác nhận DB được cập nhật trạng thái 'failed'.
    """
    error_dir = "error-logs"
    if os.path.exists(error_dir):
        # Clean up before test
        for f in os.listdir(error_dir):
            os.remove(os.path.join(error_dir, f))
    else:
        os.makedirs(error_dir)
    
    # Mock execute_crawl_job to raise exception
    with patch("vvr_scraper.job_runner.execute_crawl_job", side_effect=Exception("Simulated failure")):
        scrape_data = {
            "task": "crawl",
            "payload": {"slug": "fail-story"}
        }
        scrape_job = JobManifest.model_validate(scrape_data)
        job_id = await db_manager.create_job("crawl", json.dumps(scrape_data))
        
        await job_worker.execute_job(job_id, scrape_job)
        
        # 1. Check if error-logs directory exists
        assert os.path.exists(error_dir)
        
        # 2. Check if log file is created
        logs = [f for f in os.listdir(error_dir) if f.startswith(f"job_{job_id}")]
        assert len(logs) == 1
        log_path = os.path.join(error_dir, logs[0])
        
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Simulated failure" in content
            assert "fail-story" in content
            assert "STACK TRACE" in content
            assert "=== JOB MANIFEST ===" in content
            
        # 3. Check DB status
        status = await db_manager.get_job_status(job_id)
        assert status["status"] == "failed"
        assert status["error_summary"] == "Simulated failure"
        assert status["error_log_path"] == log_path

    # Cleanup log file after test
    if os.path.exists(log_path):
        os.remove(log_path)
