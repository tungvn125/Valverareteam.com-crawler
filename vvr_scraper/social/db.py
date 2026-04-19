import asyncio
import os
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import aiosqlite
from loguru import logger

REACTION_TYPES = {"heart", "cry", "wow", "angry", "fire", "skull", "think", "clap"}


def group_reactions_by_anchor(reactions: list[dict]) -> dict[str, list[dict]]:
    anchors: dict[str, list[dict]] = defaultdict(list)
    for r in reactions:
        anchors[r["anchor"]].append(r)
    return dict(anchors)


class SocialDatabaseManager:

    async def _enrich_user(self, db, payload: dict) -> dict:
        user_id = payload.get("user_id")
        if user_id and "user" not in payload:
            cursor = await db.execute("SELECT id, username, display_name, role, created_at FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            if row:
                payload["user"] = {"id": row[0], "username": row[1], "displayName": row[2], "role": row[3]}
        return payload
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

    async def create_user_for_test(self, username: str, role: str = "member") -> str:
        user_id = str(uuid.uuid4())
        db = await self.get_db()
        await db.execute(
            "INSERT INTO users (id, username, display_name, hashed_password, invite_code_used, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, username, "hashed", None, role, datetime.now(UTC).isoformat()),
        )
        await db.commit()
        return user_id

    async def create_reaction(self, user_id: str, book_slug: str, chapter_id: str, anchor: str, reaction_type: str) -> str:
        if reaction_type not in REACTION_TYPES:
            raise ValueError("invalid reaction type")
        reaction_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        db = await self.get_db()
        try:
            await db.execute(
                "INSERT INTO reactions (id, user_id, book_slug, chapter_id, anchor, reaction_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (reaction_id, user_id, book_slug, chapter_id, anchor, reaction_type, now),
            )
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise ValueError("reaction already exists") from exc
        return reaction_id

    async def get_reaction(self, reaction_id: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM reactions WHERE id = ?", (reaction_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_reaction(self, reaction_id: str) -> None:
        db = await self.get_db()
        await db.execute("DELETE FROM reactions WHERE id = ?", (reaction_id,))
        await db.commit()

    async def list_reactions(self, book_slug: str, chapter_id: str, anchor: str | None = None) -> list[dict]:
        db = await self.get_db()
        if anchor:
            cursor = await db.execute(
                "SELECT * FROM reactions WHERE book_slug = ? AND chapter_id = ? AND anchor = ?",
                (book_slug, chapter_id, anchor),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM reactions WHERE book_slug = ? AND chapter_id = ?",
                (book_slug, chapter_id),
            )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            payload = dict(row)
            await self._enrich_user(db, payload)
            result.append(payload)
        return result

    async def get_comment(self, comment_id: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_comment(
        self, user_id: str, book_slug: str, chapter_id: str, anchor: str | None, content: str, parent_id: str | None
    ) -> str:
        if parent_id:
            parent = await self.get_comment(parent_id)
            if not parent:
                raise ValueError("parent comment not found")
            if parent["parent_id"] is not None:
                raise ValueError("comments may only be one level deep")
        comment_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        db = await self.get_db()
        await db.execute(
            "INSERT INTO comments (id, user_id, book_slug, chapter_id, anchor, parent_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (comment_id, user_id, book_slug, chapter_id, anchor, parent_id, content, now, now),
        )
        await db.commit()
        return comment_id

    async def list_comments(self, book_slug: str, chapter_id: str, anchor: str | None = None) -> list[dict]:
        db = await self.get_db()
        if anchor:
            cursor = await db.execute(
                "SELECT * FROM comments WHERE book_slug = ? AND chapter_id = ? AND anchor = ?",
                (book_slug, chapter_id, anchor),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM comments WHERE book_slug = ? AND chapter_id = ?",
                (book_slug, chapter_id),
            )
        rows = await cursor.fetchall()
        parents = []
        replies_by_parent = defaultdict(list)
        for row in rows:
            payload = dict(row)
            await self._enrich_user(db, payload)
            payload["replies"] = []
            if payload["parent_id"]:
                replies_by_parent[payload["parent_id"]].append(payload)
            else:
                parents.append(payload)
        for parent in parents:
            parent["replies"] = replies_by_parent[parent["id"]]
        return parents

    async def update_comment(self, comment_id: str, content: str) -> dict:
        now = datetime.now(UTC).isoformat()
        db = await self.get_db()
        await db.execute(
            "UPDATE comments SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, comment_id),
        )
        await db.commit()
        return await self.get_comment(comment_id)

    async def delete_comment(self, comment_id: str) -> None:
        db = await self.get_db()
        await db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        await db.execute("DELETE FROM comments WHERE parent_id = ?", (comment_id,))
        await db.commit()

    async def create_invite_code(self, code: str, created_by: str, max_uses: int = 1) -> dict:
        now = datetime.now(UTC).isoformat()
        db = await self.get_db()
        await db.execute(
            "INSERT INTO invite_codes (code, created_by, max_uses, use_count, created_at) VALUES (?, ?, ?, 0, ?)",
            (code, created_by, max_uses, now),
        )
        await db.commit()
        return {"code": code, "created_by": created_by, "max_uses": max_uses, "use_count": 0}

    async def get_invite_code(self, code: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_invite_codes(self) -> list[dict]:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM invite_codes")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_user_by_username(self, username: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> dict | None:
        db = await self.get_db()
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_random_invite(self, created_by: str, max_uses: int = 1) -> dict:
        code = str(uuid.uuid4())[:8]
        return await self.create_invite_code(code=code, created_by=created_by, max_uses=max_uses)

    async def has_any_admin(self) -> bool:
        db = await self.get_db()
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        row = await cursor.fetchone()
        return row[0] > 0

    async def create_admin_user(self, username: str, hashed_password: str, display_name: str) -> dict:
        user_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        db = await self.get_db()
        try:
            await db.execute(
                "INSERT INTO users (id, username, display_name, hashed_password, invite_code_used, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, display_name, hashed_password, None, "admin", now),
            )
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise ValueError(f"username '{username}' is already taken") from exc
        return {"id": user_id, "username": username, "display_name": display_name, "role": "admin"}

    async def register_user_with_invite(
        self, invite_code: str, username: str, hashed_password: str, display_name: str
    ) -> dict:
        if await self.get_user_by_username(username):
            raise ValueError(f"username '{username}' is already taken")

        invite = await self.get_invite_code(invite_code)
        if not invite:
            bootstrap_code = os.getenv("VVR_ADMIN_CODE")
            if invite_code == bootstrap_code and not await self.has_any_admin():
                role = "admin"
            else:
                raise ValueError("invalid invite code")
        else:
            if invite["use_count"] >= invite["max_uses"]:
                raise ValueError("invite code exhausted")
            role = "member"

        user_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        db = await self.get_db()
        try:
            await db.execute(
                "INSERT INTO users (id, username, display_name, hashed_password, invite_code_used, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, display_name, hashed_password, invite_code, role, now),
            )
        except aiosqlite.IntegrityError as exc:
            raise ValueError(f"username '{username}' is already taken") from exc

        if invite:
            await db.execute(
                "UPDATE invite_codes SET use_count = use_count + 1 WHERE code = ?",
                (invite_code,),
            )
        await db.commit()
        return {"id": user_id, "username": username, "display_name": display_name, "role": role}
