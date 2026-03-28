import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.cli import ValvrareScraperCLI
from vvr_scraper.models import StoryInfo
import json
import os

@pytest.mark.asyncio
async def test_cli_publish_command_dry_run():
    """
    Simulates: vvrt publish test-slug --dry-run
    """
    mock_story = StoryInfo(title="Test Story", author="Author", description="Desc", slug="test-slug")
    mock_tree = [{"volume": "Vol 1", "chapters": [{"title": "Chap 1", "url": "/test-slug/chuong-1"}]}]
    
    # Simulate CLI arguments
    test_args = ['vvrt', 'publish', 'test-slug', '--dry-run']
    
    with patch.object(sys, 'argv', test_args), \
         patch('vvr_scraper.publisher.DatabaseManager.init_db', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.DatabaseManager.get_task_by_url', new_callable=AsyncMock, return_value=None), \
         patch('vvr_scraper.publisher.DatabaseManager.upsert_publishing_task', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.DatabaseManager.get_pending_tasks', new_callable=AsyncMock) as mock_get_pending, \
         patch('vvr_scraper.publisher.DatabaseManager.update_task_status', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.lay_thong_tin_truyen', new_callable=AsyncMock, return_value=mock_story), \
         patch('vvr_scraper.publisher.tao_so_do_cay.get_chapter_tree_list', new_callable=AsyncMock) as mock_tree_fetch, \
         patch('vvr_scraper.publisher.scrape_chapters', new_callable=AsyncMock) as mock_scrape, \
         patch('vvr_scraper.publisher.AIHelper.generate_metadata', new_callable=AsyncMock) as mock_ai, \
         patch('vvr_scraper.publisher.tao_file_mp3', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.VideoEngine.generate_video', new_callable=AsyncMock) as mock_video, \
         patch('vvr_scraper.publisher.YouTubeClient.get_remaining_quota', return_value=10000), \
         patch('vvr_scraper.publisher.async_playwright', new_callable=MagicMock), \
         patch('vvr_scraper.cli.Console.print') as mock_print:
        
        # Setup tree fetch to write a dummy file
        def tree_side_effect(url, output_file, **kwargs):
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(mock_tree, f)
        mock_tree_fetch.side_effect = tree_side_effect
        
        # Setup pending tasks return value for process_queue
        mock_get_pending.return_value = [
            {
                "novel_slug": "test-slug",
                "chapter_url": "https://valvrareteam.net/test-slug/chuong-1",
                "status": "PENDING"
            }
        ]
        
        # Setup scrape result
        mock_scrape.return_value = {
            "https://valvrareteam.net/test-slug/chuong-1": [MagicMock(type="text", data="text")]
        }
        
        mock_ai.return_value = MagicMock()
        mock_ai.return_value.title = "Mock Title"
        mock_ai.return_value.model_dump_json.return_value = "{}"
        mock_ai.return_value.model_dump.return_value = {"title": "Mock Title"}

        cli = ValvrareScraperCLI()
        await cli.run()
        
        # Verify it went through the pipeline
        mock_scrape.assert_called()
        mock_ai.assert_called()
        mock_video.assert_not_called() # Should NOT be called in dry-run (per my refactored publisher)
        
        # Check if dry-run log message was printed (indirectly via mock_print or just check mock_video not called)
        # In my refactored publisher.py:
        # if not dry_run:
        #    ... generate_video ...
        # else:
        #    logger.info(f"[DRY-RUN] Would generate video: {video_path}")
        
        # Also check cli completion message
        mock_print.assert_any_call("[bold green]Publishing process completed.[/bold green]")

@pytest.mark.asyncio
async def test_cli_publish_all_new_dry_run():
    """
    Simulates: vvrt publish --all-new --dry-run
    """
    test_args = ['vvrt', 'publish', '--all-new', '--dry-run']
    
    with patch.object(sys, 'argv', test_args), \
         patch('vvr_scraper.publisher.DatabaseManager.init_db', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.Publisher.sync_library_and_queue_new_chapters', new_callable=AsyncMock) as mock_sync, \
         patch('vvr_scraper.publisher.Publisher.process_queue', new_callable=AsyncMock) as mock_process, \
         patch('vvr_scraper.cli.Console.print') as mock_print:
        
        cli = ValvrareScraperCLI()
        await cli.run()
        
        mock_sync.assert_called_once()
        mock_process.assert_called_once_with(dry_run=True, ai_off=False)
        mock_print.assert_any_call("[bold green]Publishing process completed.[/bold green]")
