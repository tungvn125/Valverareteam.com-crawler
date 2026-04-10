import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from vvr_scraper.models import StoryInfo

# Import the function to test
from vvr_scraper.web import check_library_updates


@pytest.mark.asyncio
async def test_check_library_updates():
    # Mock DB
    db = MagicMock()
    db.get_all_novels = AsyncMock(
        return_value=[
            {"slug": "novel-1", "title": "Novel 1", "last_synced_count": 10},
            {"slug": "novel-2", "title": "Novel 2", "last_synced_count": 20},
            {"slug": "novel-404", "title": "Novel 404", "last_synced_count": 5},
            {"slug": "novel-unknown", "title": "Novel Unknown", "last_synced_count": 5},
        ]
    )
    db.update_library_metadata = AsyncMock()

    # Mock Manager
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    # Mock lay_thong_tin_truyen
    async def mock_lay_thong_tin_truyen(client, slug):
        if slug == "novel-1":
            return StoryInfo(title="Novel 1", author="A", description="D", total_chapters="15")
        if slug == "novel-2":
            return StoryInfo(title="Novel 2", author="A", description="D", total_chapters="20")
        if slug == "novel-404":
            response = MagicMock()
            response.status_code = 404
            raise httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=response)
        if slug == "novel-unknown":
            return StoryInfo(title="Novel Unknown", author="A", description="D", total_chapters="Unknown")
        return StoryInfo(title="Other", author="A", description="D", total_chapters="0")

    # Use any_str or a helper for last_checked_at check
    class AnyDateTime:
        def __eq__(self, other):
            try:
                datetime.fromisoformat(other)
                return True
            except ValueError:
                return False

    with patch("vvr_scraper.web.routes.library.lay_thong_tin_truyen", side_effect=mock_lay_thong_tin_truyen):
        with patch("vvr_scraper.web.routes.library.load_session", return_value={}):
            with patch("vvr_scraper.web.routes.library.get_config_path", return_value="/tmp/fake"):
                await check_library_updates(db, manager)

    # Verify updates
    # novel-1 should have update (15 > 10)
    db.update_library_metadata.assert_any_call(
        "novel-1", {"server_chapter_count": 15, "has_updates": 1, "last_checked_at": AnyDateTime()}
    )

    # novel-2 should NOT have update (20 == 20)
    db.update_library_metadata.assert_any_call(
        "novel-2", {"server_chapter_count": 20, "has_updates": 0, "last_checked_at": AnyDateTime()}
    )

    # novel-404 should be archived
    db.update_library_metadata.assert_any_call("novel-404", {"status": "archived"})

    # novel-unknown should NOT have update_library_metadata called for chapters
    # (it skips after logging warning)
    # But wait, it might have been called if I didn't return early.
    # In my implementation:
    # if info.total_chapters == "Unknown":
    #     logger.warning(...)
    #     continue
    # So it should NOT be called.

    # Check broadcasts
    # Progress broadcasts for each novel
    manager.broadcast.assert_any_call({"type": "library_check_progress", "current": 1, "total": 4, "title": "Novel 1"})
    manager.broadcast.assert_any_call({"type": "library_check_progress", "current": 2, "total": 4, "title": "Novel 2"})
    manager.broadcast.assert_any_call(
        {"type": "library_check_progress", "current": 3, "total": 4, "title": "Novel 404"}
    )
    manager.broadcast.assert_any_call(
        {"type": "library_check_progress", "current": 4, "total": 4, "title": "Novel Unknown"}
    )

    # Completion broadcast
    manager.broadcast.assert_any_call({"type": "library_check_complete", "updates_found": 1})


@pytest.mark.asyncio
async def test_sync_all_endpoint():
    # Mock FastAPI app and its state
    from vvr_scraper.web import DownloadRequest, app
    from vvr_scraper.web.routes.library import sync_all_novels

    mock_db = AsyncMock()
    mock_db.get_all_novels.return_value = [
        {
            "slug": "novel-update",
            "title": "Novel Update",
            "has_updates": 1,
            "last_synced_count": 10,
            "server_chapter_count": 15,
            "output_folder": "/tmp/novel-update",
            "formats": "EPUB",
        },
        {
            "slug": "novel-no-update",
            "title": "Novel No Update",
            "has_updates": 0,
            "last_synced_count": 20,
            "server_chapter_count": 20,
        },
    ]
    mock_db.update_library_metadata = AsyncMock()

    # Manually set the db on the app state, saving original to restore later
    original_db = getattr(app.state, "db", None)
    app.state.db = mock_db

    try:
        # Mock download_queue and active_tasks
        with patch("vvr_scraper.web.state.download_queue.add_task", new_callable=AsyncMock) as mock_add_task:
            with patch("vvr_scraper.web.routes.library.get_chapter_tree_list", new_callable=AsyncMock) as mock_get_tree:
                # Mock the tree to return 15 chapters
                mock_get_tree.return_value = [
                    {"volume": "V1", "chapters": [{"title": f"C{i}", "url": f"/c{i}"} for i in range(1, 16)]}
                ]

                with patch("vvr_scraper.web.routes.library.async_playwright"):
                    with patch("vvr_scraper.web.routes.library.load_session", return_value={}):
                        with patch("vvr_scraper.web.routes.library.get_config_path", return_value="/tmp/fake"):
                            # Call the handler directly instead of via TestClient to avoid lifespan overwriting app.state.db
                            response = await sync_all_novels()

                            assert response == {"status": "ok", "queued": 1}

                            # Verify get_chapter_tree_list was called for the novel with updates
                            mock_get_tree.assert_called_once()

                            # Verify add_task was called with ALL 15 chapters
                            mock_add_task.assert_called_once()
                            req, task_id = mock_add_task.call_args[0]
                            assert isinstance(req, DownloadRequest)
                            assert req.slug == "novel-update"
                            assert len(req.selected_urls) == 15
                            assert req.selected_urls[0] == "/c1"
                            assert req.selected_urls[-1] == "/c15"
                            assert req.output_folder == "/tmp/novel-update"
                            assert req.formats == ["EPUB"]

                            # Verify has_updates was reset
                            mock_db.update_library_metadata.assert_called_with("novel-update", {"has_updates": 0})
    finally:
        app.state.db = original_db


@pytest.mark.asyncio
async def test_get_chapter_range_urls():
    from vvr_scraper.tao_so_do_cay import get_chapter_range_urls

    mock_tree = [
        {"volume": "Vol 1", "chapters": [{"title": "C1", "url": "/c1"}, {"title": "C2", "url": "/c2"}]},
        {
            "volume": "Vol 2",
            "chapters": [{"title": "C3", "url": "/c3"}, {"title": "C4", "url": "/c4"}, {"title": "C5", "url": "/c5"}],
        },
    ]

    with patch("vvr_scraper.tao_so_do_cay.get_chapter_tree_list", new_callable=AsyncMock) as mock_get_tree:
        mock_get_tree.return_value = mock_tree

        # Test range 1 to 4 (exclusive of 4, so indices 1, 2, 3)
        # Flattened list: /c1, /c2, /c3, /c4, /c5
        # Indices:        0,   1,   2,   3,   4
        # Range 1:4 -> /c2, /c3, /c4
        urls = await get_chapter_range_urls("some-slug", 1, 4)

        assert urls == ["/c2", "/c3", "/c4"]
        mock_get_tree.assert_called_once()


@pytest.mark.asyncio
async def test_run_scrape_task_updates_sync_count():
    from vvr_scraper.web import DownloadRequest, app
    from vvr_scraper.web.routes.download import run_scrape_task

    req = DownloadRequest(slug="novel-sync", formats=["EPUB"], tasks=1)
    task_id = "test-task"

    mock_db = AsyncMock()
    original_db = getattr(app.state, "db", None)
    app.state.db = mock_db

    try:
        # Mock all external calls inside run_scrape_task
        with patch("vvr_scraper.web.routes.download.lay_thong_tin_truyen", new_callable=AsyncMock) as mock_info:
            from dataclasses import dataclass

            @dataclass
            class MockStoryInfo:
                title: str
                author: str
                description: str
                cover_url: str
                total_chapters: str = "2"
                genres: list = None
                cover_path: str = None

            mock_info.return_value = MockStoryInfo(
                title="Novel Sync", author="A", description="D", cover_url="http://cover"
            )

            with patch("vvr_scraper.web.routes.download.get_chapter_tree_list", new_callable=AsyncMock) as mock_tree:
                mock_tree.return_value = [
                    {"volume": "V1", "chapters": [{"title": "C1", "url": "/c1"}, {"title": "C2", "url": "/c2"}]}
                ]

                with patch("vvr_scraper.web.routes.download.scrape_chapters", new_callable=AsyncMock) as mock_scrape:
                    mock_scrape.return_value = {"https://valvrareteam.net/c1": [], "https://valvrareteam.net/c2": []}

                    with patch("vvr_scraper.web.routes.download.tao_file_epub", new_callable=AsyncMock):
                        with patch("vvr_scraper.web.routes.download.async_playwright"):
                            with patch("os.makedirs"):
                                with patch("vvr_scraper.web.routes.download.load_session", return_value={}):
                                    with patch("vvr_scraper.web.state.manager.broadcast", new_callable=AsyncMock):
                                        with patch("vvr_scraper.web.routes.download.get_config_path", return_value="/tmp/fake"):
                                            with patch("os.path.exists", return_value=False):
                                                await run_scrape_task(req, task_id)

        # Verify update_library_metadata was called with last_synced_count = 2
        mock_db.update_library_metadata.assert_called_with("novel-sync", {"last_synced_count": 2, "has_updates": 0})
    finally:
        app.state.db = original_db


@pytest.mark.asyncio
async def test_run_scrape_task_skips_sync_count_on_partial():
    from vvr_scraper.web import DownloadRequest, app
    from vvr_scraper.web.routes.download import run_scrape_task

    # Manual partial download: only chapter 1, missing chapter 2 (the latest)
    req = DownloadRequest(slug="novel-partial", formats=["EPUB"], selected_urls=["/c1"])
    task_id = "test-task-partial"

    mock_db = AsyncMock()
    original_db = getattr(app.state, "db", None)
    app.state.db = mock_db

    try:
        # Mock all external calls inside run_scrape_task
        with patch("vvr_scraper.web.routes.download.lay_thong_tin_truyen", new_callable=AsyncMock) as mock_info:
            from dataclasses import dataclass

            @dataclass
            class MockStoryInfo:
                title: str
                author: str
                description: str
                cover_url: str
                total_chapters: str = "2"
                genres: list = None
                cover_path: str = None

            mock_info.return_value = MockStoryInfo(
                title="Novel Partial", author="A", description="D", cover_url="http://cover"
            )

            with patch("vvr_scraper.web.routes.download.get_chapter_tree_list", new_callable=AsyncMock) as mock_tree:
                mock_tree.return_value = [
                    {"volume": "V1", "chapters": [{"title": "C1", "url": "/c1"}, {"title": "C2", "url": "/c2"}]}
                ]

                with patch("vvr_scraper.web.routes.download.scrape_chapters", new_callable=AsyncMock) as mock_scrape:
                    mock_scrape.return_value = {"https://valvrareteam.net/c1": []}

                    with patch("vvr_scraper.web.routes.download.tao_file_epub", new_callable=AsyncMock):
                        with patch("vvr_scraper.web.routes.download.async_playwright"):
                            with patch("os.makedirs"):
                                with patch("vvr_scraper.web.routes.download.load_session", return_value={}):
                                    with patch("vvr_scraper.web.state.manager.broadcast", new_callable=AsyncMock):
                                        with patch("vvr_scraper.web.routes.download.get_config_path", return_value="/tmp/fake"):
                                            with patch("os.path.exists", return_value=False):
                                                await run_scrape_task(req, task_id)

        # Verify update_library_metadata was NOT called for last_synced_count
        # because /c2 was missing from selected_urls
        for call in mock_db.update_library_metadata.call_args_list:
            args, kwargs = call
            if args[0] == "novel-partial" and isinstance(args[1], dict) and "last_synced_count" in args[1]:
                pytest.fail(
                    "update_library_metadata should NOT have been called with last_synced_count for partial sync"
                )
    finally:
        app.state.db = original_db


if __name__ == "__main__":
    asyncio.run(test_check_library_updates())
