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
            
            # Migration: Add new columns if they don't exist
            new_columns = [
                ("last_synced_count", "INTEGER DEFAULT 0"),
                ("server_chapter_count", "INTEGER DEFAULT 0"),
                ("has_updates", "INTEGER DEFAULT 0"),
                ("last_checked_at", "TEXT")
            ]
            
            for col_name, col_type in new_columns:
                try:
                    await db.execute(f"ALTER TABLE library ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to library table.")
                except aiosqlite.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug(f"Column {col_name} already exists in library table.")
                    else:
                        raise e

            await db.execute("""
                CREATE TABLE IF NOT EXISTS character_voices (
                    story_id TEXT,
                    character_name TEXT,
                    voice_name TEXT,
                    PRIMARY KEY (story_id, character_name)
                )
            """)
            await db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def update_library_metadata(self, slug: str, metadata: Dict[str, Any]):
        """Updates one or more metadata fields for a novel identified by its slug."""
        if not metadata:
            return

        keys = list(metadata.keys())
        values = list(metadata.values())
        
        set_clause = ", ".join([f"{key} = ?" for key in keys])
        query = f"UPDATE library SET {set_clause} WHERE slug = ?"
        params = values + [slug]

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                if cursor.rowcount == 0:
                    logger.warning(f"No novel found with slug: {slug} to update metadata.")
            await db.commit()

    async def save_character_voice(self, story_id: str, character_name: str, voice_name: str):
        """Saves or updates a voice mapping for a character in a story."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO character_voices (story_id, character_name, voice_name)
                VALUES (?, ?, ?)
                ON CONFLICT(story_id, character_name) DO UPDATE SET voice_name=excluded.voice_name
            """, (story_id, character_name, voice_name))
            await db.commit()

    async def get_character_voice(self, story_id: str, character_name: str) -> Optional[str]:
        """Retrieves the voice name for a character in a story."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT voice_name FROM character_voices WHERE story_id = ? AND character_name = ?",
                (story_id, character_name)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_all_story_voices(self, story_id: str) -> Dict[str, str]:
        """Retrieves all character to voice mappings for a story."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT character_name, voice_name FROM character_voices WHERE story_id = ?",
                (story_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}

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
