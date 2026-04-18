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
