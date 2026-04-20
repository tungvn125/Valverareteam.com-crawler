import pytest

from vvr_scraper.social.db import SocialDatabaseManager


@pytest.mark.asyncio
async def test_social_db_creates_core_tables(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))

    await db.init_db()

    table_names = await db.list_table_names()
    assert set(table_names) >= {"users", "invite_codes", "reactions", "comments"}


@pytest.mark.asyncio
async def test_social_db_enables_wal_mode(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))

    await db.init_db()

    assert await db.get_journal_mode() == "wal"


@pytest.mark.asyncio
async def test_reaction_uniqueness_is_enforced(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    await db.create_reaction(user_id, "book-1", "chapter-1", "epubcfi(/6/2)", "heart")

    with pytest.raises(ValueError, match="already exists"):
        await db.create_reaction(user_id, "book-1", "chapter-1", "epubcfi(/6/2)", "heart")


@pytest.mark.asyncio
async def test_comment_replies_are_limited_to_one_level(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    parent_id = await db.create_comment(user_id, "book-1", "chapter-1", None, "root", None)
    child_id = await db.create_comment(user_id, "book-1", "chapter-1", None, "reply", parent_id)

    with pytest.raises(ValueError, match="one level deep"):
        await db.create_comment(user_id, "book-1", "chapter-1", None, "nested", child_id)


@pytest.mark.asyncio
async def test_create_reaction_rejects_invalid_type(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    with pytest.raises(ValueError, match="invalid reaction type"):
        await db.create_reaction(user_id, "book-1", "chapter-1", "anchor", "invalid")


@pytest.mark.asyncio
async def test_list_reactions_returns_created(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    await db.create_reaction(user_id, "book-1", "chapter-1", "anchor-1", "heart")
    await db.create_reaction(user_id, "book-1", "chapter-1", "anchor-2", "fire")

    reactions = await db.list_reactions("book-1", "chapter-1")
    assert len(reactions) == 2


@pytest.mark.asyncio
async def test_list_comments_returns_created(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    await db.create_comment(user_id, "book-1", "chapter-1", None, "hello", None)

    comments = await db.list_comments("book-1", "chapter-1")
    assert len(comments) == 1
    assert comments[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_get_comment_returns_none_for_missing(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    result = await db.get_comment("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_create_reaction_accepts_new_emoji_types(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    new_types = ["nerd", "laugh", "eyes", "pray", "sparkles"]
    for rt in new_types:
        rid = await db.create_reaction(user_id, "book-1", "chapter-1", f"anchor-{rt}", rt)
        reaction = await db.get_reaction(rid)
        assert reaction is not None
        assert reaction["reaction_type"] == rt


@pytest.mark.asyncio
async def test_create_reaction_still_rejects_unknown_emoji_type(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    with pytest.raises(ValueError, match="invalid reaction type"):
        await db.create_reaction(user_id, "book-1", "chapter-1", "anchor", "tableflip")
