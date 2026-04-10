import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from vvr_scraper.web import app
from vvr_scraper.job_models import JobManifest, ScrapePayload, ScrapeJob

@pytest.fixture
def client():
    """Create a TestClient with mocked DB to avoid lifespan issues."""
    from contextlib import asynccontextmanager
    
    mock_db = AsyncMock()
    mock_db.create_job = AsyncMock(return_value="mock_job_id")
    mock_db.close = AsyncMock()

    @asynccontextmanager
    async def noop_lifespan(a):
        original_db = getattr(a.state, "db", None)
        a.state.db = mock_db
        try:
            yield
        finally:
            a.state.db = original_db

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.router.lifespan_context = original_lifespan

def test_submit_job_without_worker(client):
    with patch("vvr_scraper.web.routes.jobs.worker", None):
        response = client.post("/api/jobs", json={
            "task": "crawl",
            "payload": {"slug": "test", "formats": ["EPUB"]}
        })
        assert response.status_code == 503
        assert response.json()["detail"] == "JobWorker not initialized"

def test_submit_job_success_with_dependencies(client):
    worker_mock = AsyncMock()
    app.state.db.create_job = AsyncMock(side_effect=["job_id_1", "job_id_2"])
    
    payload = [
        {
            "task": "crawl",
            "alias_id": "crawl_1",
            "payload": {"slug": "test", "formats": ["EPUB"]},
            "priority": 3
        },
        {
            "task": "render",
            "depends_on": ["crawl_1"],
            "payload": {"manifest_path": "test", "output_path": "test"},
            "priority": 1
        }
    ]
    
    with patch("vvr_scraper.web.routes.jobs.worker", worker_mock):
        response = client.post("/api/jobs", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert len(data["job_ids"]) == 2
        
        # Verify dependency resolution mapping crawl_1 -> job_id_1
        # The second create_job call for render job should have depends_on="job_id_1"
        call_args = app.state.db.create_job.call_args_list[1][1]
        assert call_args["depends_on"] == "job_id_1"
        assert worker_mock.enqueue_job.call_count == 2

def test_submit_job_exception(client):
    worker_mock = AsyncMock()
    app.state.db.create_job = AsyncMock(side_effect=Exception("DB Error"))
    
    payload = {
        "task": "crawl",
        "payload": {"slug": "test", "formats": ["EPUB"]}
    }
    
    with patch("vvr_scraper.web.routes.jobs.worker", worker_mock):
        response = client.post("/api/jobs", json=payload)
        assert response.status_code == 400
        assert "DB Error" in response.json()["detail"]

def test_pause_task_running(client):
    future_mock = MagicMock()
    with patch.dict("vvr_scraper.web.routes.jobs.active_tasks_futures", {"t1": future_mock}):
        response = client.post("/api/tasks/t1/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "pausing"
        future_mock.cancel.assert_called_once()

def test_resume_task_found(client):
    req_mock = MagicMock()
    mock_queue = AsyncMock()
    with patch.dict("vvr_scraper.web.routes.jobs.active_tasks", {"t1": req_mock}), \
         patch("vvr_scraper.web.state.download_queue", mock_queue, create=True):
        response = client.post("/api/tasks/t1/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "resuming"
        mock_queue.add_task.assert_called_once()
