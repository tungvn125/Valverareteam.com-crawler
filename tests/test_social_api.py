"""
Tests for social auth and admin API routes.
"""

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
