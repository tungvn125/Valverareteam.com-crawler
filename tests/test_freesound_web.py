import pytest
from fastapi.testclient import TestClient
from vvr_scraper.web import app
from unittest.mock import patch, MagicMock, AsyncMock

client = TestClient(app)

@patch("vvr_scraper.web.FreesoundManager")
def test_freesound_auth_url(mock_fs_class):
    mock_instance = mock_fs_class.return_value
    mock_instance.get_auth_url.return_value = "https://freesound.org/authorize"
    
    response = client.get("/api/freesound/auth")
    assert response.status_code == 200
    assert response.json() == {"url": "https://freesound.org/authorize"}

@patch("vvr_scraper.web.FreesoundManager")
@pytest.mark.asyncio
async def test_freesound_callback(mock_fs_class):
    mock_instance = mock_fs_class.return_value
    mock_instance.exchange_code = AsyncMock(return_value={"access_token": "test_token"})
    
    # Simulate async call if it's awaited in the endpoint
    # Note: If it's not awaited, we need to handle it accordingly.
    # Looking at freesound_manager.py, exchange_code IS async.
    
    # Since FastAPI endpoints are usually async, and we're using TestClient,
    # it's usually handled for us.
    
    response = client.post("/api/freesound/callback", json={"code": "test_code"})
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Freesound authentication successful."}
