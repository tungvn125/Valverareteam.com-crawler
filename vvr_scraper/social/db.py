import asyncio

import aiosqlite
from loguru import logger


class SocialDatabaseManager:
    def __init__(self, db_path: str):
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
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, hashed_password TEXT NOT NULL, invite_code_used TEXT, role TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS invite_codes (code TEXT PRIMARY KEY, created_by TEXT NOT NULL, used_by TEXT, max_uses INTEGER NOT NULL DEFAULT 1, use_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS reactions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, book_slug TEXT NOT NULL, chapter_id TEXT NOT NULL, anchor TEXT NOT NULL, reaction_type TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id, book_slug, chapter_id, anchor, reaction_type))"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS comments (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, book_slug TEXT NOT NULL, chapter_id TEXT NOT NULL, anchor TEXT, parent_id TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        await db.commit()
        logger.info(f"Social database initialized at {self.db_path}")

    async def list_table_names(self) -> list[str]:
        db = await self.get_db()
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_journal_mode(self) -> str:
        db = await self.get_db()
        async with db.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
        return str(row[0]).lower()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
