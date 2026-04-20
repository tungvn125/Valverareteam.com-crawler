"""
Tests for social auth and admin API routes.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vvr_scraper.social.db import SocialDatabaseManager
from vvr_scraper.social.router import RATE_BUCKETS
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


@pytest.fixture
def second_member_token(client, admin_token):
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
            json={"invite_code": code, "username": "secondmember", "password": "secret1234"},
        )
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def seeded_reaction_id(client, member_token):
    RATE_BUCKETS.clear()
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"anchor": "epubcfi(/6/4)", "reaction_type": "heart"},
        )
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture
def seeded_comment_id(client, member_token):
    RATE_BUCKETS.clear()
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"content": "seeded comment"},
        )
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture
def seeded_comments(client, member_token):
    RATE_BUCKETS.clear()
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        parent_resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"content": "parent comment"},
        )
    assert parent_resp.status_code == 200
    parent_id = parent_resp.json()["id"]

    RATE_BUCKETS.clear()
    with patch.dict(os.environ, {"VVR_JWT_SECRET": "test-secret-key-for-testing"}):
        reply_resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"content": "reply comment", "parent_id": parent_id},
        )
    assert reply_resp.status_code == 200
    return parent_id


class TestAuthRoutes:
    def test_register_returns_user_and_token(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "alice", "password": "secret1234"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["username"] == "alice"
        assert data["user"]["role"] == "admin"
        assert isinstance(data["token"], str)

    def test_register_with_invite_code(self, client, admin_token):
        invite_resp = client.post(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"max_uses": 5},
        )
        code = invite_resp.json()["code"]

        resp = client.post(
            "/api/auth/register",
            json={"invite_code": code, "username": "bob", "password": "secret1234"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "member"

    def test_register_rejects_duplicate_username(self, client):
        client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "alice", "password": "secret1234"},
        )
        resp = client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "alice", "password": "otherpass1"},
        )
        assert resp.status_code == 400

    def test_register_rejects_bad_invite_code(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"invite_code": "bad-code", "username": "charlie", "password": "secret1234"},
        )
        assert resp.status_code == 400

    def test_login_returns_token_for_valid_credentials(self, client):
        client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "alice", "password": "secret1234"},
        )
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "secret1234"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["token"], str)
        assert data["user"]["username"] == "alice"

    def test_login_rejects_wrong_password(self, client):
        client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "alice", "password": "secret1234"},
        )
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "wrongpass1"})
        assert resp.status_code == 401

    def test_login_rejects_unknown_user(self, client):
        resp = client.post("/api/auth/login", json={"username": "nobody", "password": "secret1234"})
        assert resp.status_code == 401

    def test_me_returns_current_user(self, client):
        reg = client.post(
            "/api/auth/register",
            json={"invite_code": "seed-admin", "username": "alice", "password": "secret1234"},
        )
        token = reg.json()["token"]
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "alice"

    def test_me_rejects_missing_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestAdminRoutes:
    def test_admin_can_create_invite(self, client, admin_token):
        resp = client.post(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"max_uses": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert data["max_uses"] == 3

    def test_admin_can_list_invites(self, client, admin_token):
        client.post(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"max_uses": 1},
        )
        resp = client.get(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        invites = resp.json()
        assert len(invites) >= 1

    def test_admin_invite_creation_requires_admin_role(self, client, member_token):
        resp = client.post(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"max_uses": 1},
        )
        assert resp.status_code == 403

    def test_admin_invite_listing_requires_admin_role(self, client, member_token):
        resp = client.get(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 403

    def test_admin_endpoints_require_auth(self, client):
        resp = client.post("/api/admin/invites", json={"max_uses": 1})
        assert resp.status_code == 401

        resp = client.get("/api/admin/invites")
        assert resp.status_code == 401


class TestReactionRoutes:
    def test_create_reaction_returns_created_payload(self, client, member_token):
        RATE_BUCKETS.clear()
        response = client.post(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"anchor": "epubcfi(/6/2)", "reaction_type": "heart"},
        )
        assert response.status_code == 200
        assert response.json()["reaction_type"] == "heart"

    def test_list_reactions_returns_grouped_by_anchor(self, client, member_token):
        RATE_BUCKETS.clear()
        client.post(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"anchor": "epubcfi(/6/2)", "reaction_type": "heart"},
        )
        resp = client.get(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        anchors = resp.json()["anchors"]
        assert "epubcfi(/6/2)" in anchors

    def test_delete_reaction_requires_owner(self, client, second_member_token, seeded_reaction_id):
        response = client.delete(
            f"/api/social/reactions/{seeded_reaction_id}",
            headers={"Authorization": f"Bearer {second_member_token}"},
        )
        assert response.status_code == 403

    def test_delete_reaction_by_owner_succeeds(self, client, member_token, seeded_reaction_id):
        response = client.delete(
            f"/api/social/reactions/{seeded_reaction_id}",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert response.status_code == 204

    def test_delete_nonexistent_reaction_returns_404(self, client, member_token):
        response = client.delete(
            "/api/social/reactions/nonexistent-id",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert response.status_code == 404

    def test_create_reaction_accepts_new_emoji_type(self, client, member_token):
        RATE_BUCKETS.clear()
        response = client.post(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"anchor": "epubcfi(/6/2)", "reaction_type": "nerd"},
        )
        assert response.status_code == 200
        assert response.json()["reaction_type"] == "nerd"


class TestCommentRoutes:
    def test_create_comment_supports_chapter_level_anchor(self, client, member_token):
        RATE_BUCKETS.clear()
        response = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"content": "First!"},
        )
        assert response.status_code == 200
        assert response.json()["anchor"] is None

    def test_update_comment_requires_owner(self, client, second_member_token, seeded_comment_id):
        response = client.put(
            f"/api/social/comments/{seeded_comment_id}",
            headers={"Authorization": f"Bearer {second_member_token}"},
            json={"content": "edited"},
        )
        assert response.status_code == 403

    def test_update_comment_by_owner_succeeds(self, client, member_token, seeded_comment_id):
        response = client.put(
            f"/api/social/comments/{seeded_comment_id}",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"content": "edited content"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "edited content"

    def test_delete_comment_requires_owner(self, client, second_member_token, seeded_comment_id):
        response = client.delete(
            f"/api/social/comments/{seeded_comment_id}",
            headers={"Authorization": f"Bearer {second_member_token}"},
        )
        assert response.status_code == 403

    def test_delete_comment_by_owner_succeeds(self, client, member_token, seeded_comment_id):
        response = client.delete(
            f"/api/social/comments/{seeded_comment_id}",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert response.status_code == 204

    def test_list_comments_returns_replies_nested_under_parent(self, client, member_token, seeded_comments):
        response = client.get(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        parent = [c for c in data if c["id"] == seeded_comments][0]
        assert len(parent["replies"]) == 1
        assert parent["replies"][0]["content"] == "reply comment"

    def test_delete_nonexistent_comment_returns_404(self, client, member_token):
        response = client.delete(
            "/api/social/comments/nonexistent-id",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert response.status_code == 404


class TestRateLimiting:
    def test_reaction_rate_limit(self, client, member_token):
        RATE_BUCKETS.clear()
        headers = {"Authorization": f"Bearer {member_token}"}
        for i in range(5):
            resp = client.post(
                "/api/social/books/book-1/chapters/ch-1/reactions",
                headers=headers,
                json={"anchor": f"anchor-{i}", "reaction_type": "heart"},
            )
            assert resp.status_code == 200
        resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers=headers,
            json={"anchor": "anchor-6", "reaction_type": "heart"},
        )
        assert resp.status_code == 429

    def test_comment_rate_limit(self, client, member_token):
        RATE_BUCKETS.clear()
        headers = {"Authorization": f"Bearer {member_token}"}
        resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers=headers,
            json={"content": "first"},
        )
        assert resp.status_code == 200
        resp = client.post(
            "/api/social/books/book-1/chapters/ch-1/comments",
            headers=headers,
            json={"content": "second"},
        )
        assert resp.status_code == 429
