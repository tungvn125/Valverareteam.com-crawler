import pytest

from vvr_scraper.social.auth import create_access_token, hash_password, verify_password
from vvr_scraper.social.db import SocialDatabaseManager


def test_password_hash_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_create_access_token_contains_subject_and_role(monkeypatch):
    monkeypatch.setenv("VVR_JWT_SECRET", "test-secret")

    token = create_access_token(user_id="u1", username="alice", role="admin")

    assert isinstance(token, str)
    assert token.count(".") == 2


@pytest.mark.asyncio
async def test_bootstrap_admin_from_env_code(tmp_path, monkeypatch):
    monkeypatch.setenv("VVR_ADMIN_CODE", "seed-admin")
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    user = await db.register_user_with_invite("seed-admin", "adminuser", "hashed", "Admin")

    assert user["role"] == "admin"


@pytest.mark.asyncio
async def test_register_with_invite_code(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    admin_id = await db.create_user_for_test("admin", role="admin")
    await db.create_invite_code("invite-123", admin_id, max_uses=1)

    user = await db.register_user_with_invite("invite-123", "newuser", "hashed", "New User")

    assert user["role"] == "member"
    assert user["username"] == "newuser"


@pytest.mark.asyncio
async def test_register_rejects_exhausted_invite(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    admin_id = await db.create_user_for_test("admin", role="admin")
    await db.create_invite_code("invite-123", admin_id, max_uses=1)
    await db.register_user_with_invite("invite-123", "user1", "hashed", "User 1")

    with pytest.raises(ValueError, match="exhausted"):
        await db.register_user_with_invite("invite-123", "user2", "hashed", "User 2")


@pytest.mark.asyncio
async def test_register_rejects_invalid_invite(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    await db.create_user_for_test("admin", role="admin")

    with pytest.raises(ValueError, match="invalid invite code"):
        await db.register_user_with_invite("bad-code", "user1", "hashed", "User 1")


@pytest.mark.asyncio
async def test_register_rejects_duplicate_username(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    await db.create_user_for_test("alice")

    with pytest.raises(ValueError, match="already taken"):
        await db.register_user_with_invite("some-code", "alice", "hashed", "Alice Too")


@pytest.mark.asyncio
async def test_create_admin_user(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    user = await db.create_admin_user(username="root", hashed_password="hashed", display_name="Root")

    assert user["role"] == "admin"
    assert user["username"] == "root"


@pytest.mark.asyncio
async def test_get_user_by_username(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    user_id = await db.create_user_for_test("alice")

    user = await db.get_user_by_username("alice")
    assert user is not None
    assert user["id"] == user_id


@pytest.mark.asyncio
async def test_get_user_by_id(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    user_id = await db.create_user_for_test("bob")

    user = await db.get_user_by_id(user_id)
    assert user is not None
    assert user["username"] == "bob"


@pytest.mark.asyncio
async def test_has_any_admin(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    assert await db.has_any_admin() is False

    await db.create_user_for_test("admin", role="admin")
    assert await db.has_any_admin() is True
