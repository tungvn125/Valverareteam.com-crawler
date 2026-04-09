import json
from unittest.mock import MagicMock, patch

import pytest

from vvr_scraper.freesound_manager import FreesoundManager


@pytest.fixture
def manager(tmp_path):
    auth_file = tmp_path / "auth.json"
    return FreesoundManager(client_id="test_id", client_secret="test_secret", auth_file=str(auth_file))


def test_get_auth_url(manager):
    url = manager.get_auth_url()
    assert "freesound.org/apiv2/oauth2/authorize" in url
    assert "client_id=test_id" in url
    assert "response_type=code" in url


@pytest.mark.asyncio
async def test_exchange_code_success(manager):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 3600,
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        token = await manager.exchange_code("test_code")

        assert token["access_token"] == "new_access_token"
        assert manager.token == token
        # Verify it was saved
        with open(manager.auth_file) as f:
            saved = json.load(f)
            assert saved == token

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["code"] == "test_code"
        assert kwargs["data"]["client_id"] == "test_id"
        assert kwargs["data"]["client_secret"] == "test_secret"
        assert kwargs["data"]["grant_type"] == "authorization_code"


@pytest.mark.asyncio
async def test_exchange_code_failure(manager):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Invalid code"

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(Exception, match="Failed to exchange code: Invalid code"):
            await manager.exchange_code("invalid_code")
