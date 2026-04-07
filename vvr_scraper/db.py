import aiosqlite
import os
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger

class DatabaseManager:
    def __init__(self, db_path: str = "vvr_library.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def get_db(self) -> aiosqlite.Connection:
        """Returns the persistent database connection, initializing it if needed."""
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def close(self):
        """Closes the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def init_db(self):
        """Initializes the database and creates necessary tables if they don't exist."""
        db = await self.get_db()
        
        # Performance: Enable WAL mode for production concurrency
        await db.execute("PRAGMA journal_mode=WAL")
        
        # Migration: Rename library to novels if it exists
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library'") as cursor:
            if await cursor.fetchone():
                try:
                    await db.execute("ALTER TABLE library RENAME TO novels")
                    logger.info("Renamed library table to novels.")
                except aiosqlite.OperationalError as e:
                    logger.error(f"Failed to rename library table: {e}")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                slug TEXT UNIQUE,
                author TEXT,
                genres TEXT,
                description TEXT,
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
            ("last_checked_at", "TEXT"),
            ("genres", "TEXT"),
            ("description", "TEXT")
        ]
        
        cursor = await db.execute("PRAGMA table_info(novels)")
        existing_columns = [row[1] for row in await cursor.fetchall()]
        
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    await db.execute(f"ALTER TABLE novels ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to novels table.")
                except aiosqlite.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug(f"Column {col_name} already exists in novels table.")
                    else:
                        logger.error(f"Error adding column {col_name}: {e}")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS character_voices (
                story_id TEXT,
                character_name TEXT,
                voice_name TEXT,
                PRIMARY KEY (story_id, character_name)
            )
        """)

        # Job Management Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                task_type TEXT,
                status TEXT,
                progress REAL DEFAULT 0.0,
                payload TEXT,
                error_summary TEXT,
                error_log_path TEXT,
                created_at TEXT,
                finished_at TEXT
            )
        """)
        await db.commit()
        logger.info(f"Database initialized at {self.db_path} (WAL mode enabled)")

    async def create_job(self, task_type: str, payload: str) -> str:
        """Creates a new job entry and returns its ID (UUID)."""
        job_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        db = await self.get_db()
        await db.execute(
            "INSERT INTO jobs (id, task_type, status, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, task_type, "pending", payload, created_at)
        )
        await db.commit()
        return job_id

    async def update_job_status(self, job_id: str, status: str, progress: float = None, 
                               error_summary: str = None, error_log_path: str = None):
        """Updates the status and metadata of a job."""
        db = await self.get_db()
        finished_at = None
        if status in ("success", "failed"):
            finished_at = datetime.now().isoformat()
            
        sql = "UPDATE jobs SET status = ?"
        params = [status]
        
        if progress is not None:
            sql += ", progress = ?"
            params.append(progress)
        if error_summary is not None:
            sql += ", error_summary = ?"
            params.append(error_summary)
        if error_log_path is not None:
            sql += ", error_log_path = ?"
            params.append(error_log_path)
        if finished_at:
            sql += ", finished_at = ?"
            params.append(finished_at)
            
        sql += " WHERE id = ?"
        params.append(job_id)
        
        await db.execute(sql, tuple(params))
        await db.commit()

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Returns the current status of a job."""
        db = await self.get_db()
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_recent_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent jobs from the database."""
        db = await self.get_db()
        async with db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", 
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_library_metadata(self, slug: str, metadata: Dict[str, Any]):
        """Updates one or more metadata fields for a novel identified by its slug."""
        if not metadata:
            return

        db = await self.get_db()
        keys = list(metadata.keys())
        values = list(metadata.values())
        
        set_clause = ", ".join([f"{key} = ?" for key in keys])
        query = f"UPDATE novels SET {set_clause} WHERE slug = ?"
        params = values + [slug]
        await db.execute(query, tuple(params))
        await db.commit()

    async def upsert_novel(self, novel_data: Dict[str, Any]):
        """Inserts or updates a novel entry."""
        db = await self.get_db()
        await db.execute("""
            INSERT INTO novels (
                title, slug, author, last_chapter_count, last_downloaded_at,
                output_folder, formats, status, cover_url, genres, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title=excluded.title,
                author=excluded.author,
                last_chapter_count=excluded.last_chapter_count,
                last_downloaded_at=excluded.last_downloaded_at,
                output_folder=excluded.output_folder,
                formats=excluded.formats,
                status=excluded.status,
                cover_url=excluded.cover_url,
                genres=excluded.genres,
                description=excluded.description
        """, (
            novel_data.get('title'),
            novel_data.get('slug'),
            novel_data.get('author'),
            novel_data.get('last_chapter_count'),
            novel_data.get('last_downloaded_at', datetime.now().isoformat()),
            novel_data.get('output_folder'),
            novel_data.get('formats'),
            novel_data.get('status', 'synced'),
            novel_data.get('cover_url'),
            novel_data.get('genres'),
            novel_data.get('description')
        ))
        await db.commit()

    async def get_all_novels(self, page: Optional[int] = None, size: int = 20) -> List[Dict[str, Any]]:
        """Returns entries in the library with optional pagination."""
        db = await self.get_db()
        if page is not None:
            offset = (page - 1) * size
            query = "SELECT * FROM novels ORDER BY id LIMIT ? OFFSET ?"
            params = (size, offset)
        else:
            query = "SELECT * FROM novels ORDER BY id"
            params = ()
            
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def search_novels(self, query: str, page: int = 1, size: int = 20) -> List[Dict[str, Any]]:
        """Searches for novels by title or author with pagination."""
        db = await self.get_db()
        search_query = f"%{query}%"
        sql = """
            SELECT * FROM novels 
            WHERE title LIKE ? OR author LIKE ? 
            ORDER BY last_downloaded_at DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(sql, (search_query, search_query, size, (page - 1) * size)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_novel_status(self, slug: str, status: str, last_chapter_count: int = None):
        """Updates specific fields for a novel."""
        db = await self.get_db()
        if last_chapter_count is not None:
            await db.execute(
                "UPDATE novels SET status = ?, last_chapter_count = ? WHERE slug = ?",
                (status, last_chapter_count, slug)
            )
        else:
            await db.execute(
                "UPDATE novels SET status = ? WHERE slug = ?",
                (status, slug)
            )
        await db.commit()

    async def get_newest_novels(self, limit: int = 20, page: int = 1) -> List[Dict[str, Any]]:
        """Returns the newest novels based on last_downloaded_at with pagination."""
        db = await self.get_db()
        size = limit # Fixed size for pagination
        offset = (page - 1) * size
        async with db.execute(
            "SELECT * FROM novels ORDER BY last_downloaded_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_unique_genres(self) -> List[str]:
        """Returns a list of unique genres from all novels."""
        db = await self.get_db()
        async with db.execute("SELECT genres FROM novels WHERE genres IS NOT NULL AND genres != ''") as cursor:
            rows = await cursor.fetchall()
            genres_set = set()
            for row in rows:
                if row[0]:
                    parts = [p.strip() for p in row[0].split(",") if p.strip()]
                    genres_set.update(parts)
            return sorted(list(genres_set))

    async def get_unique_authors(self) -> List[str]:
        """Returns a list of unique authors from all novels."""
        db = await self.get_db()
        async with db.execute(
            "SELECT DISTINCT author FROM novels WHERE author IS NOT NULL AND author != '' ORDER BY author"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_all_story_voices(self, story_id: str) -> Dict[str, str]:
        """Returns a mapping of character names to voice IDs for a story."""
        db = await self.get_db()
        async with db.execute(
            "SELECT character_name, voice_name FROM character_voices WHERE story_id = ?",
            (story_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    async def save_character_voice(self, story_id: str, character_name: str, voice_name: str):
        """Saves or updates a character's voice assignment."""
        db = await self.get_db()
        await db.execute(
            "INSERT INTO character_voices (story_id, character_name, voice_name) VALUES (?, ?, ?) "
            "ON CONFLICT(story_id, character_name) DO UPDATE SET voice_name=excluded.voice_name",
            (story_id, character_name, voice_name)
        )
        await db.commit()
