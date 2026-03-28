import pytest
from unittest.mock import MagicMock, patch
from vvr_scraper.youtube_api import YouTubeClient

@pytest.fixture
def mock_youtube_client():
    with patch('googleapiclient.discovery.build'):
        with patch('vvr_scraper.youtube_api.YouTubeClient._authenticate', return_value=MagicMock()):
            client = YouTubeClient()
            client.service = MagicMock()
            yield client

def test_get_remaining_quota(mock_youtube_client):
    # Mock quota logic - should return 10000 by default or tracking from file
    quota = mock_youtube_client.get_remaining_quota()
    assert quota >= 0
    assert quota <= 10000

def test_quota_reset_on_new_day(mock_youtube_client, tmp_path):
    # Manually create a quota file with an old date and low remaining quota
    quota_file = tmp_path / ".youtube_quota.json"
    import json
    from datetime import datetime, timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    with open(quota_file, 'w') as f:
        json.dump({"remaining": 500, "last_reset": yesterday}, f)
    
    # Update the client's quota_path to our temp file
    mock_youtube_client.quota_path = str(quota_file)
    
    # Should reset to 10000 because it's a "new day"
    assert mock_youtube_client.get_remaining_quota() == 10000
    
    # Verify the file was updated with today's date
    with open(quota_file, 'r') as f:
        data = json.load(f)
        assert data["remaining"] == 10000
        assert data["last_reset"] == datetime.now().strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_upload_video_mock(mock_youtube_client):
    # Mock the resumable upload process and MediaFileUpload
    mock_request = MagicMock()
    mock_request.execute.return_value = {'id': 'test_video_id'}
    mock_youtube_client.service.videos().insert.return_value = mock_request
    
    metadata = {
        'title': 'Test Title',
        'description': 'Test Desc',
        'tags': ['tag1']
    }
    
    with patch('vvr_scraper.youtube_api.MediaFileUpload'):
        video_id = await mock_youtube_client.upload_video("test.mp4", metadata)
        assert video_id == 'test_video_id'
        mock_youtube_client.service.videos().insert.assert_called_once()

@pytest.mark.asyncio
async def test_upload_video_insufficient_quota(mock_youtube_client):
    # Mock low quota
    with patch.object(mock_youtube_client, 'get_remaining_quota', return_value=500):
        metadata = {'title': 'Test Title'}
        with pytest.raises(Exception, match="Insufficient YouTube API quota"):
            await mock_youtube_client.upload_video("test.mp4", metadata)

@pytest.mark.asyncio
async def test_upload_video_dry_run(mock_youtube_client):
    # Enable dry run mode
    mock_youtube_client.dry_run = True
    
    metadata = {
        'title': 'Dry Run Title',
    }
    
    video_id = await mock_youtube_client.upload_video("test.mp4", metadata)
    assert video_id.startswith("dry_run_")
    # API should NOT be called
    mock_youtube_client.service.videos().insert.assert_not_called()
