"""
Unit tests for job_runner.py — resolve_story_url, execute_crawl_job,
execute_render_job, run_manifest, start_server_from_job.
"""

import json
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from vvr_scraper.job_models import (
    JobManifest,
    RenderPayload,
    ScrapeJob,
    ScrapePayload,
    ServerPayload,
)
from vvr_scraper.job_runner import (
    _run_job_directly,
    execute_render_job,
    resolve_story_url,
    run_manifest,
    start_server_from_job,
)
from vvr_scraper.models import ContentItem, StoryInfo


# =============================================================================
# resolve_story_url
# =============================================================================

class TestResolveStoryUrl:
    @pytest.mark.asyncio
    async def test_finds_url_in_sitemap(self):
        sitemap_xml = b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://valvrareteam.net/truyen/dau-pha-thuong-khung-abc12345</loc></url>
            <url><loc>https://valvrareteam.net/truyen/mot-truyen-khac-xyz</loc></url>
        </urlset>"""

        mock_response = MagicMock()
        mock_response.content = sitemap_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            result = await resolve_story_url("dau-pha-thuong-khung")
            assert result is not None
            assert "dau-pha-thuong-khung" in result

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        sitemap_xml = b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://valvrareteam.net/truyen/other-story</loc></url>
        </urlset>"""

        mock_response = MagicMock()
        mock_response.content = sitemap_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            result = await resolve_story_url("non-existing-story")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self):
        with patch("httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.get = AsyncMock(side_effect=Exception("Network error"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            result = await resolve_story_url("any-story")
            assert result is None

    @pytest.mark.asyncio
    async def test_excludes_chapter_urls(self):
        sitemap_xml = b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://valvrareteam.net/truyen/my-story/chuong-1</loc></url>
            <url><loc>https://valvrareteam.net/truyen/my-story-abc123</loc></url>
        </urlset>"""

        mock_response = MagicMock()
        mock_response.content = sitemap_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            result = await resolve_story_url("my-story")
            # Should find the non-chapter URL
            assert result is not None
            assert "/chuong" not in result


# =============================================================================
# execute_render_job
# =============================================================================

class TestExecuteRenderJob:
    @pytest.mark.asyncio
    async def test_calls_renderer(self):
        payload = RenderPayload(
            manifest_path="/tmp/manifest.json",
            output_path="/tmp/output.mp4",
            fps=30,
        )
        mock_db = AsyncMock()

        with patch("vvr_scraper.job_runner.VideoRenderer") as MockRenderer:
            mock_renderer = AsyncMock()
            MockRenderer.return_value = mock_renderer

            await execute_render_job(payload, "job-123", mock_db)

            MockRenderer.assert_called_once_with(
                manifest_path="/tmp/manifest.json",
                output_path="/tmp/output.mp4",
                fps=30,
                render_format="landscape",
                vfx_scale=100,
            )
            mock_renderer.render.assert_called_once()
            mock_db.update_job_status.assert_any_call("job-123", "running", progress=10.0)

    @pytest.mark.asyncio
    async def test_handles_render_failure(self):
        payload = RenderPayload(
            manifest_path="/tmp/manifest.json",
            output_path="/tmp/output.mp4",
        )
        mock_db = AsyncMock()

        with patch("vvr_scraper.job_runner.VideoRenderer") as MockRenderer:
            mock_renderer = AsyncMock()
            mock_renderer.render = AsyncMock(side_effect=Exception("FFmpeg crashed"))
            MockRenderer.return_value = mock_renderer

            with pytest.raises(Exception, match="FFmpeg crashed"):
                await execute_render_job(payload, "job-fail", mock_db)

            mock_db.update_job_status.assert_any_call(
                "job-fail", "failed", error_summary="FFmpeg crashed"
            )

    @pytest.mark.asyncio
    async def test_render_without_db(self):
        payload = RenderPayload(
            manifest_path="/tmp/manifest.json",
            output_path="/tmp/output.mp4",
        )

        with patch("vvr_scraper.job_runner.VideoRenderer") as MockRenderer:
            mock_renderer = AsyncMock()
            MockRenderer.return_value = mock_renderer

            # Should not crash with db=None
            await execute_render_job(payload, "job-no-db", None)
            mock_renderer.render.assert_called_once()


# =============================================================================
# start_server_from_job
# =============================================================================

class TestStartServerFromJob:
    @pytest.mark.asyncio
    async def test_starts_server(self):
        payload = ServerPayload(host="0.0.0.0", port=9000)

        with patch("vvr_scraper.job_runner.run_web_server", new_callable=AsyncMock) as mock_server:
            await start_server_from_job(payload)
            mock_server.assert_called_once_with(host="0.0.0.0", port=9000)

    @pytest.mark.asyncio
    async def test_sets_opds_password_env(self):
        payload = ServerPayload(opds_password="secret123")

        with patch("vvr_scraper.job_runner.run_web_server", new_callable=AsyncMock):
            await start_server_from_job(payload)
            assert os.environ.get("VVR_OPDS_PASSWORD") == "secret123"

        # Cleanup
        os.environ.pop("VVR_OPDS_PASSWORD", None)


# =============================================================================
# run_manifest
# =============================================================================

class TestRunManifest:
    @pytest.mark.asyncio
    async def test_missing_file(self):
        """Should log error and return gracefully on missing file."""
        await run_manifest("/nonexistent/manifest.json")
        # Should not raise

    @pytest.mark.asyncio
    async def test_invalid_json(self, tmp_path):
        """Should handle invalid JSON gracefully."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json")

        await run_manifest(str(bad_file))
        # Should not raise

    @pytest.mark.asyncio
    async def test_valid_manifest_submits_to_server(self, tmp_path):
        """When local server is running, should submit via API."""
        manifest_data = {
            "task": "crawl",
            "payload": {"slug": "test-story", "formats": ["epub"]},
        }
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.post = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await run_manifest(str(manifest_file))
            instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_local_when_server_down(self, tmp_path):
        """When server is not available, should run locally."""
        manifest_data = {
            "task": "crawl",
            "payload": {"slug": "test-story", "formats": ["epub"]},
        }
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        with patch("httpx.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.post = AsyncMock(side_effect=Exception("Connection refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            with patch("vvr_scraper.job_runner._run_job_directly", new_callable=AsyncMock) as mock_direct:
                await run_manifest(str(manifest_file))
                mock_direct.assert_called_once()
