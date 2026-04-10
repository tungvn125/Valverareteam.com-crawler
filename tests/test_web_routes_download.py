import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.web.models import DownloadRequest
from vvr_scraper.web.routes.download import run_scrape_task


@pytest.fixture
def mock_story_info():
    mock = MagicMock()
    mock.title = "Test Novel"
    mock.author = "Author"
    mock.description = "Test Desc"
    mock.cover_url = "http://test.com/cover.jpg"
    mock.cover_path = "cover.jpg"
    mock.genres = "Action,Fantasy"
    return mock

@pytest.fixture
def mock_chapter_data():
    return [
        {
            "volume": "Vol 1",
            "chapters": [
                {"title": "Chapter 1", "url": "/c1"},
                {"title": "Chapter 2", "url": "/c2"}
            ]
        }
    ]

@pytest.mark.asyncio
async def test_run_scrape_task_success(mock_story_info, mock_chapter_data):
    req = DownloadRequest(
        slug="test-novel",
        formats=["EPUB", "PDF", "AD-MP3"],
        output_folder="/tmp/test_download"
    )
    task_id = "task123"

    mock_db = AsyncMock()

    with patch("vvr_scraper.web.routes.download.manager.broadcast", new_callable=AsyncMock) as mock_broadcast, \
         patch("vvr_scraper.web.routes.download.lay_thong_tin_truyen", return_value=mock_story_info), \
         patch("vvr_scraper.web.routes.download.get_chapter_tree_list", return_value=mock_chapter_data), \
         patch("vvr_scraper.web.routes.download.scrape_chapters", return_value={"https://valvrareteam.net/c1": [], "https://valvrareteam.net/c2": []}), \
         patch("vvr_scraper.web.routes.download.tao_file_epub", new_callable=AsyncMock), \
         patch("vvr_scraper.web.routes.download.tao_file_pdf", new_callable=AsyncMock), \
         patch("vvr_scraper.web.routes.download.tao_file_audiodrama", new_callable=AsyncMock), \
         patch("vvr_scraper.web.routes.download.get_db", return_value=mock_db), \
         patch("vvr_scraper.web.routes.download.async_playwright") as mock_playwright, \
         patch("os.makedirs"):

        # Setup playwright mock
        mock_p = AsyncMock()
        mock_browser = AsyncMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_playwright.return_value.__aenter__.return_value = mock_p

        await run_scrape_task(req, task_id)

        # Verify broadcasts
        mock_broadcast.assert_any_call({"type": "complete", "task_id": "task123", "path": "/tmp/test_download"})

        # Verify db updates
        mock_db.upsert_novel.assert_called_once()
        mock_db.update_library_metadata.assert_called_once()

@pytest.mark.asyncio
async def test_run_scrape_task_high_failure_rate(mock_story_info, mock_chapter_data):
    req = DownloadRequest(slug="test-novel", formats=["EPUB"], output_folder="/tmp/test_download")
    task_id = "task123"

    with patch("vvr_scraper.web.routes.download.manager.broadcast", new_callable=AsyncMock) as mock_broadcast, \
         patch("vvr_scraper.web.routes.download.lay_thong_tin_truyen", return_value=mock_story_info), \
         patch("vvr_scraper.web.routes.download.get_chapter_tree_list", return_value=mock_chapter_data), \
         patch("vvr_scraper.web.routes.download.scrape_chapters", return_value={}), \
         patch("vvr_scraper.web.routes.download.async_playwright") as mock_playwright, \
         patch("os.makedirs"):

        mock_p = AsyncMock()
        mock_browser = AsyncMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_playwright.return_value.__aenter__.return_value = mock_p

        # Expect Exception due to high failure rate
        with patch("vvr_scraper.web.routes.download.logger.error") as mock_logger:
            await run_scrape_task(req, task_id)
            mock_logger.assert_any_call("Quá nhiều chương tải thất bại: 2/2 (100%). Hủy xuất file.")
            mock_broadcast.assert_any_call({"type": "error", "task_id": "task123", "error": "Quá nhiều chương tải thất bại: 2/2 (100%). Hủy xuất file."})

@pytest.mark.asyncio
async def test_run_scrape_task_cancellation():
    req = DownloadRequest(slug="test-novel")
    task_id = "task123"

    with patch("vvr_scraper.web.routes.download.manager.broadcast", new_callable=AsyncMock) as mock_broadcast, \
         patch("vvr_scraper.web.routes.download.lay_thong_tin_truyen", side_effect=asyncio.CancelledError):

        with pytest.raises(asyncio.CancelledError):
            await run_scrape_task(req, task_id)

        mock_broadcast.assert_any_call({"type": "status", "task_id": "task123", "status": "Paused"})
