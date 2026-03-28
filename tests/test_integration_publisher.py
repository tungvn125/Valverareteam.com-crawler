import pytest
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.publisher import Publisher
from vvr_scraper.models import StoryInfo

@pytest.mark.asyncio
async def test_publisher_run_pipeline_dry_run():
    # Mock data
    mock_story = StoryInfo(title="Test Story", author="Author", description="Desc", slug="test-slug")
    mock_tree = [{"volume": "Vol 1", "chapters": [{"title": "Chap 1", "url": "/test-slug/chuong-1"}]}]
    
    # Mock all internal components
    with patch('vvr_scraper.publisher.DatabaseManager.init_db', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.DatabaseManager.upsert_publishing_task', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.DatabaseManager.get_task_by_url', new_callable=AsyncMock, return_value=None), \
         patch('vvr_scraper.publisher.DatabaseManager.get_pending_tasks', new_callable=AsyncMock) as mock_get_pending, \
         patch('vvr_scraper.publisher.DatabaseManager.update_task_status', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.AIHelper.generate_metadata', new_callable=AsyncMock) as mock_ai, \
         patch('vvr_scraper.publisher.YouTubeClient.get_remaining_quota', return_value=10000), \
         patch('vvr_scraper.publisher.VideoEngine.generate_video', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.lay_thong_tin_truyen', new_callable=AsyncMock, return_value=mock_story), \
         patch('vvr_scraper.publisher.tao_so_do_cay.get_chapter_tree_list', new_callable=AsyncMock) as mock_tree_fetch, \
         patch('vvr_scraper.publisher.scrape_chapters', new_callable=AsyncMock) as mock_scrape, \
         patch('vvr_scraper.publisher.tao_file_mp3', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.async_playwright', new_callable=MagicMock):
        
        # Setup tree fetch to write a dummy file
        def side_effect(url, output_file, **kwargs):
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(mock_tree, f)
        mock_tree_fetch.side_effect = side_effect
        
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
        
        mock_ai_meta = MagicMock()
        mock_ai_meta.title = "Mock Title"
        mock_ai_meta.model_dump_json.return_value = "{}"
        mock_ai_meta.model_dump.return_value = {"title": "Mock Title"}
        mock_ai.return_value = mock_ai_meta
        
        publisher = Publisher()
        await publisher.run_pipeline("test-slug", dry_run=True)
        
        mock_ai.assert_called_once()
        # Verify temp file was cleaned up
        assert not os.path.exists("temp_test-slug_chapters.json")
