import pytest
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.publisher import Publisher
from vvr_scraper.models import StoryInfo

@pytest.mark.asyncio
async def test_run_pipeline_preserves_status_if_exists():
    """
    Test that run_pipeline does not reset tasks that are already in the queue
    with a status other than PENDING or FAILED (e.g., AUDIO_READY, PUBLISHED).
    """
    mock_story = StoryInfo(title="Test Story", author="Author", description="Desc", slug="test-slug")
    mock_tree = [{'volume': 'Vol 1', 'chapters': [{'title': 'Chap 1', 'url': '/test-slug/chuong-1'}]}]
    
    # Existing task that is AUDIO_READY
    existing_task = {
        "novel_slug": "test-slug",
        "chapter_url": "https://valvrareteam.net/test-slug/chuong-1",
        "status": "AUDIO_READY"
    }

    with patch('vvr_scraper.publisher.DatabaseManager.init_db', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.YouTubeClient', autospec=True), \
         patch('vvr_scraper.publisher.lay_thong_tin_truyen', new_callable=AsyncMock, return_value=mock_story), \
         patch('vvr_scraper.publisher.tao_so_do_cay.get_chapter_tree_list', new_callable=AsyncMock), \
         patch('vvr_scraper.publisher.DatabaseManager.get_task_by_url', new_callable=AsyncMock, return_value=existing_task), \
         patch('vvr_scraper.publisher.DatabaseManager.upsert_publishing_task', new_callable=AsyncMock) as mock_upsert, \
         patch('vvr_scraper.publisher.Publisher.process_queue', new_callable=AsyncMock), \
         patch('builtins.open', MagicMock()), \
         patch('json.load', return_value=mock_tree), \
         patch('os.path.exists', return_value=True), \
         patch('os.remove', MagicMock()):
        
        publisher = Publisher()
        # Mocking the upsert to see what it's called with
        await publisher.run_pipeline("test-slug", chapters=[1])
        
        # Verify it did NOT call upsert with PENDING because it was already AUDIO_READY
        # Actually, if it's already in the queue, we might skip upserting entirely
        # or upsert with the existing status.
        for call in mock_upsert.call_args_list:
            args, _ = call
            assert args[0]['status'] != 'PENDING' # Should not reset to PENDING
