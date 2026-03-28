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
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS publishing_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    novel_slug TEXT,
                    chapter_url TEXT UNIQUE,
                    status TEXT DEFAULT 'PENDING',
                    audio_path TEXT,
                    video_path TEXT,
                    ai_metadata_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                    last_chapter_count=COALESCE(excluded.last_chapter_count, library.last_chapter_count),
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

    async def get_novel_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Returns a novel entry by its slug."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM library WHERE slug = ?", (slug,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

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

    async def upsert_publishing_task(self, task_data: Dict[str, Any]):
        """Inserts or updates a publishing task."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO publishing_queue (
                    novel_slug, chapter_url, status, audio_path, video_path, ai_metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter_url) DO UPDATE SET
                    status=excluded.status,
                    audio_path=COALESCE(excluded.audio_path, publishing_queue.audio_path),
                    video_path=COALESCE(excluded.video_path, publishing_queue.video_path),
                    ai_metadata_json=COALESCE(excluded.ai_metadata_json, publishing_queue.ai_metadata_json),
                    updated_at=excluded.updated_at
            """, (
                task_data.get('novel_slug'),
                task_data.get('chapter_url'),
                task_data.get('status', 'PENDING'),
                task_data.get('audio_path'),
                task_data.get('video_path'),
                task_data.get('ai_metadata_json'),
                datetime.now().isoformat()
            ))
            await db.commit()

    async def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Returns all pending publishing tasks."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM publishing_queue WHERE status != 'PUBLISHED'") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_task_by_url(self, chapter_url: str) -> Optional[Dict[str, Any]]:
        """Returns a publishing task by its chapter URL."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM publishing_queue WHERE chapter_url = ?", (chapter_url,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_task_status(self, chapter_url: str, status: str, **kwargs):
        """Updates the status and other fields of a publishing task."""
        async with aiosqlite.connect(self.db_path) as db:
            set_clauses = ["status = ?", "updated_at = ?"]
            params = [status, datetime.now().isoformat()]
            
            for key, value in kwargs.items():
                set_clauses.append(f"{key} = ?")
                params.append(value)
            
            params.append(chapter_url)
            query = f"UPDATE publishing_queue SET {', '.join(set_clauses)} WHERE chapter_url = ?"
            await db.execute(query, params)
            await db.commit()
