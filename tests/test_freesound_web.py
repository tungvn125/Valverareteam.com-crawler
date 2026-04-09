from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from vvr_scraper.web import app


@pytest.fixture
def client():
    @asynccontextmanager
    async def noop_lifespan(a):
        a.state.db = AsyncMock()
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.router.lifespan_context = original


@patch("vvr_scraper.freesound_manager.FreesoundManager")
def test_freesound_auth_url(mock_fs_class, client):
    mock_instance = mock_fs_class.return_value
    mock_instance.get_auth_url.return_value = "https://freesound.org/authorize"

    response = client.get("/api/freesound/auth")
    assert response.status_code == 200
    assert response.json() == {"url": "https://freesound.org/authorize"}


@patch("vvr_scraper.freesound_manager.FreesoundManager")
def test_freesound_callback(mock_fs_class, client):
    mock_instance = mock_fs_class.return_value
    mock_instance.exchange_code = AsyncMock(return_value={"access_token": "test_token"})

    response = client.post("/api/freesound/callback", json={"code": "test_code"})
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Freesound authentication successful."}
