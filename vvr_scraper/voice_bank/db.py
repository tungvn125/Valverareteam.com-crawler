"""Voice Bank Database Manager using aiosqlite."""

import asyncio
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
                await self._db.execute("PRAGMA foreign_keys = ON")
                await self._db.execute("PRAGMA journal_mode = WAL")
        return self._db

    async def init_db(self):
        """Create tables and indexes with WAL mode."""
        db = await self.get_db()
        # Note: PRAGMAs are now set in get_db() to ensure they apply on every connection

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
        await db.execute("CREATE INDEX IF NOT EXISTS idx_voices_community ON voice_samples(visibility)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_voices_user ON voice_samples(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_voices_gender_age ON voice_samples(gender, age_group)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tags_tag ON voice_tags(tag)")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_voices_user_hash ON voice_samples(user_id, file_hash)")

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

        db = await self.get_db()
        try:
            await db.execute(
                """INSERT INTO voice_samples
                    (id, user_id, name, description, ref_audio_path, ref_text, duration_ms,
                     sample_rate, gender, age_group, language, mood, visibility, usage_count,
                     file_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                (
                    voice_id,
                    user_id,
                    name,
                    description or "",
                    ref_audio_path,
                    ref_text,
                    duration_ms,
                    sample_rate,
                    gender,
                    age_group,
                    language,
                    mood,
                    visibility,
                    file_hash,
                    now,
                    now,
                ),
            )
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            if "user_id" in str(exc).lower() and "file_hash" in str(exc).lower():
                raise ValueError("Duplicate voice sample") from exc
            raise
        return voice_id

    async def get_voice_sample(self, voice_id: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM voice_samples WHERE id = ?", (voice_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        tags, vote_score = await asyncio.gather(self.get_tags(voice_id), self.get_vote_score(voice_id))
        result["tags"] = tags
        result["vote_score"] = vote_score
        return result

    async def get_voice_by_hash(self, user_id: str, file_hash: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute(
            "SELECT * FROM voice_samples WHERE user_id = ? AND file_hash = ?",
            (user_id, file_hash),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_my_voices(self, user_id: str, limit: int = 20, offset: int = 0) -> dict:
        """List voice samples owned by user_id with pagination."""
        db = await self.get_db()

        # Get total count
        cursor = await db.execute("SELECT COUNT(*) FROM voice_samples WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        total = row[0]

        # Get items with correlated subqueries for tags and vote_score
        # to avoid Cartesian product when voice has both tags AND votes
        cursor = await db.execute(
            """SELECT
                v.*,
                (SELECT GROUP_CONCAT(tag) FROM voice_tags WHERE voice_id = v.id) as tags,
                COALESCE((SELECT SUM(vote) FROM voice_votes WHERE voice_id = v.id), 0) as vote_score
            FROM voice_samples v
            WHERE v.user_id = ?
            ORDER BY v.created_at DESC
            LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        )
        rows = await cursor.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            # Parse GROUP_CONCAT result into list of tags
            tags_str = item.get("tags")
            item["tags"] = tags_str.split(",") if tags_str else []
            item["vote_score"] = item.get("vote_score", 0)
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
        """List public voice samples with optional filters.

        Tag filtering is done in SQL using EXISTS to ensure correct pagination.
        """
        db = await self.get_db()

        conditions = ["visibility = 'public'"]
        params: list = []
        count_params: list = []

        if gender:
            conditions.append("gender = ?")
            params.append(gender)
            count_params.append(gender)
        if age_group:
            conditions.append("age_group = ?")
            params.append(age_group)
            count_params.append(age_group)

        # Tag filtering using EXISTS (moved to SQL for correct pagination)
        tag_conditions = []
        if tags:
            tag_placeholders = ",".join(["?"] * len(tags))
            tag_conditions.append(
                f"EXISTS (SELECT 1 FROM voice_tags vt WHERE vt.voice_id = v.id AND vt.tag IN ({tag_placeholders}))"  # noqa: S608
            )
            params.extend(tags)
            count_params.extend(tags)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        if tag_conditions:
            where_clause += " AND " + " AND ".join(tag_conditions)

        # Get total count with same WHERE clause
        count_sql = f"""SELECT COUNT(*) FROM voice_samples v WHERE {where_clause}"""  # noqa: S608
        cursor = await db.execute(count_sql, count_params)
        row = await cursor.fetchone()
        total = row[0]

        # Build ordering
        if sort == "votes":
            order_sql = """ORDER BY
                (SELECT COALESCE(SUM(vote), 0) FROM voice_votes WHERE voice_id = v.id) DESC,
                usage_count DESC, created_at DESC"""
        else:
            order_sql = "ORDER BY created_at DESC"

        # Get items with correlated subqueries for tags and vote_score
        # to avoid Cartesian product when voice has both tags AND votes
        sql = f"""SELECT
            v.*,
            (SELECT GROUP_CONCAT(tag) FROM voice_tags WHERE voice_id = v.id) as tags,
            COALESCE((SELECT SUM(vote) FROM voice_votes WHERE voice_id = v.id), 0) as vote_score
        FROM voice_samples v
        WHERE {where_clause}
        {order_sql}
        LIMIT ? OFFSET ?"""  # noqa: S608

        query_params = params + [limit, offset]
        cursor = await db.execute(sql, query_params)
        rows = await cursor.fetchall()

        items = []
        for row in rows:
            item = dict(row)
            # Parse GROUP_CONCAT result into list of tags
            tags_str = item.get("tags")
            item["tags"] = tags_str.split(",") if tags_str else []
            item["vote_score"] = item.get("vote_score", 0)
            items.append(item)

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
        # Delete voice_samples first and check if it succeeded
        # Tags and votes will be cleaned up by CASCADE since foreign_keys is ON
        result = await db.execute(
            "DELETE FROM voice_samples WHERE id = ? AND user_id = ?",
            (voice_id, user_id),
        )
        if result.rowcount == 0:
            raise ValueError("Voice sample not found or not owned")
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
        cursor = await db.execute("SELECT SUM(vote) FROM voice_votes WHERE voice_id = ?", (voice_id,))
        row = await cursor.fetchone()
        return int(row[0]) if row[0] is not None else 0

    async def set_tags(self, voice_id: str, tags: list[str]) -> None:
        """Replace all tags for voice_id (max 5)."""
        db = await self.get_db()
        await db.execute("DELETE FROM voice_tags WHERE voice_id = ?", (voice_id,))
        normalized = [t.lower().strip() for t in tags[:5] if t and len(t) <= 15]
        for tag in normalized:
            await db.execute(
                "INSERT OR IGNORE INTO voice_tags (voice_id, tag) VALUES (?, ?)",
                (voice_id, tag),
            )
        await db.commit()

    async def get_tags(self, voice_id: str) -> list[str]:
        """Get all tags for voice_id."""
        db = await self.get_db()
        cursor = await db.execute("SELECT tag FROM voice_tags WHERE voice_id = ?", (voice_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def find_best_voice(self, gender: str, tags: list[str]) -> dict | None:
        """Find best matching public voice by tag matches and vote score.

        Score = (tag_matches * 10) + vote_score.
        Sort by score DESC, usage_count DESC, created_at DESC. LIMIT 1.
        Uses correlated subqueries to avoid Cartesian product when voice has both tags AND votes.
        """
        db = await self.get_db()

        # Build placeholders for tags
        if tags:
            tag_placeholders = ",".join(["?"] * len(tags))
            tag_params = tags
        else:
            tag_placeholders = "?"
            tag_params = [""]

        # Use correlated subqueries to avoid Cartesian product
        cursor = await db.execute(
            f"""SELECT
                v.*,
                (SELECT GROUP_CONCAT(tag) FROM voice_tags WHERE voice_id = v.id) as tags,
                COALESCE((SELECT SUM(vote) FROM voice_votes WHERE voice_id = v.id), 0) as vote_score,
                COALESCE((SELECT COUNT(*) FROM voice_tags WHERE voice_id = v.id AND tag IN ({tag_placeholders})), 0) as matching_tags
            FROM voice_samples v
            WHERE v.visibility = 'public' AND (v.gender = ? OR v.gender = 'other')
            ORDER BY matching_tags DESC, vote_score DESC, v.usage_count DESC, v.created_at DESC
            LIMIT 1""",  # noqa: S608
            tag_params + [gender],
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        voice = dict(row)
        # Parse GROUP_CONCAT result into list of tags
        tags_str = voice.get("tags")
        voice["tags"] = tags_str.split(",") if tags_str else []
        voice["vote_score"] = voice.get("vote_score", 0)

        return voice

    async def update_voice_sample(self, voice_id: str, **updates) -> None:
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
            f"UPDATE voice_samples SET {', '.join(sets)} WHERE id = ?",  # noqa: S608
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
