import pytest
import aiosqlite
import os
from vvr_scraper.db import DatabaseManager

@pytest.mark.asyncio
async def test_novels_table_has_genres_and_description(tmp_path):
    db_path = str(tmp_path / "test_vvr_library.db")
    db_manager = DatabaseManager(db_path)
    
    # Initialize DB
    await db_manager.init_db()
    
    # Check for genres and description columns in 'novels' table
    async with aiosqlite.connect(db_path) as db:
        try:
            cursor = await db.execute("PRAGMA table_info(novels)")
            columns = [row[1] for row in await cursor.fetchall()]
            
            assert "genres" in columns, "Column 'genres' not found in 'novels' table"
            assert "description" in columns, "Column 'description' not found in 'novels' table"
        except Exception as e:
            await db_manager.close()
            raise e
    
    await db_manager.close()

@pytest.mark.asyncio
async def test_migration_from_library_table(tmp_path):
    db_path = str(tmp_path / "test_migration.db")
    
    # Manually create the old 'library' table
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                slug TEXT UNIQUE,
                author TEXT
            )
        """)
        await db.execute("INSERT INTO library (title, slug, author) VALUES (?, ?, ?)", 
                         ("Old Novel", "old-novel", "Old Author"))
        await db.commit()
    
    db_manager = DatabaseManager(db_path)
    
    # Initialize DB (should trigger migration)
    await db_manager.init_db()
    
    # Check if 'novels' table exists and contains the data
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM novels WHERE slug = ?", ("old-novel",)) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["title"] == "Old Novel"
            assert row["author"] == "Old Author"
            
            # Check for new columns
            columns = list(row.keys())
            assert "genres" in columns
            assert "description" in columns
            
        # Check if 'library' table is gone
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library'") as cursor:
            assert await cursor.fetchone() is None
            
    await db_manager.close()
