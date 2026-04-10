import asyncio
import uuid
from datetime import datetime
from typing import Any

import aiosqlite
from loguru import logger

from .enums import ALLOWED_NOVEL_COLUMNS


class DatabaseManager:
    def __init__(self, db_path: str = "vvr_library.db"):
        self.db_path = db_path
        self._db = None
        self._lock = asyncio.Lock()

    async def get_db(self):
        async with self._lock:
            if self._db is None:
                self._db = await aiosqlite.connect(self.db_path)
                self._db.row_factory = aiosqlite.Row
        return self._db

    async def init_db(self):
        db = await self.get_db()

        # Enable WAL mode for better concurrency
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                author TEXT,
                description TEXT,
                cover_url TEXT,
                status TEXT DEFAULT 'pending',
                last_chapter_count INTEGER DEFAULT 0,
                last_downloaded_at TEXT,
                output_folder TEXT,
                formats TEXT,
                genres TEXT
            )
        """)

        # Check if columns exist and add them if not (Robust upgrade logic)
        cursor = await db.execute("PRAGMA table_info(novels)")
        existing_columns = [row[1] for row in await cursor.fetchall()]

        expected_columns = [
            ("author", "TEXT"),
            ("description", "TEXT"),
            ("cover_url", "TEXT"),
            ("status", "TEXT DEFAULT 'pending'"),
            ("last_chapter_count", "INTEGER DEFAULT 0"),
            ("last_downloaded_at", "TEXT"),
            ("output_folder", "TEXT"),
            ("formats", "TEXT"),
            ("genres", "TEXT"),
            ("last_synced_count", "INTEGER DEFAULT 0"),
            ("server_chapter_count", "INTEGER DEFAULT 0"),
            ("has_updates", "INTEGER DEFAULT 0"),
            ("last_checked_at", "TEXT"),
        ]

        for col_name, col_def in expected_columns:
            if col_name not in existing_columns:
                await db.execute(f"ALTER TABLE novels ADD COLUMN {col_name} {col_def}")
                await db.commit()
                logger.info(f"Added column {col_name} to novels table.")

        # Audio drama specific tables
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
                task_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                payload TEXT,
                progress REAL DEFAULT 0.0,
                error_summary TEXT,
                error_log_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                alias_id TEXT,
                batch_id TEXT,
                depends_on TEXT,
                priority INTEGER DEFAULT 0,
                from_chapter INTEGER,
                to_chapter INTEGER
            )
        """)

        # Add new columns to jobs if they don't exist
        cursor = await db.execute("PRAGMA table_info(jobs)")
        existing_job_columns = [row[1] for row in await cursor.fetchall()]

        expected_job_columns = [
            ("alias_id", "TEXT"),
            ("batch_id", "TEXT"),
            ("depends_on", "TEXT"),
            ("priority", "INTEGER DEFAULT 0"),
            ("from_chapter", "INTEGER"),
            ("to_chapter", "INTEGER"),
            ("updated_at", "TEXT"),
            ("progress", "REAL DEFAULT 0.0"),
            ("error_summary", "TEXT"),
            ("error_log_path", "TEXT"),
        ]

        for col_name, col_def in expected_job_columns:
            if col_name not in existing_job_columns:
                try:
                    await db.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}")
                    await db.commit()
                    logger.info(f"Added column {col_name} to jobs table.")
                except Exception as e:
                    logger.warning(f"Could not add column {col_name} to jobs: {e}")

        await db.commit()

        # Legacy Migration: check if 'library' table exists
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library'")
        if await cursor.fetchone():
            logger.info("Migrating legacy 'library' table to 'novels'...")
            # Copy data (only columns we know exist in both)
            await db.execute("""
                INSERT INTO novels (title, slug)
                SELECT title, slug FROM library
                WHERE slug NOT IN (SELECT slug FROM novels)
            """)
            # Try to copy author if it exists in library
            cursor = await db.execute("PRAGMA table_info(library)")
            lib_cols = [row[1] for row in await cursor.fetchall()]
            if "author" in lib_cols:
                await db.execute("""
                    UPDATE novels
                    SET author = (SELECT author FROM library WHERE library.slug = novels.slug)
                    WHERE slug IN (SELECT slug FROM library) AND author IS NULL
                """)

            # Drop old table
            await db.execute("DROP TABLE library")
            await db.commit()
            logger.info("Legacy migration complete.")
        logger.info(f"Database initialized at {self.db_path} (WAL mode enabled)")

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def get_all_novels(
        self, page: int | None = None, size: int = 20, offset: int | None = None
    ) -> list[dict[str, Any]]:
        """Returns entries in the library with optional pagination."""
        db = await self.get_db()
        if page is not None:
            actual_offset = offset if offset is not None else (page - 1) * size
            query = "SELECT * FROM novels ORDER BY id LIMIT ? OFFSET ?"
            params = (size, actual_offset)
        else:
            query = "SELECT * FROM novels ORDER BY id"
            params = ()

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_newest_novels(
        self, limit: int = 20, page: int = 1, offset: int | None = None
    ) -> list[dict[str, Any]]:
        """Returns the newest novels based on last_downloaded_at with pagination."""
        db = await self.get_db()
        actual_offset = offset if offset is not None else (page - 1) * limit
        async with db.execute(
            "SELECT * FROM novels ORDER BY last_downloaded_at DESC LIMIT ? OFFSET ?", (limit, actual_offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def search_novels(self, query: str, page: int = 1, size: int = 20) -> list[dict[str, Any]]:
        """Searches for novels by title or author with pagination."""
        db = await self.get_db()
        search_query = f"%{query}%"
        offset = (page - 1) * size
        sql = """
            SELECT * FROM novels
            WHERE title LIKE ? OR author LIKE ?
            ORDER BY last_downloaded_at DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(sql, (search_query, search_query, size, offset)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_unique_genres(self) -> list[str]:
        """Returns a list of all unique genres in the library."""
        db = await self.get_db()
        async with db.execute("SELECT genres FROM novels WHERE genres IS NOT NULL") as cursor:
            rows = await cursor.fetchall()
            all_genres = set()
            for row in rows:
                if row[0]:
                    genres = [g.strip() for g in row[0].split(",")]
                    all_genres.update(genres)
            return sorted(list(all_genres))

    async def get_unique_authors(self) -> list[str]:
        """Returns a list of all unique authors in the library."""
        db = await self.get_db()
        async with db.execute("SELECT DISTINCT author FROM novels WHERE author IS NOT NULL") as cursor:
            rows = await cursor.fetchall()
            return sorted([row[0] for row in rows])

    async def get_all_story_voices(self, story_id: str) -> dict[str, str]:
        """Returns a mapping of character names to voice IDs for a story."""
        db = await self.get_db()
        async with db.execute(
            "SELECT character_name, voice_name FROM character_voices WHERE story_id = ?", (story_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    async def get_character_voice(self, story_id: str, character_name: str) -> str | None:
        """Returns the voice name for a specific character in a story."""
        db = await self.get_db()
        async with db.execute(
            "SELECT voice_name FROM character_voices WHERE story_id = ? AND character_name = ?",
            (story_id, character_name),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def save_character_voice(self, story_id: str, character_name: str, voice_name: str):
        """Saves or updates a character's voice assignment."""
        db = await self.get_db()
        await db.execute(
            "INSERT INTO character_voices (story_id, character_name, voice_name) VALUES (?, ?, ?) "
            "ON CONFLICT(story_id, character_name) DO UPDATE SET voice_name=excluded.voice_name",
            (story_id, character_name, voice_name),
        )
        await db.commit()

    async def get_novel_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Returns a single novel entry identified by its slug."""
        db = await self.get_db()
        async with db.execute("SELECT * FROM novels WHERE slug = ?", (slug,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_library_metadata(self, slug: str, metadata: dict[str, Any]):
        """Updates one or more metadata fields for a novel identified by its slug."""
        if not metadata:
            return

        db = await self.get_db()
        # Validate column names against whitelist to prevent SQL injection
        keys = [k for k in metadata.keys() if k in ALLOWED_NOVEL_COLUMNS]
        if not keys:
            logger.warning(f"No valid columns to update for slug: {slug}")
            return
        values = [metadata[k] for k in keys]

        set_clause = ", ".join(  # noqa: S608  — column names validated against whitelist
            [f"{key} = ?" for key in keys]
        )
        query = f"UPDATE novels SET {set_clause} WHERE slug = ?"  # noqa: S608
        params = values + [slug]
        async with db.execute(query, tuple(params)) as cursor:
            if cursor.rowcount == 0:
                logger.warning(f"No novel found with slug: {slug}")
        await db.commit()

    async def upsert_novel(self, novel_data: dict[str, Any]):
        """Inserts or updates a novel entry."""
        db = await self.get_db()

        # Check if exists
        slug = novel_data.get("slug")
        if not slug:
            return

        # Validate column names against whitelist
        columns = [c for c in novel_data.keys() if c in ALLOWED_NOVEL_COLUMNS | {"slug"}]
        if not columns:
            return
        filtered_data = {c: novel_data[c] for c in columns}
        placeholders = ", ".join(["?" for _ in columns])

        # Build update clause for ON CONFLICT  # noqa: S608  — columns validated above
        update_clause = ", ".join([f"{col}=excluded.{col}" for col in columns if col != "slug"])

        sql = f"""
            INSERT INTO novels ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(slug) DO UPDATE SET {update_clause}
        """  # noqa: S608

        await db.execute(sql, tuple(filtered_data.values()))
        await db.commit()

    async def create_job(
        self,
        task_type: str,
        payload: str,
        alias_id: str = None,
        batch_id: str = None,
        depends_on: str = None,
        priority: int = 0,
        from_chapter: int = None,
        to_chapter: int = None,
    ) -> str:
        """Creates a new job entry and returns its ID (UUID)."""
        job_id = str(uuid.uuid4())
        db = await self.get_db()
        await db.execute(
            """INSERT INTO jobs (
                id, task_type, payload, created_at, updated_at,
                alias_id, batch_id, depends_on, priority,
                from_chapter, to_chapter
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                task_type,
                payload,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                alias_id,
                batch_id,
                depends_on,
                priority,
                from_chapter,
                to_chapter,
            ),
        )
        await db.commit()
        return job_id

    async def update_job_status(
        self, job_id: str, status: str, progress: float = None, error_summary: str = None, error_log_path: str = None
    ):
        """Updates the status and metadata of a job."""
        db = await self.get_db()
        updates = ["status = ?", "updated_at = ?"]
        params = [status, datetime.now().isoformat()]

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if error_summary is not None:
            updates.append("error_summary = ?")
            params.append(error_summary)
        if error_log_path is not None:
            updates.append("error_log_path = ?")
            params.append(error_log_path)

        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"  # noqa: S608  — column names are hardcoded above
        await db.execute(query, tuple(params))
        await db.commit()

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Returns the current status of a job."""
        db = await self.get_db()
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_recent_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns the most recent jobs from the database."""
        db = await self.get_db()
        async with db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
