import aiosqlite
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger

class DatabaseManager:
    def __init__(self, db_path: str = "vvr_library.db"):
        self.db_path = db_path

    async def init_db(self):
        """Initializes the database and creates the library table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    slug TEXT UNIQUE,
                    author TEXT,
                    last_chapter_count INTEGER,
                    last_downloaded_at DATETIME,
                    output_folder TEXT,
                    formats TEXT,
                    status TEXT,
                    cover_url TEXT
                )
            """)
            await db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def upsert_novel(self, novel_data: Dict[str, Any]):
        """Inserts or updates a novel entry based on the slug."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO library (
                    title, slug, author, last_chapter_count, 
                    last_downloaded_at, output_folder, formats, status, cover_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    last_chapter_count=excluded.last_chapter_count,
                    last_downloaded_at=excluded.last_downloaded_at,
                    output_folder=excluded.output_folder,
                    formats=excluded.formats,
                    status=excluded.status,
                    cover_url=excluded.cover_url
            """, (
                novel_data.get('title'),
                novel_data.get('slug'),
                novel_data.get('author'),
                novel_data.get('last_chapter_count'),
                novel_data.get('last_downloaded_at', datetime.now().isoformat()),
                novel_data.get('output_folder'),
                novel_data.get('formats'),
                novel_data.get('status', 'synced'),
                novel_data.get('cover_url')
            ))
            await db.commit()

    async def get_all_novels(self) -> List[Dict[str, Any]]:
        """Returns all entries in the library."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM library") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_novel_status(self, slug: str, status: str, last_chapter_count: int = None):
        """Updates specific fields for a novel."""
        async with aiosqlite.connect(self.db_path) as db:
            if last_chapter_count is not None:
                await db.execute(
                    "UPDATE library SET status = ?, last_chapter_count = ? WHERE slug = ?",
                    (status, last_chapter_count, slug)
                )
            else:
                await db.execute(
                    "UPDATE library SET status = ? WHERE slug = ?",
                    (status, slug)
                )
            await db.commit()
