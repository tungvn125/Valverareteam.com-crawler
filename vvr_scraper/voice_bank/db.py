"""Voice Bank Database Manager using aiosqlite."""

import asyncio
import os
import uuid
from datetime import UTC, datetime

import aiosqlite
from loguru import logger


class VoiceBankDatabaseManager:
    """Manages voice_samples, voice_votes, and voice_tags tables in voice_bank.db."""

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
        """Create tables and indexes with WAL mode."""
        db = await self.get_db()
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys = ON")

        await db.execute(
            """CREATE TABLE IF NOT EXISTS voice_samples (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                ref_audio_path TEXT NOT NULL,
                ref_text TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                sample_rate INTEGER NOT NULL,
                gender TEXT NOT NULL,
                age_group TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'vi',
                mood TEXT,
                visibility TEXT NOT NULL DEFAULT 'private',
                usage_count INTEGER NOT NULL DEFAULT 0,
                file_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

        await db.execute(
            """CREATE TABLE IF NOT EXISTS voice_votes (
                voice_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                vote INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (voice_id, user_id),
                FOREIGN KEY (voice_id) REFERENCES voice_samples(id) ON DELETE CASCADE
            )"""
        )

        await db.execute(
            """CREATE TABLE IF NOT EXISTS voice_tags (
                voice_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (voice_id, tag),
                FOREIGN KEY (voice_id) REFERENCES voice_samples(id) ON DELETE CASCADE
            )"""
        )

        # Indexes
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_voices_community ON voice_samples(visibility)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_voices_user ON voice_samples(user_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_voices_gender_age ON voice_samples(gender, age_group)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tags_tag ON voice_tags(tag)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_voices_file_hash ON voice_samples(user_id, file_hash)"
        )

        await db.commit()
        logger.info(f"Voice bank database initialized at {self.db_path}")

    async def list_table_names(self) -> list[str]:
        db = await self.get_db()
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def create_voice_sample(
        self,
        user_id: str,
        name: str,
        description: str,
        ref_audio_path: str,
        ref_text: str,
        duration_ms: int,
        sample_rate: int,
        gender: str,
        age_group: str,
        language: str = "vi",
        mood: str | None = None,
        visibility: str = "private",
        file_hash: str = "",
    ) -> str:
        """Insert a new voice sample. Raises ValueError if duplicate file_hash for same user."""
        voice_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        # Check for duplicate file_hash per user
        existing = await self.get_voice_by_hash(user_id, file_hash)
        if existing:
            raise ValueError("Duplicate voice sample")

        db = await self.get_db()
        await db.execute(
            """INSERT INTO voice_samples
                (id, user_id, name, description, ref_audio_path, ref_text, duration_ms,
                 sample_rate, gender, age_group, language, mood, visibility, usage_count,
                 file_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                voice_id, user_id, name, description or "", ref_audio_path, ref_text,
                duration_ms, sample_rate, gender, age_group, language, mood, visibility,
                file_hash, now, now,
            ),
        )
        await db.commit()
        return voice_id

    async def get_voice_sample(self, voice_id: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT * FROM voice_samples WHERE id = ?", (voice_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        result["tags"] = await self.get_tags(voice_id)
        result["vote_score"] = await self.get_vote_score(voice_id)
        return result

    async def get_voice_by_hash(self, user_id: str, file_hash: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT * FROM voice_samples WHERE user_id = ? AND file_hash = ?",
            (user_id, file_hash),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_my_voices(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> dict:
        """List voice samples owned by user_id with pagination."""
        db = await self.get_db()

        # Get total count
        cursor = await db.execute(
            "SELECT COUNT(*) FROM voice_samples WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        total = row[0]

        # Get items
        cursor = await db.execute(
            """SELECT * FROM voice_samples
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        )
        rows = await cursor.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["tags"] = await self.get_tags(item["id"])
            item["vote_score"] = await self.get_vote_score(item["id"])
            items.append(item)

        return {"items": items, "total": total}

    async def list_community_voices(
        self,
        limit: int = 20,
        offset: int = 0,
        tags: list[str] | None = None,
        gender: str | None = None,
        age_group: str | None = None,
        sort: str = "votes",
    ) -> dict:
        """List public voice samples with optional filters."""
        db = await self.get_db()

        conditions = ["visibility = 'public'"]
        params: list = []

        if gender:
            conditions.append("gender = ?")
            params.append(gender)
        if age_group:
            conditions.append("age_group = ?")
            params.append(age_group)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM voice_samples WHERE {where_clause}"
        cursor = await db.execute(count_sql, params)
        row = await cursor.fetchone()
        total = row[0]

        # Build ordering
        if sort == "votes":
            order_sql = """ORDER BY
                (SELECT COALESCE(SUM(vote), 0) FROM voice_votes WHERE voice_id = voice_samples.id) DESC,
                usage_count DESC, created_at DESC"""
        else:
            order_sql = "ORDER BY created_at DESC"

        # Get items
        sql = f"""SELECT * FROM voice_samples WHERE {where_clause} {order_sql} LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["tags"] = await self.get_tags(item["id"])
            item["vote_score"] = await self.get_vote_score(item["id"])
            items.append(item)

        # Filter by tags if specified
        if tags:
            filtered_items = []
            for item in items:
                item_tags = set(item["tags"])
                if any(t in item_tags for t in tags):
                    filtered_items.append(item)
            items = filtered_items
            total = len(items)

        return {"items": items, "total": total}

    async def publish_voice(self, voice_id: str, user_id: str) -> None:
        """Set visibility to 'public'. Owner only."""
        db = await self.get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE voice_samples SET visibility = 'public', updated_at = ? WHERE id = ? AND user_id = ?",
            (now, voice_id, user_id),
        )
        await db.commit()

    async def delist_voice(self, voice_id: str, user_id: str) -> None:
        """Set visibility to 'delisted'. Owner only."""
        db = await self.get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE voice_samples SET visibility = 'delisted', updated_at = ? WHERE id = ? AND user_id = ?",
            (now, voice_id, user_id),
        )
        await db.commit()

    async def delete_voice_sample(self, voice_id: str, user_id: str) -> None:
        """Delete a voice sample and its associated tags and votes. Owner only."""
        db = await self.get_db()
        # Explicitly delete tags and votes first (cascade delete may not be reliable across connections)
        await db.execute("DELETE FROM voice_tags WHERE voice_id = ?", (voice_id,))
        await db.execute("DELETE FROM voice_votes WHERE voice_id = ?", (voice_id,))
        await db.execute(
            "DELETE FROM voice_samples WHERE id = ? AND user_id = ?",
            (voice_id, user_id),
        )
        await db.commit()

    async def vote_voice(self, voice_id: str, user_id: str, vote: int) -> None:
        """Upsert a vote (1 or -1) for voice_id by user_id."""
        db = await self.get_db()
        now = datetime.now(UTC).isoformat()
        await db.execute(
            """INSERT INTO voice_votes (voice_id, user_id, vote, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(voice_id, user_id) DO UPDATE SET vote = ?, created_at = ?""",
            (voice_id, user_id, vote, now, vote, now),
        )
        await db.commit()

    async def get_vote_score(self, voice_id: str) -> int:
        """Compute SUM(vote) on-demand for voice_id."""
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT SUM(vote) FROM voice_votes WHERE voice_id = ?", (voice_id,)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row[0] is not None else 0

    async def set_tags(self, voice_id: str, tags: list[str]) -> None:
        """Replace all tags for voice_id (max 5)."""
        db = await self.get_db()
        await db.execute("DELETE FROM voice_tags WHERE voice_id = ?", (voice_id,))
        normalized = [
            t.lower().strip() for t in tags[:5] if t and len(t) <= 15
        ]
        for tag in normalized:
            await db.execute(
                "INSERT OR IGNORE INTO voice_tags (voice_id, tag) VALUES (?, ?)",
                (voice_id, tag),
            )
        await db.commit()

    async def get_tags(self, voice_id: str) -> list[str]:
        """Get all tags for voice_id."""
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT tag FROM voice_tags WHERE voice_id = ?", (voice_id,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def find_best_voice(
        self, gender: str, tags: list[str]
    ) -> dict | None:
        """Find best matching public voice by tag matches and vote score.

        Score = (tag_matches * 10) + vote_score.
        Sort by score DESC, usage_count DESC, created_at DESC. LIMIT 1.
        """
        db = await self.get_db()

        # Get all public voices with matching gender
        cursor = await db.execute(
            """SELECT * FROM voice_samples
               WHERE visibility = 'public'
               AND (gender = ? OR gender = 'other')
               ORDER BY created_at DESC""",
            (gender,),
        )
        rows = await cursor.fetchall()

        best = None
        best_score = -1

        for row in rows:
            voice = dict(row)
            voice_tags = set(await self.get_tags(voice["id"]))

            # Count matching tags
            tag_matches = sum(1 for t in tags if t in voice_tags)

            # Compute vote score
            vote_score = await self.get_vote_score(voice["id"])

            score = tag_matches * 10 + vote_score

            if score > best_score:
                best_score = score
                best = voice
                best["tags"] = list(voice_tags)
                best["vote_score"] = vote_score
            elif score == best_score:
                # Tie-break: prefer higher usage_count
                if voice["usage_count"] > (best["usage_count"] if best else 0):
                    best = voice
                    best["tags"] = list(voice_tags)
                    best["vote_score"] = vote_score

        return best

    async def update_voice_sample(
        self, voice_id: str, **updates
    ) -> None:
        """Update name, description, mood fields."""
        allowed = {"name", "description", "mood"}
        sets = []
        params = []
        for key, value in updates.items():
            if key in allowed and value is not None:
                sets.append(f"{key} = ?")
                params.append(value)

        if not sets:
            return

        sets.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(voice_id)

        db = await self.get_db()
        await db.execute(
            f"UPDATE voice_samples SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        await db.commit()

    async def increment_usage(self, voice_id: str) -> None:
        """Increment usage_count by 1."""
        db = await self.get_db()
        await db.execute(
            "UPDATE voice_samples SET usage_count = usage_count + 1 WHERE id = ?",
            (voice_id,),
        )
        await db.commit()
