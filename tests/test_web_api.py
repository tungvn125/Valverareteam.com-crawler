"""
Tests for web package — API endpoints using FastAPI TestClient.
Tests ConnectionManager, DownloadManager, settings, task management,
OPDS routes, and API endpoints.
"""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from vvr_scraper.web import (
    ConnectionManager,
    DownloadManager,
    DownloadRequest,
    Settings,
    app,
    load_vvr_settings,
)

# =============================================================================
# ConnectionManager
# =============================================================================


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        cm = ConnectionManager()
        ws = AsyncMock()
        await cm.connect(ws)
        assert ws in cm.active_connections

        cm.disconnect(ws)
        assert ws not in cm.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent(self):
        cm = ConnectionManager()
        ws = AsyncMock()
        cm.disconnect(ws)  # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast(self):
        cm = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await cm.connect(ws1)
        await cm.connect(ws2)

        await cm.broadcast({"type": "test", "data": "hello"})

        ws1.send_json.assert_called_once_with({"type": "test", "data": "hello"})
        ws2.send_json.assert_called_once_with({"type": "test", "data": "hello"})

    @pytest.mark.asyncio
    async def test_broadcast_handles_broken_connection(self):
        cm = ConnectionManager()
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_json = AsyncMock(side_effect=Exception("Connection closed"))
        await cm.connect(ws_good)
        await cm.connect(ws_bad)

        await cm.broadcast({"type": "test"})

        ws_good.send_json.assert_called_once()


# =============================================================================
# DownloadManager
# =============================================================================


class TestDownloadManager:
    def test_initialization(self):
        dm = DownloadManager(num_workers=3)
        assert dm.num_workers == 3
        assert dm.workers == []

    @pytest.mark.asyncio
    async def test_add_task(self):
        dm = DownloadManager()
        req = DownloadRequest(slug="test-novel")

        with patch("vvr_scraper.web.state.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            await dm.add_task(req, "task-123")

            assert dm.queue.qsize() == 1
            mock_manager.broadcast.assert_called_once()


# =============================================================================
# Settings
# =============================================================================


class TestSettings:
    def test_default_settings(self):
        s = Settings()
        assert s.num_workers == 1
        assert s.default_output_folder == "novels"

    def test_custom_settings(self):
        s = Settings(num_workers=4, default_output_folder="/data/novels")
        assert s.num_workers == 4
        assert s.default_output_folder == "/data/novels"

    def test_load_settings_missing_file(self):
        with patch("vvr_scraper.web.models.get_config_path", return_value="/tmp/nonexistent_settings.json"):
            with patch("os.path.exists", return_value=False):
                result = load_vvr_settings()
                assert result.num_workers == 1

    def test_load_settings_valid_file(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"num_workers": 3, "default_output_folder": "/custom"}))

        with patch("vvr_scraper.web.models.get_config_path", return_value=str(settings_file)):
            result = load_vvr_settings()
            assert result.num_workers == 3
            assert result.default_output_folder == "/custom"

    def test_load_settings_invalid_file(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("not json {{{")

        with patch("vvr_scraper.web.models.get_config_path", return_value=str(settings_file)):
            result = load_vvr_settings()
            assert result.num_workers == 1  # defaults

    def test_save_settings(self, tmp_path):
        settings_file = tmp_path / "settings.json"

        with patch("vvr_scraper.web.models.get_config_path", return_value=str(settings_file)):
            settings = Settings(num_workers=5)
            with open(str(settings_file), "w", encoding="utf-8") as f:
                json.dump(settings.model_dump(), f, ensure_ascii=False, indent=2)

            with open(settings_file) as f:
                data = json.load(f)
            assert data["num_workers"] == 5


# =============================================================================
# DownloadRequest model
# =============================================================================


class TestDownloadRequest:
    def test_defaults(self):
        req = DownloadRequest(slug="test")
        assert req.slug == "test"
        assert req.formats == ["EPUB"]
        assert req.grouping == "tatca"
        assert req.tasks == 5
        assert req.skip_illustrations is False
        assert req.output_folder is None
        assert req.selected_urls is None

    def test_custom_values(self):
        req = DownloadRequest(
            slug="my-novel",
            formats=["PDF", "EPUB"],
            grouping="volume",
            tasks=10,
            skip_illustrations=True,
            output_folder="/out",
            selected_urls=["/c1", "/c2"],
        )
        assert req.formats == ["PDF", "EPUB"]
        assert req.grouping == "volume"
        assert req.tasks == 10


# =============================================================================
# API Endpoints (using TestClient)
# =============================================================================


class TestAPIEndpoints:
    """Tests for FastAPI endpoints using a mock DB."""

    @pytest.fixture
    def client(self):
        """Create a TestClient with mocked DB to avoid lifespan issues."""
        from contextlib import asynccontextmanager

        from fastapi.testclient import TestClient

        mock_db = AsyncMock()
        mock_db.get_all_novels = AsyncMock(return_value=[])
        mock_db.get_recent_jobs = AsyncMock(return_value=[])
        mock_db.init_db = AsyncMock()
        mock_db.close = AsyncMock()

        # No-op lifespan to skip startup tasks (workers, browsers)
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

    def test_get_settings(self, client):
        with patch("vvr_scraper.web.routes.api.load_vvr_settings", return_value=Settings(num_workers=2)):
            response = client.get("/api/settings")
            assert response.status_code == 200
            data = response.json()
            assert data["num_workers"] == 2

    def test_get_library_empty(self, client):
        response = client.get("/api/library")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_library_with_novels(self, client):
        app.state.db.get_all_novels = AsyncMock(
            return_value=[
                {"slug": "novel-1", "title": "Novel 1"},
                {"slug": "novel-2", "title": "Novel 2"},
            ]
        )
        response = client.get("/api/library")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_jobs(self, client):
        app.state.db.get_recent_jobs = AsyncMock(
            return_value=[
                {"id": "j1", "task_type": "crawl", "status": "success"},
            ]
        )
        response = client.get("/api/jobs")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_job_detail_found(self, client):
        app.state.db.get_job_status = AsyncMock(
            return_value={
                "id": "j1",
                "task_type": "crawl",
                "status": "running",
                "progress": 50.0,
            }
        )
        response = client.get("/api/jobs/j1")
        assert response.status_code == 200
        assert response.json()["progress"] == 50.0

    def test_get_job_detail_not_found(self, client):
        app.state.db.get_job_status = AsyncMock(return_value=None)
        response = client.get("/api/jobs/nonexistent")
        assert response.status_code == 404

    def test_get_task_logs_empty(self, client):
        response = client.get("/api/tasks/unknown-task/logs")
        assert response.status_code == 200
        assert response.json() == []

    def test_cancel_task(self, client):
        response = client.post("/api/tasks/task-123/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_pause_task_not_running(self, client):
        response = client.post("/api/tasks/task-999/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "not_running"

    def test_resume_task_not_found(self, client):
        response = client.post("/api/tasks/task-999/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "task_not_found"

    def test_opds_requires_auth(self, client):
        response = client.get("/opds/v1/root")
        assert response.status_code == 401

    def test_opds_with_valid_auth(self, client):
        with patch.dict(os.environ, {"VVR_OPDS_USER": "admin", "VVR_OPDS_PASS": "pass123"}):
            response = client.get("/opds/v1/root", auth=("admin", "pass123"))
            assert response.status_code == 200
            assert b"Valvrare" in response.content

    def test_opds_with_wrong_auth(self, client):
        with patch.dict(os.environ, {"VVR_OPDS_USER": "admin", "VVR_OPDS_PASS": "correct"}):
            response = client.get("/opds/v1/root", auth=("admin", "wrong"))
            assert response.status_code == 401
