import pytest
import aiosqlite
import os
import asyncio
from vvr_scraper.db import DatabaseManager

@pytest.mark.asyncio
async def test_publishing_queue_table_exists():
    db_path = "test_publish.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db_manager = DatabaseManager(db_path)
    await db_manager.init_db()
    
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='publishing_queue'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 'publishing_queue'
    
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.mark.asyncio
async def test_upsert_publishing_task():
    db_path = "test_publish_upsert.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db_manager = DatabaseManager(db_path)
    await db_manager.init_db()
    
    task_data = {
        "novel_slug": "test-novel",
        "chapter_url": "https://valvrareteam.net/test-novel/chuong-1",
        "status": "PENDING"
    }
    
    # This method should be implemented in Task 2
    await db_manager.upsert_publishing_task(task_data)
    
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM publishing_queue WHERE novel_slug='test-novel'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row['chapter_url'] == task_data['chapter_url']
            assert row['status'] == 'PENDING'
            
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.mark.asyncio
async def test_get_novel_by_slug():
    db_path = "test_get_slug.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db_manager = DatabaseManager(db_path)
    await db_manager.init_db()
    
    novel_data = {
        "title": "Test Novel",
        "slug": "test-novel",
        "author": "Test Author",
        "last_chapter_count": 10,
        "output_folder": "test_folder",
        "formats": "mp3",
        "status": "synced",
        "cover_url": "test_url"
    }
    await db_manager.upsert_novel(novel_data)
    
    # Test existing slug
    novel = await db_manager.get_novel_by_slug("test-novel")
    assert novel is not None
    assert novel["title"] == "Test Novel"
    assert novel["last_chapter_count"] == 10
    
    # Test non-existing slug
    none_novel = await db_manager.get_novel_by_slug("non-existent")
    assert none_novel is None
    
    if os.path.exists(db_path):
        os.remove(db_path)

from unittest.mock import patch, AsyncMock
from vvr_scraper.publisher import Publisher

@pytest.mark.asyncio
async def test_sync_library_and_queue_new_chapters():
    db_path = "test_sync.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db_manager = DatabaseManager(db_path)
    await db_manager.init_db()
    
    # 1. Setup a novel in library with 1 chapter already known
    novel_data = {
        "title": "Test Sync Novel",
        "slug": "test-sync-novel",
        "last_chapter_count": 1,
        "cover_url": "test_url"
    }
    await db_manager.upsert_novel(novel_data)
    
    # 2. Mock tao_so_do_cay.get_chapter_tree_list to return 2 chapters
    mock_tree = [
        {
            "volume": "Vol 1",
            "chapters": [
                {"title": "Chapter 1", "url": "/test-sync-novel/chap-1", "locked": False},
                {"title": "Chapter 2", "url": "/test-sync-novel/chap-2", "locked": False}
            ]
        }
    ]
    
    publisher = Publisher(db_path=db_path)
    
    with patch("vvr_scraper.tao_so_do_cay.get_chapter_tree_list", new_callable=AsyncMock) as mock_get_tree:
        mock_get_tree.return_value = mock_tree
        
        # 3. Run sync
        await publisher.sync_library_and_queue_new_chapters()
        
        # 4. Verify chapter 2 is in queue
        pending_tasks = await db_manager.get_pending_tasks()
        # It should only have 1 NEW chapter (Chapter 2)
        assert len(pending_tasks) == 1
        assert pending_tasks[0]["chapter_url"] == "https://valvrareteam.net/test-sync-novel/chap-2"
        
        # 5. Verify library count is updated
        updated_novel = await db_manager.get_novel_by_slug("test-sync-novel")
        assert updated_novel["last_chapter_count"] == 2

    if os.path.exists(db_path):
        os.remove(db_path)
