import pytest
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.publisher import Publisher
from vvr_scraper.models import StoryInfo

@pytest.mark.asyncio
async def test_publisher_resumption_logic():
    # Mock data
    mock_story = StoryInfo(title="Test Story", author="Author", description="Desc", slug="test-slug")
    
    # We want to test that if a task is already AUDIO_READY, it skips scraping and TTS
    pending_tasks = [
        {
            "novel_slug": "test-slug",
            "chapter_url": "https://valvrareteam.net/test-slug/chuong-1",
            "status": "AUDIO_READY",
            "audio_path": "test_chap_1.mp3",
            "video_path": None,
            "ai_metadata_json": json.dumps({"title": "Mock Title", "description": "Mock Desc", "tags": ["tag"]})
        }
    ]

    # Mock all internal components
    with patch('vvr_scraper.publisher.DatabaseManager.init_db', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.YouTubeClient', autospec=True), \
         patch('vvr_scraper.publisher.DatabaseManager.get_pending_tasks', new_callable=AsyncMock, return_value=pending_tasks), \
         patch('vvr_scraper.publisher.DatabaseManager.update_task_status', new_callable=AsyncMock) as mock_update_status, \
         patch('vvr_scraper.publisher.VideoEngine.generate_video', new_callable=AsyncMock) as mock_video, \
         patch('vvr_scraper.publisher.lay_thong_tin_truyen', new_callable=AsyncMock, return_value=mock_story), \
         patch('vvr_scraper.publisher.scrape_chapters', new_callable=AsyncMock) as mock_scrape, \
         patch('vvr_scraper.publisher.tao_file_mp3', new_callable=AsyncMock) as mock_tts, \
         patch('vvr_scraper.publisher.async_playwright', new_callable=MagicMock), \
         patch('os.path.exists', return_value=True):
        
        publisher = Publisher()
        # Mock the instances created in __init__
        publisher.yt.get_remaining_quota.return_value = 10000
        publisher.yt.upload_video = AsyncMock(return_value="yt_id_123")
        
        # Setup scrape result
        mock_scrape.return_value = {
            "https://valvrareteam.net/test-slug/chuong-1": [MagicMock(type="text", data="text")]
        }
        
        # We need to mock the cleanup too so it doesn't try to delete non-existent files
        with patch('os.remove'):
            await publisher.process_queue(slug="test-slug", dry_run=False)
        
        # Verify that scrape WAS called because we need content/images for video rendering
        mock_scrape.assert_called_once()
        # Verify that TTS was NOT called because status was AUDIO_READY
        mock_tts.assert_not_called()
        
        # Verify that video generation WAS called
        mock_video.assert_called_once()
        
        # Verify status updates
        # Expected: VIDEO_READY then PUBLISHED
        assert mock_update_status.call_count >= 2
        mock_update_status.assert_any_call("https://valvrareteam.net/test-slug/chuong-1", "VIDEO_READY", video_path="test_chap_1.mp4")
        mock_update_status.assert_any_call("https://valvrareteam.net/test-slug/chuong-1", "PUBLISHED", youtube_id="yt_id_123")

@pytest.mark.asyncio
async def test_run_pipeline_does_not_reset_status_if_exists():
    # Mock chapter tree data
    mock_tree = [{'volume': 'Vol 1', 'chapters': [{'title': 'Chap 1', 'url': '/slug/1'}]}]
    
    with patch('vvr_scraper.publisher.DatabaseManager.init_db', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.YouTubeClient', autospec=True), \
         patch('vvr_scraper.publisher.lay_thong_tin_truyen', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.tao_so_do_cay.get_chapter_tree_list', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.DatabaseManager.upsert_publishing_task', new_callable=AsyncMock) as mock_upsert, \
         patch('vvr_scraper.publisher.Publisher.process_queue', new_callable=AsyncMock), \
         patch('builtins.open', MagicMock()), \
         patch('json.load', return_value=mock_tree), \
         patch('os.path.exists', return_value=True), \
         patch('os.remove', MagicMock()):
        
        publisher = Publisher()
        # Mocking the upsert to see what it's called with
        await publisher.run_pipeline("test-slug", chapters=[1])
        
        # Verify it called upsert with PENDING
        mock_upsert.assert_called_once()
        args, _ = mock_upsert.call_args
        assert args[0]['status'] == 'PENDING'
        # This confirms that currently run_pipeline ALWAYS uses PENDING when calling upsert.
        # We want to change this so it only queues if not already there, OR it preserves status.
