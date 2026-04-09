import logging

import aiosqlite
import pytest
from loguru import logger

from vvr_scraper.db import DatabaseManager


@pytest.fixture
def caplog_loguru(caplog):
    class PropagateHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    handler_id = logger.add(caplog.handler, format="{message}", level="DEBUG")
    yield caplog
    logger.remove(handler_id)


@pytest.fixture
async def db_manager(tmp_path):
    db_path = tmp_path / "test_library.db"
    manager = DatabaseManager(str(db_path))
    return manager


@pytest.mark.asyncio
async def test_init_db_adds_columns(tmp_path):
    db_path = tmp_path / "test_migration.db"

    # 1. Create DB with old schema (subset of columns)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("""
            CREATE TABLE library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE,
                title TEXT
            )
        """)
        await db.commit()

    # 2. Initialize with DatabaseManager (should run migration)
    manager = DatabaseManager(str(db_path))
    await manager.init_db()

    # 3. Verify columns exist
    async with aiosqlite.connect(str(db_path)) as db:
        async with db.execute("PRAGMA table_info(novels)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]

    assert "last_synced_count" in columns
    assert "server_chapter_count" in columns
    assert "has_updates" in columns
    assert "last_checked_at" in columns
    assert "genres" in columns
    assert "description" in columns


@pytest.mark.asyncio
async def test_update_library_metadata(db_manager):
    await db_manager.init_db()

    # Insert a test novel
    await db_manager.upsert_novel(
        {"slug": "test-novel", "title": "Test Novel", "author": "Author", "last_chapter_count": 10}
    )

    # Update metadata
    update_data = {
        "last_synced_count": 5,
        "server_chapter_count": 12,
        "has_updates": 1,
        "last_checked_at": "2023-10-27T10:00:00",
    }
    await db_manager.update_library_metadata("test-novel", update_data)

    # Verify updates
    novels = await db_manager.get_all_novels()
    test_novel = next(n for n in novels if n["slug"] == "test-novel")

    assert test_novel["last_synced_count"] == 5
    assert test_novel["server_chapter_count"] == 12
    assert test_novel["has_updates"] == 1
    assert test_novel["last_checked_at"] == "2023-10-27T10:00:00"


@pytest.mark.asyncio
async def test_update_library_metadata_nonexistent_slug(db_manager, caplog_loguru):
    await db_manager.init_db()
    await db_manager.update_library_metadata("non-existent", {"has_updates": 1})
    assert "No novel found with slug: non-existent" in caplog_loguru.text


@pytest.mark.asyncio
async def test_get_novel_by_slug(db_manager):
    await db_manager.init_db()

    novel_data = {
        "title": "Test Novel",
        "slug": "truyen/test-novel-12345678",
        "author": "Test Author",
        "output_folder": "novels/Test Novel",
    }
    await db_manager.upsert_novel(novel_data)

    retrieved = await db_manager.get_novel_by_slug("truyen/test-novel-12345678")
    assert retrieved is not None
    assert retrieved["title"] == "Test Novel"

    # Non-existent slug
    assert await db_manager.get_novel_by_slug("non-existent") is None
