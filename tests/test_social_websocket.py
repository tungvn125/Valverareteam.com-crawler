import os
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vvr_scraper.social.db import SocialDatabaseManager
from vvr_scraper.web import app


@pytest.fixture
def social_db(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social_test.db"))
    return db


@pytest.fixture
def client(social_db):
    @asynccontextmanager
    async def test_lifespan(a):
        await social_db.init_db()
        a.state.social_db = social_db
        a.state.db = None
        try:
            yield
        finally:
            await social_db.close()

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = test_lifespan
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.router.lifespan_context = original_lifespan


@pytest.fixture
def admin_token(client):
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        resp = client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "adminuser", "password": "secret1234"},
        )
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def member_token(client, admin_token):
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        invite_resp = client.post(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"max_uses": 5},
        )
    assert invite_resp.status_code == 200
    code = invite_resp.json()["code"]

    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        resp = client.post(
            "/api/auth/register",
            json={"invite_code": code, "username": "memberuser", "password": "secret1234"},
        )
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture(autouse=True)
def _set_jwt_secret():
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing", "VVR_ADMIN_CODE": "seed-admin"}):
        yield


def test_reaction_broadcast_is_scoped_to_same_chapter(client, member_token):
    with client.websocket_connect("/ws/social/book-1/ch-1") as ws_same:
        with client.websocket_connect("/ws/social/book-1/ch-2") as ws_other:
            response = client.post(
                "/api/social/books/book-1/chapters/ch-1/reactions",
                headers={"Authorization": f"Bearer {member_token}"},
                json={"anchor": "epubcfi(/6/2)", "reaction_type": "heart"},
            )
            assert response.status_code == 200
            msg = ws_same.receive_json()
            assert msg["type"] == "reaction"
            assert msg["data"]["reaction_type"] == "heart"
            ws_other.send_text("ping")


def test_comment_broadcast_is_scoped_to_same_chapter(client, member_token):
    with client.websocket_connect("/ws/social/book-1/ch-1") as ws:
        response = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"content": "Hello!"},
        )
        assert response.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "comment"
        assert msg["data"]["content"] == "Hello!"
