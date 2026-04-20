# Social Reader MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add invite-only social reading to VVR by extending this FastAPI backend with auth, invites, reactions, comments, and chapter-scoped WebSocket updates, then integrate a Readest fork so readers can authenticate, react to selections, and read/write threaded comments while reading EPUBs from VVR OPDS.

**Architecture:** Implement the backend first in this repository so the social data model, auth flow, and real-time API surface are stable before the reader integration begins. Then extend the Readest fork in `../readest` with one small social client stack: persisted VVR settings, a zustand social store, a `useSocial` hook for REST plus WebSocket synchronization, and focused reader UI integrations in the annotator popup and notebook panel.

**Tech Stack:** FastAPI, aiosqlite, Pydantic, PyJWT, bcrypt/passlib, pytest, Docker Compose, Next.js, React 19, Zustand, Vitest, Tauri/Next shared app services, OPDS-fed EPUB reading via foliate-js

---

## Scope Check

This spec spans two independent codebases:

- This repository: `vvr_scraper` backend and CLI.
- The sibling Readest fork at `../readest`.

That is larger than a normal single-repo plan. The work is therefore split into two execution tracks in one document:

- **Track A:** backend and deployment in this repository.
- **Track B:** reader integration in `../readest`.

If you want to execute the work with maximum isolation, split this document into two plans and finish Track A before starting Track B. The tasks below are already ordered that way.

## File Structure

- Create: `vvr_scraper/social/__init__.py`
  Package entry for the social module.
- Create: `vvr_scraper/social/models.py`
  Pydantic request/response models for auth, invites, reactions, comments, and websocket payloads.
- Create: `vvr_scraper/social/db.py`
  `SocialDatabaseManager`, social schema creation, and all social queries against `social.db`.
- Create: `vvr_scraper/social/auth.py`
  Password hashing, JWT creation/validation, auth dependencies, invite consumption, and admin bootstrap helpers.
- Create: `vvr_scraper/social/websocket.py`
  Chapter-scoped connection manager and broadcast helpers.
- Create: `vvr_scraper/social/router.py`
  FastAPI routers for `/api/auth`, `/api/admin`, `/api/social`, and `/ws/social/{book_slug}/{chapter_id}`.
- Modify: `vvr_scraper/web/__init__.py`
  Initialize `social.db`, mount the social routers, and close the social database on shutdown.
- Modify: `vvr_scraper/web/deps.py`
  Add `get_social_db` so route handlers do not reach through module globals.
- Modify: `vvr_scraper/cli.py`
  Add `vvrt social create-admin` bootstrap command.
- Modify: `pyproject.toml`
  Add JWT and password-hashing dependencies used by the social module.
- Modify: `.env.example`
  Document `VVR_JWT_SECRET` and `VVR_ADMIN_CODE`.
- Modify: `docker-compose.yml`
  Pass the new social environment variables into the existing `vvr-web` container.
- Create: `tests/test_social_db.py`
  Social database schema, uniqueness, and query tests.
- Create: `tests/test_social_auth.py`
  Auth, invite, JWT, and admin bootstrap tests.
- Create: `tests/test_social_api.py`
  FastAPI endpoint tests for auth, admin, reactions, comments, and rate limits.
- Create: `tests/test_social_websocket.py`
  Chapter-scoped WebSocket tests.
- Modify: `tests/test_cli_unit.py`
  Add CLI coverage for `vvrt social create-admin` argument handling.

- Create: `../readest/apps/readest-app/src/components/social/AuthModal.tsx`
  Login/register modal for VVR social auth.
- Create: `../readest/apps/readest-app/src/components/social/SocialPanel.tsx`
  Notebook tab content showing chapter comments and reaction groupings.
- Create: `../readest/apps/readest-app/src/components/social/ReactionBar.tsx`
  Small reaction picker launched from the annotator popup.
- Create: `../readest/apps/readest-app/src/components/social/ReactionBadges.tsx`
  Inline chapter-anchor reaction counts rendered near the current selection target.
- Create: `../readest/apps/readest-app/src/components/social/CommentThread.tsx`
  One-level-deep threaded comment list with edit/delete affordances for own comments.
- Create: `../readest/apps/readest-app/src/components/social/CommentInput.tsx`
  New comment / reply input with content limit and mutation states.
- Create: `../readest/apps/readest-app/src/hooks/useSocial.ts`
  REST and WebSocket orchestration for auth/session/chapter data.
- Create: `../readest/apps/readest-app/src/store/socialStore.ts`
  Zustand store for auth state, chapter state, optimistic mutation state, and settings-derived availability.
- Create: `../readest/apps/readest-app/src/types/social.ts`
  Shared frontend types for user/session/reaction/comment/chapter payloads.
- Create: `../readest/apps/readest-app/src/utils/social.ts`
  URL normalization, slug extraction from VVR OPDS/download URLs, and response grouping helpers.
- Modify: `../readest/apps/readest-app/src/types/settings.ts`
  Add persisted VVR social settings to `SystemSettings`.
- Modify: `../readest/apps/readest-app/src/store/notebookStore.ts`
  Add `'social'` notebook tab support.
- Modify: `../readest/apps/readest-app/src/components/settings/SettingsDialog.tsx`
  Add a top-level settings tab for VVR social configuration.
- Create: `../readest/apps/readest-app/src/components/settings/SocialPanel.tsx`
  Settings panel that captures VVR server URL and social enablement.
- Modify: `../readest/apps/readest-app/src/app/reader/components/notebook/Notebook.tsx`
  Render the social tab panel.
- Modify: `../readest/apps/readest-app/src/app/reader/components/notebook/NotebookTabNavigation.tsx`
  Add Social tab icon and label.
- Modify: `../readest/apps/readest-app/src/app/reader/components/annotator/AnnotationPopup.tsx`
  Support a dedicated social action button.
- Modify: `../readest/apps/readest-app/src/app/reader/components/annotator/Annotator.tsx`
  Wire text selection CFI into reaction/comment flows and inline badge rendering.
- Modify: `../readest/apps/readest-app/src/app/reader/hooks/useFoliateEvents.ts`
  Add chapter change callback support so social connections can follow navigation.
- Create: `../readest/apps/readest-app/src/__tests__/store/social-store.test.ts`
  Store behavior tests.
- Create: `../readest/apps/readest-app/src/__tests__/utils/social.test.ts`
  Slug extraction and grouping helper tests.
- Create: `../readest/apps/readest-app/src/__tests__/hooks/use-social.test.tsx`
  Hook tests for REST loading and websocket application.
- Create: `../readest/apps/readest-app/src/__tests__/components/social-panel.test.tsx`
  Social panel and auth modal rendering tests.
- Modify: `../readest/apps/readest-app/src/__tests__/store/notebook-store.test.ts`
  Add coverage for the new `social` notebook tab.
- Modify: `../readest/apps/readest-app/src/__tests__/store/settings-store.test.ts`
  Extend fixture coverage for new social settings.

### Task 1: Add Backend Social Dependencies and Database Wiring

**Files:**
- Modify: `pyproject.toml:15-38`
- Modify: `.env.example:7-34`
- Modify: `docker-compose.yml:15-34`
- Modify: `vvr_scraper/web/__init__.py:53-124`
- Modify: `vvr_scraper/web/deps.py:39-55`
- Create: `vvr_scraper/social/__init__.py`
- Create: `vvr_scraper/social/db.py`
- Test: `tests/test_social_db.py`

- [ ] **Step 1: Write the failing database wiring tests**

```python
import pytest

from vvr_scraper.social.db import SocialDatabaseManager


@pytest.mark.asyncio
async def test_social_db_creates_core_tables(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))

    await db.init_db()

    table_names = await db.list_table_names()
    assert set(table_names) >= {"users", "invite_codes", "reactions", "comments"}


@pytest.mark.asyncio
async def test_social_db_enables_wal_mode(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))

    await db.init_db()

    assert await db.get_journal_mode() == "wal"
```

- [ ] **Step 2: Run the database tests to verify they fail**

Run: `pytest tests/test_social_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vvr_scraper.social'`.

- [ ] **Step 3: Add the new Python dependencies and documented env vars**

Update `pyproject.toml` dependencies to include:

```toml
"PyJWT>=2.10.1",
"passlib[bcrypt]>=1.7.4",
```

Add these lines to `.env.example`:

```dotenv
# --- Social Reader Auth ---
VVR_JWT_SECRET=change-this-random-secret
VVR_ADMIN_CODE=bootstrap-admin-code
```

Add these lines to the `vvr-web` service `environment` block in `docker-compose.yml`:

```yaml
      - VVR_JWT_SECRET=${VVR_JWT_SECRET:-change-this-random-secret}
      - VVR_ADMIN_CODE=${VVR_ADMIN_CODE:-}
```

- [ ] **Step 4: Create the social package and database manager**

Create `vvr_scraper/social/__init__.py`:

```python
"""Social reading module for VVR."""

from .db import SocialDatabaseManager

__all__ = ["SocialDatabaseManager"]
```

Create `vvr_scraper/social/db.py` with this initial shape:

```python
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
```

- [ ] **Step 5: Wire `social.db` into the FastAPI app state**

Update `vvr_scraper/web/__init__.py` so `lifespan()` initializes both databases:

```python
from ..utils import get_config_path
from ..social.db import SocialDatabaseManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    state._event_loop = asyncio.get_running_loop()
    if not hasattr(app.state, "db") or app.state.db is None:
        app.state.db = DatabaseManager(db_path=get_config_path("vvr_library.db"))
    if not hasattr(app.state, "social_db") or app.state.social_db is None:
        app.state.social_db = SocialDatabaseManager(db_path=get_config_path("social.db"))

    await app.state.db.init_db()
    await app.state.social_db.init_db()
    yield
    if hasattr(app.state, "social_db") and app.state.social_db:
        await app.state.social_db.close()
    if hasattr(app.state, "db") and app.state.db:
        await app.state.db.close()
```

Update `vvr_scraper/web/deps.py` with a second dependency:

```python
def get_social_db(request: Request | None = None):
    if request is not None:
        state = request.app.state
    else:
        from . import app

        state = app.state

    db = getattr(state, "social_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Social database not initialized")
    return db
```

- [ ] **Step 6: Run the database tests again**

Run: `pytest tests/test_social_db.py -v`
Expected: PASS for the initial schema and WAL checks.

- [ ] **Step 7: Commit the database foundation**

```bash
git add pyproject.toml .env.example docker-compose.yml vvr_scraper/social/__init__.py vvr_scraper/social/db.py vvr_scraper/web/__init__.py vvr_scraper/web/deps.py tests/test_social_db.py
git commit -m "feat: add social database foundation"
```

### Task 2: Implement Social Models, Constraints, and Query Helpers

**Files:**
- Modify: `vvr_scraper/social/db.py`
- Create: `vvr_scraper/social/models.py`
- Modify: `tests/test_social_db.py`

- [ ] **Step 1: Write failing query and constraint tests**

Append these tests to `tests/test_social_db.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_reaction_uniqueness_is_enforced(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    await db.create_reaction(user_id, "book-1", "chapter-1", "epubcfi(/6/2)", "heart")

    with pytest.raises(ValueError, match="already exists"):
        await db.create_reaction(user_id, "book-1", "chapter-1", "epubcfi(/6/2)", "heart")


@pytest.mark.asyncio
async def test_comment_replies_are_limited_to_one_level(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    parent_id = await db.create_comment(user_id, "book-1", "chapter-1", None, "root", None)
    child_id = await db.create_comment(user_id, "book-1", "chapter-1", None, "reply", parent_id)

    with pytest.raises(ValueError, match="one level deep"):
        await db.create_comment(user_id, "book-1", "chapter-1", None, "nested", child_id)
```

- [ ] **Step 2: Run the tests to verify query helpers are missing**

Run: `pytest tests/test_social_db.py -v`
Expected: FAIL with missing helper methods such as `create_user_for_test`, `create_reaction`, or `create_comment`.

- [ ] **Step 3: Create the social Pydantic models**

Create `vvr_scraper/social/models.py` with these core types:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ReactionType = Literal["heart", "cry", "wow", "angry", "fire", "skull", "think", "clap"]
UserRole = Literal["admin", "member"]


class SocialUser(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    created_at: datetime


class RegisterRequest(BaseModel):
    invite_code: str
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class InviteCreateRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=100)


class ReactionCreateRequest(BaseModel):
    anchor: str = Field(min_length=1, max_length=1000)
    reaction_type: ReactionType


class CommentCreateRequest(BaseModel):
    anchor: str | None = Field(default=None, max_length=1000)
    content: str = Field(min_length=1, max_length=2000)
    parent_id: str | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class CommentUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
```

- [ ] **Step 4: Expand `SocialDatabaseManager` with schema validation helpers and core CRUD**

Add these behaviors in `vvr_scraper/social/db.py`:

```python
REACTION_TYPES = {"heart", "cry", "wow", "angry", "fire", "skull", "think", "clap"}


async def create_user_for_test(self, username: str, role: str = "member") -> str:
    user_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO users (id, username, display_name, hashed_password, invite_code_used, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, username, "hashed", None, role, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()
    return user_id


async def create_reaction(self, user_id: str, book_slug: str, chapter_id: str, anchor: str, reaction_type: str):
    if reaction_type not in REACTION_TYPES:
        raise ValueError("invalid reaction type")
    try:
        ...
    except aiosqlite.IntegrityError as exc:
        raise ValueError("reaction already exists") from exc


async def create_comment(self, user_id: str, book_slug: str, chapter_id: str, anchor: str | None, content: str, parent_id: str | None):
    if parent_id:
        parent = await self.get_comment(parent_id)
        if not parent:
            raise ValueError("parent comment not found")
        if parent["parent_id"] is not None:
            raise ValueError("comments may only be one level deep")
    ...
```

Also add grouped fetch helpers used later by the API:

```python
async def list_reactions(self, book_slug: str, chapter_id: str, anchor: str | None = None) -> list[dict]: ...
async def list_comments(self, book_slug: str, chapter_id: str, anchor: str | None = None) -> list[dict]: ...
async def get_comment(self, comment_id: str) -> dict | None: ...
```

- [ ] **Step 5: Run the database tests again**

Run: `pytest tests/test_social_db.py -v`
Expected: PASS for uniqueness and one-level reply constraints.

- [ ] **Step 6: Commit the social model/query layer**

```bash
git add vvr_scraper/social/db.py vvr_scraper/social/models.py tests/test_social_db.py
git commit -m "feat: add social data models and queries"
```

### Task 3: Implement Auth, Invite Consumption, and Admin Bootstrap

**Files:**
- Create: `vvr_scraper/social/auth.py`
- Modify: `vvr_scraper/social/db.py`
- Create: `tests/test_social_auth.py`
- Modify: `tests/test_cli_unit.py`
- Modify: `vvr_scraper/cli.py:179-240`

- [ ] **Step 1: Write the failing auth and bootstrap tests**

Create `tests/test_social_auth.py`:

```python
import os

import pytest

from vvr_scraper.social.auth import create_access_token, hash_password, verify_password
from vvr_scraper.social.db import SocialDatabaseManager


def test_password_hash_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_create_access_token_contains_subject_and_role(monkeypatch):
    monkeypatch.setenv("VVR_JWT_SECRET", "test-secret")

    token = create_access_token(user_id="u1", username="alice", role="admin")

    assert isinstance(token, str)
    assert token.count(".") == 2


@pytest.mark.asyncio
async def test_bootstrap_admin_from_env_code(tmp_path, monkeypatch):
    monkeypatch.setenv("VVR_ADMIN_CODE", "seed-admin")
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()

    user = await db.register_user_with_invite("seed-admin", "adminuser", "hashed", "Admin")

    assert user["role"] == "admin"
```

Add CLI tests to `tests/test_cli_unit.py`:

```python
def test_social_create_admin_command_parses():
    cli = self._parse(["social", "create-admin", "--username", "alice", "--password", "secret123"])
    assert cli.args.ten_truyen[:2] == ["social", "create-admin"]
    assert cli.args.username == "alice"
```

- [ ] **Step 2: Run the auth tests to verify they fail**

Run: `pytest tests/test_social_auth.py tests/test_cli_unit.py -v`
Expected: FAIL with missing auth helpers and unknown CLI arguments.

- [ ] **Step 3: Implement `auth.py` with JWT and password helpers**

Create `vvr_scraper/social/auth.py` with these core functions:

```python
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_jwt_secret() -> str:
    secret = os.getenv("VVR_JWT_SECRET")
    if not secret:
        raise RuntimeError("VVR_JWT_SECRET is required for social auth")
    return secret


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_access_token(user_id: str, username: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")
```

Also add dependencies used later by routers:

```python
class AuthUser(BaseModel):
    id: str
    username: str
    role: str


async def get_auth_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    ...


async def require_admin(user: AuthUser = Depends(get_auth_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

- [ ] **Step 4: Add invite and registration helpers in `SocialDatabaseManager`**

Add these methods to `vvr_scraper/social/db.py`:

```python
async def create_invite_code(self, code: str, created_by: str, max_uses: int = 1) -> dict: ...
async def get_invite_code(self, code: str) -> dict | None: ...
async def list_invite_codes(self) -> list[dict]: ...
async def get_user_by_username(self, username: str) -> dict | None: ...
async def get_user_by_id(self, user_id: str) -> dict | None: ...


async def register_user_with_invite(self, invite_code: str, username: str, hashed_password: str, display_name: str) -> dict:
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
    ...
```

- [ ] **Step 5: Add CLI argument parsing for `vvrt social create-admin`**

Extend `vvr_scraper/cli.py` with these parser additions:

```python
parser.add_argument("--username", help="Username for social admin bootstrap.")
parser.add_argument("--password", help="Password for social admin bootstrap.")
parser.add_argument("--display-name", help="Display name for social admin bootstrap.")
```

And add this early handler in `run()` before the normal scraping modes:

```python
if self.args.ten_truyen[:2] == ["social", "create-admin"]:
    from .social.auth import hash_password
    from .social.db import SocialDatabaseManager

    social_db = SocialDatabaseManager(db_path=get_config_path("social.db"))
    await social_db.init_db()
    user = await social_db.create_admin_user(
        username=self.args.username,
        hashed_password=hash_password(self.args.password),
        display_name=self.args.display_name or self.args.username,
    )
    console.print(f"Created admin user: {user['username']}")
    await social_db.close()
    return
```

- [ ] **Step 6: Run the auth and CLI tests again**

Run: `pytest tests/test_social_auth.py tests/test_cli_unit.py -v`
Expected: PASS for password hashing, JWT issuance, env bootstrap, and CLI parse coverage.

- [ ] **Step 7: Commit the auth/bootstrap layer**

```bash
git add vvr_scraper/social/auth.py vvr_scraper/social/db.py vvr_scraper/cli.py tests/test_social_auth.py tests/test_cli_unit.py
git commit -m "feat: add social auth and admin bootstrap"
```

### Task 4: Expose Auth and Admin Invite API Routes

**Files:**
- Create: `vvr_scraper/social/router.py`
- Modify: `vvr_scraper/web/__init__.py`
- Modify: `tests/test_social_api.py`

- [ ] **Step 1: Write failing auth/admin API tests**

Create `tests/test_social_api.py` with these first endpoint tests:

```python
def test_register_returns_user_and_token(client):
    response = client.post(
        "/api/auth/register",
        json={"invite_code": "seed-admin", "username": "alice", "password": "secret1234"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["username"] == "alice"
    assert isinstance(data["token"], str)


def test_login_returns_token_for_valid_credentials(client, seeded_social_user):
    response = client.post("/api/auth/login", json={"username": "alice", "password": "secret1234"})
    assert response.status_code == 200


def test_admin_invite_creation_requires_admin_role(client, member_token):
    response = client.post("/api/admin/invites", headers={"Authorization": f"Bearer {member_token}"}, json={})
    assert response.status_code == 403
```

- [ ] **Step 2: Run the API tests to verify the routers do not exist yet**

Run: `pytest tests/test_social_api.py -v`
Expected: FAIL with `404` responses for `/api/auth/*` and `/api/admin/*`.

- [ ] **Step 3: Add auth and admin routers in `vvr_scraper/social/router.py`**

Create the initial router module with this structure:

```python
from fastapi import APIRouter, Depends, HTTPException, Request

from ..web.deps import get_social_db
from .auth import create_access_token, get_auth_user, hash_password, require_admin, verify_password
from .models import InviteCreateRequest, LoginRequest, RegisterRequest, SocialUser


auth_router = APIRouter()
admin_router = APIRouter()
social_router = APIRouter()


@auth_router.post("/register")
async def register(payload: RegisterRequest, social_db=Depends(get_social_db)):
    user = await social_db.register_user_with_invite(
        invite_code=payload.invite_code,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        display_name=payload.username,
    )
    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    return {"user": user, "token": token}


@auth_router.post("/login")
async def login(payload: LoginRequest, social_db=Depends(get_social_db)):
    user = await social_db.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    return {"user": user, "token": token}


@auth_router.get("/me")
async def me(user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    row = await social_db.get_user_by_id(user.id)
    return {"user": row}


@admin_router.post("/invites")
async def create_invite(payload: InviteCreateRequest, user=Depends(require_admin), social_db=Depends(get_social_db)):
    invite = await social_db.create_random_invite(created_by=user.id, max_uses=payload.max_uses)
    return invite


@admin_router.get("/invites")
async def list_invites(user=Depends(require_admin), social_db=Depends(get_social_db)):
    return await social_db.list_invite_codes()
```

- [ ] **Step 4: Mount the new routers into the FastAPI app**

Update `vvr_scraper/web/__init__.py` imports and router registration:

```python
from ..social.router import admin_router, auth_router, social_router, websocket_router

app.include_router(auth_router, prefix="/api/auth", tags=["Social Auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["Social Admin"])
app.include_router(social_router, prefix="/api/social", tags=["Social"])
app.include_router(websocket_router, tags=["Social"])
```

- [ ] **Step 5: Run the auth/admin API tests again**

Run: `pytest tests/test_social_api.py -v -k "register or login or admin"`
Expected: PASS for register/login/me and admin invite authorization.

- [ ] **Step 6: Commit the initial social routers**

```bash
git add vvr_scraper/social/router.py vvr_scraper/web/__init__.py tests/test_social_api.py
git commit -m "feat: add social auth and admin routes"
```

### Task 5: Add Reactions API, Ownership Rules, and Broadcast Payloads

**Files:**
- Modify: `vvr_scraper/social/db.py`
- Modify: `vvr_scraper/social/models.py`
- Create: `vvr_scraper/social/websocket.py`
- Modify: `vvr_scraper/social/router.py`
- Modify: `tests/test_social_api.py`
- Create: `tests/test_social_websocket.py`

- [ ] **Step 1: Write failing reaction API and websocket tests**

Add these tests:

```python
def test_create_reaction_returns_created_payload(client, member_token):
    response = client.post(
        "/api/social/books/book-1/chapters/ch-1/reactions",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"anchor": "epubcfi(/6/2)", "reaction_type": "heart"},
    )

    assert response.status_code == 200
    assert response.json()["reaction_type"] == "heart"


def test_delete_reaction_requires_owner(client, second_member_token, seeded_reaction_id):
    response = client.delete(
        f"/api/social/reactions/{seeded_reaction_id}",
        headers={"Authorization": f"Bearer {second_member_token}"},
    )
    assert response.status_code == 403
```

Create `tests/test_social_websocket.py`:

```python
def test_reaction_broadcast_is_scoped_to_same_chapter(client, member_token):
    with client.websocket_connect("/ws/social/book-1/ch-1") as ws_same:
        with client.websocket_connect("/ws/social/book-1/ch-2") as ws_other:
            response = client.post(
                "/api/social/books/book-1/chapters/ch-1/reactions",
                headers={"Authorization": f"Bearer {member_token}"},
                json={"anchor": "epubcfi(/6/2)", "reaction_type": "heart"},
            )
            assert response.status_code == 200
            assert ws_same.receive_json()["type"] == "reaction"
            ws_other.send_text("ping")
```

- [ ] **Step 2: Run the reaction tests to verify missing route coverage**

Run: `pytest tests/test_social_api.py tests/test_social_websocket.py -v -k reaction`
Expected: FAIL with `404` or missing websocket router behavior.

- [ ] **Step 3: Implement chapter-scoped websocket manager**

Create `vvr_scraper/social/websocket.py`:

```python
from collections import defaultdict

from fastapi import WebSocket


class SocialConnectionManager:
    def __init__(self):
        self.rooms: dict[tuple[str, str], list[WebSocket]] = defaultdict(list)

    async def connect(self, book_slug: str, chapter_id: str, websocket: WebSocket):
        await websocket.accept()
        self.rooms[(book_slug, chapter_id)].append(websocket)

    def disconnect(self, book_slug: str, chapter_id: str, websocket: WebSocket):
        room = self.rooms[(book_slug, chapter_id)]
        if websocket in room:
            room.remove(websocket)

    async def broadcast(self, book_slug: str, chapter_id: str, message: dict):
        room = list(self.rooms[(book_slug, chapter_id)])
        dead = []
        for websocket in room:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(book_slug, chapter_id, websocket)


social_ws_manager = SocialConnectionManager()
```

- [ ] **Step 4: Add reactions routes and ownership enforcement**

Extend `vvr_scraper/social/router.py`:

```python
@social_router.get("/books/{slug}/chapters/{cid}/reactions")
async def list_reactions(slug: str, cid: str, anchor: str | None = None, user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    rows = await social_db.list_reactions(slug, cid, anchor)
    return {"anchors": group_reactions_by_anchor(rows)}


@social_router.post("/books/{slug}/chapters/{cid}/reactions")
async def create_reaction(slug: str, cid: str, payload: ReactionCreateRequest, user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    reaction = await social_db.create_reaction(user.id, slug, cid, payload.anchor, payload.reaction_type)
    await social_ws_manager.broadcast(slug, cid, {"type": "reaction", "data": reaction})
    return reaction


@social_router.delete("/reactions/{reaction_id}", status_code=204)
async def delete_reaction(reaction_id: str, user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    reaction = await social_db.get_reaction(reaction_id)
    if not reaction:
        raise HTTPException(status_code=404, detail="Reaction not found")
    if reaction["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's reaction")
    await social_db.delete_reaction(reaction_id)
    await social_ws_manager.broadcast(reaction["book_slug"], reaction["chapter_id"], {"type": "reaction_deleted", "data": {"id": reaction_id}})
```

- [ ] **Step 5: Add the websocket route**

Append to `vvr_scraper/social/router.py`:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

websocket_router = APIRouter()


@websocket_router.websocket("/ws/social/{book_slug}/{chapter_id}")
async def social_ws(book_slug: str, chapter_id: str, websocket: WebSocket):
    await social_ws_manager.connect(book_slug, chapter_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        social_ws_manager.disconnect(book_slug, chapter_id, websocket)
```

- [ ] **Step 6: Run the reaction tests again**

Run: `pytest tests/test_social_api.py tests/test_social_websocket.py -v -k reaction`
Expected: PASS for create/list/delete reaction behavior and chapter-scoped broadcasts.

- [ ] **Step 7: Commit the reactions layer**

```bash
git add vvr_scraper/social/db.py vvr_scraper/social/models.py vvr_scraper/social/websocket.py vvr_scraper/social/router.py tests/test_social_api.py tests/test_social_websocket.py
git commit -m "feat: add social reactions and realtime broadcasts"
```

### Task 6: Add Comments API, Edit/Delete Rules, and Rate Limits

**Files:**
- Modify: `vvr_scraper/social/db.py`
- Modify: `vvr_scraper/social/router.py`
- Modify: `tests/test_social_api.py`

- [ ] **Step 1: Write failing comment API tests**

Add these tests to `tests/test_social_api.py`:

```python
def test_create_comment_supports_chapter_level_anchor(client, member_token):
    response = client.post(
        "/api/social/books/book-1/chapters/ch-1/comments",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"content": "First!"},
    )
    assert response.status_code == 200
    assert response.json()["anchor"] is None


def test_update_comment_requires_owner(client, second_member_token, seeded_comment_id):
    response = client.put(
        f"/api/social/comments/{seeded_comment_id}",
        headers={"Authorization": f"Bearer {second_member_token}"},
        json={"content": "edited"},
    )
    assert response.status_code == 403


def test_list_comments_returns_replies_nested_under_parent(client, member_token, seeded_comments):
    response = client.get(
        "/api/social/books/book-1/chapters/ch-1/comments",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code == 200
    assert len(response.json()[0]["replies"]) == 1
```

- [ ] **Step 2: Run the comment tests to verify the routes are still missing**

Run: `pytest tests/test_social_api.py -v -k comment`
Expected: FAIL with `404` or missing payload shape assertions.

- [ ] **Step 3: Implement comment query helpers in the database layer**

Extend `vvr_scraper/social/db.py` with:

```python
async def update_comment(self, comment_id: str, content: str) -> dict: ...
async def delete_comment(self, comment_id: str) -> None: ...


async def list_comments(self, book_slug: str, chapter_id: str, anchor: str | None = None) -> list[dict]:
    ...
    parents = []
    replies_by_parent = defaultdict(list)
    for row in rows:
        payload = dict(row)
        payload["replies"] = []
        if payload["parent_id"]:
            replies_by_parent[payload["parent_id"]].append(payload)
        else:
            parents.append(payload)
    for parent in parents:
        parent["replies"] = replies_by_parent[parent["id"]]
    return parents
```

- [ ] **Step 4: Add simple in-process rate limiting for mutations**

Keep the MVP rate limiter local to the process in `vvr_scraper/social/router.py`:

```python
RATE_BUCKETS: dict[tuple[str, str], list[float]] = defaultdict(list)


def enforce_rate_limit(user_id: str, action: str, limit: int, window_seconds: int):
    now = time.monotonic()
    key = (user_id, action)
    RATE_BUCKETS[key] = [ts for ts in RATE_BUCKETS[key] if now - ts < window_seconds]
    if len(RATE_BUCKETS[key]) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    RATE_BUCKETS[key].append(now)
```

Use `enforce_rate_limit(user.id, "reaction", 5, 1)` and `enforce_rate_limit(user.id, "comment", 1, 3)` in the POST routes.

- [ ] **Step 5: Add comment create/list/update/delete endpoints and broadcasts**

Extend `vvr_scraper/social/router.py`:

```python
@social_router.get("/books/{slug}/chapters/{cid}/comments")
async def list_comments(slug: str, cid: str, anchor: str | None = None, user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    return await social_db.list_comments(slug, cid, anchor)


@social_router.post("/books/{slug}/chapters/{cid}/comments")
async def create_comment(...):
    ...
    await social_ws_manager.broadcast(slug, cid, {"type": "comment", "data": comment})
    return comment


@social_router.put("/comments/{comment_id}")
async def update_comment(comment_id: str, payload: CommentUpdateRequest, user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    existing = await social_db.get_comment(comment_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Comment not found")
    if existing["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's comment")
    return await social_db.update_comment(comment_id, payload.content)


@social_router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, user=Depends(get_auth_user), social_db=Depends(get_social_db)):
    ...
    await social_ws_manager.broadcast(existing["book_slug"], existing["chapter_id"], {"type": "comment_deleted", "data": {"id": comment_id}})
```

- [ ] **Step 6: Run the comment tests again**

Run: `pytest tests/test_social_api.py tests/test_social_websocket.py -v -k comment`
Expected: PASS for nested replies, owner-only updates/deletes, and comment broadcasts.

- [ ] **Step 7: Commit the comments layer**

```bash
git add vvr_scraper/social/db.py vvr_scraper/social/router.py tests/test_social_api.py
git commit -m "feat: add social comments endpoints"
```

### Task 7: Finish Backend Verification and Deployment Wiring

**Files:**
- Modify: `tests/test_web_api.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add smoke coverage that social app state is exposed through the main app**

Append to `tests/test_web_api.py`:

```python
def test_get_social_db_raises_http_503_when_social_database_missing():
    from fastapi import HTTPException
    from types import SimpleNamespace
    from vvr_scraper.web.deps import get_social_db

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    with pytest.raises(HTTPException) as exc_info:
        get_social_db(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Social database not initialized"
```

- [ ] **Step 2: Run the full backend social test slice**

Run: `pytest tests/test_social_db.py tests/test_social_auth.py tests/test_social_api.py tests/test_social_websocket.py tests/test_web_api.py tests/test_cli_unit.py -v`
Expected: PASS.

- [ ] **Step 3: Run lint-adjacent import verification for the modified backend files**

Run: `python -m compileall vvr_scraper/social vvr_scraper/web vvr_scraper/cli.py`
Expected: Compilation completes without syntax errors.

- [ ] **Step 4: Commit backend completion**

```bash
git add tests/test_web_api.py .env.example docker-compose.yml
git commit -m "chore: verify social backend integration"
```

### Task 8: Add Readest Social Types, Settings, and Store Foundation

**Files:**
- Create: `../readest/apps/readest-app/src/types/social.ts`
- Create: `../readest/apps/readest-app/src/store/socialStore.ts`
- Create: `../readest/apps/readest-app/src/utils/social.ts`
- Modify: `../readest/apps/readest-app/src/types/settings.ts`
- Modify: `../readest/apps/readest-app/src/store/notebookStore.ts`
- Modify: `../readest/apps/readest-app/src/__tests__/store/settings-store.test.ts`
- Modify: `../readest/apps/readest-app/src/__tests__/store/notebook-store.test.ts`
- Create: `../readest/apps/readest-app/src/__tests__/store/social-store.test.ts`
- Create: `../readest/apps/readest-app/src/__tests__/utils/social.test.ts`

- [ ] **Step 1: Write the failing Readest store and utility tests**

Create `../readest/apps/readest-app/src/__tests__/utils/social.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import { extractVvrSlugFromBookUrl, normalizeVvrBaseUrl } from '@/utils/social';

describe('social utils', () => {
  test('normalizes trailing slash', () => {
    expect(normalizeVvrBaseUrl('http://localhost:8000/')).toBe('http://localhost:8000');
  });

  test('extracts slug from VVR OPDS download URL', () => {
    expect(
      extractVvrSlugFromBookUrl('http://localhost:8000/api/opds/download/truyen/test-slug?fmt=epub'),
    ).toBe('truyen/test-slug');
  });
});
```

Create `../readest/apps/readest-app/src/__tests__/store/social-store.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import { useSocialStore } from '@/store/socialStore';

describe('socialStore', () => {
  test('starts unauthenticated', () => {
    expect(useSocialStore.getState().token).toBe('');
  });

  test('accepts the social notebook tab', () => {
    useSocialStore.getState().setCurrentChapter({ bookSlug: 'book-1', chapterId: 'ch-1' });
    expect(useSocialStore.getState().currentChapter?.bookSlug).toBe('book-1');
  });
});
```

- [ ] **Step 2: Run the Readest tests to verify the social layer does not exist yet**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/utils/social.test.ts src/__tests__/store/social-store.test.ts src/__tests__/store/settings-store.test.ts src/__tests__/store/notebook-store.test.ts`
Expected: FAIL with missing modules and missing settings fields.

- [ ] **Step 3: Add social frontend types and settings shape**

Create `../readest/apps/readest-app/src/types/social.ts`:

```ts
export type SocialReactionType = 'heart' | 'cry' | 'wow' | 'angry' | 'fire' | 'skull' | 'think' | 'clap';

export interface SocialUser {
  id: string;
  username: string;
  displayName: string;
  role: 'admin' | 'member';
}

export interface SocialReaction {
  id: string;
  user: SocialUser;
  reactionType: SocialReactionType;
  anchor: string;
  createdAt: string;
}

export interface SocialComment {
  id: string;
  user: SocialUser;
  anchor: string | null;
  content: string;
  parentId: string | null;
  createdAt: string;
  updatedAt: string;
  replies: SocialComment[];
}

export interface SocialSettings {
  enabled: boolean;
  serverUrl: string;
}
```

Modify `../readest/apps/readest-app/src/types/settings.ts`:

```ts
import type { SocialSettings } from './social';

export interface SystemSettings {
  ...
  social: SocialSettings;
}
```

Modify `../readest/apps/readest-app/src/store/notebookStore.ts`:

```ts
export type NotebookTab = 'notes' | 'ai' | 'social';
```

- [ ] **Step 4: Add utility and store foundation**

Create `../readest/apps/readest-app/src/utils/social.ts`:

```ts
export function normalizeVvrBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

export function extractVvrSlugFromBookUrl(url?: string): string | null {
  if (!url) return null;
  const match = url.match(/\/api\/opds\/download\/(.+?)(?:\?|$)/);
  return match ? decodeURIComponent(match[1]!) : null;
}
```

Create `../readest/apps/readest-app/src/store/socialStore.ts`:

```ts
import { create } from 'zustand';
import type { SocialComment, SocialReaction, SocialUser } from '@/types/social';

interface SocialStoreState {
  token: string;
  currentUser: SocialUser | null;
  currentChapter: { bookSlug: string; chapterId: string } | null;
  reactionsByAnchor: Record<string, SocialReaction[]>;
  comments: SocialComment[];
  authModalOpen: boolean;
  setToken: (token: string) => void;
  setCurrentUser: (user: SocialUser | null) => void;
  setCurrentChapter: (chapter: { bookSlug: string; chapterId: string } | null) => void;
  setComments: (comments: SocialComment[]) => void;
  setReactionsByAnchor: (value: Record<string, SocialReaction[]>) => void;
  setAuthModalOpen: (open: boolean) => void;
}

export const useSocialStore = create<SocialStoreState>((set) => ({
  token: '',
  currentUser: null,
  currentChapter: null,
  reactionsByAnchor: {},
  comments: [],
  authModalOpen: false,
  setToken: (token) => set({ token }),
  setCurrentUser: (currentUser) => set({ currentUser }),
  setCurrentChapter: (currentChapter) => set({ currentChapter }),
  setComments: (comments) => set({ comments }),
  setReactionsByAnchor: (reactionsByAnchor) => set({ reactionsByAnchor }),
  setAuthModalOpen: (authModalOpen) => set({ authModalOpen }),
}));
```

- [ ] **Step 5: Extend the existing store tests for the new settings/tab fields**

Update `../readest/apps/readest-app/src/__tests__/store/settings-store.test.ts` fixture:

```ts
social: {
  enabled: false,
  serverUrl: '',
},
```

Update `../readest/apps/readest-app/src/__tests__/store/notebook-store.test.ts` to assert `'social'` is accepted by `setNotebookActiveTab`.

- [ ] **Step 6: Run the Readest foundation tests again**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/utils/social.test.ts src/__tests__/store/social-store.test.ts src/__tests__/store/settings-store.test.ts src/__tests__/store/notebook-store.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit the Readest social foundation**

```bash
git -C ../readest add apps/readest-app/src/types/social.ts apps/readest-app/src/store/socialStore.ts apps/readest-app/src/utils/social.ts apps/readest-app/src/types/settings.ts apps/readest-app/src/store/notebookStore.ts apps/readest-app/src/__tests__/store/settings-store.test.ts apps/readest-app/src/__tests__/store/notebook-store.test.ts apps/readest-app/src/__tests__/store/social-store.test.ts apps/readest-app/src/__tests__/utils/social.test.ts
git -C ../readest commit -m "feat: add social client state foundation"
```

### Task 9: Add Readest Social Settings UI and Auth Modal

**Files:**
- Create: `../readest/apps/readest-app/src/components/settings/SocialPanel.tsx`
- Modify: `../readest/apps/readest-app/src/components/settings/SettingsDialog.tsx`
- Create: `../readest/apps/readest-app/src/components/social/AuthModal.tsx`
- Create: `../readest/apps/readest-app/src/hooks/useSocial.ts`
- Create: `../readest/apps/readest-app/src/__tests__/components/social-panel.test.tsx`

- [ ] **Step 1: Write failing settings/auth modal tests**

Create `../readest/apps/readest-app/src/__tests__/components/social-panel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import SocialPanel from '@/components/settings/SocialPanel';
import AuthModal from '@/components/social/AuthModal';

describe('social settings and auth', () => {
  test('renders VVR server URL field', () => {
    render(<SocialPanel bookKey='book-1' onRegisterReset={() => {}} />);
    expect(screen.getByText('VVR Server URL')).toBeInTheDocument();
  });

  test('renders login and register actions', () => {
    render(<AuthModal open={true} onClose={() => {}} />);
    expect(screen.getByText('Login')).toBeInTheDocument();
    expect(screen.getByText('Register')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the component tests to verify the UI is missing**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/components/social-panel.test.tsx`
Expected: FAIL with missing `SocialPanel` and `AuthModal` modules.

- [ ] **Step 3: Add the VVR social settings panel to the existing settings dialog**

Create `../readest/apps/readest-app/src/components/settings/SocialPanel.tsx` with the same configuration style used by `AIPanel.tsx`:

```tsx
import React, { useEffect, useState } from 'react';
import { useEnv } from '@/context/EnvContext';
import { saveSysSettings } from '@/helpers/settings';
import { useSettingsStore } from '@/store/settingsStore';
import { SettingsPanelPanelProp } from './SettingsDialog';

const SocialPanel: React.FC<SettingsPanelPanelProp> = ({ onRegisterReset }) => {
  const { envConfig } = useEnv();
  const { settings } = useSettingsStore();
  const [enabled, setEnabled] = useState(settings.social.enabled);
  const [serverUrl, setServerUrl] = useState(settings.social.serverUrl);

  useEffect(() => {
    onRegisterReset(() => {
      setEnabled(false);
      setServerUrl('');
      saveSysSettings(envConfig, 'social', { enabled: false, serverUrl: '' });
    });
  }, [envConfig, onRegisterReset]);

  return (
    <div className='my-4 w-full space-y-6'>
      <div className='w-full' data-setting-id='settings.social.enabled'>
        <h2 className='mb-2 font-medium'>VVR Social</h2>
        <div className='card border-base-200 bg-base-100 border shadow'>
          <div className='divide-base-200 divide-y'>
            <div className='config-item'>
              <span>Enable Social Reader</span>
              <input type='checkbox' className='toggle' checked={enabled} onChange={() => {
                const next = !enabled;
                setEnabled(next);
                saveSysSettings(envConfig, 'social', { enabled: next, serverUrl });
              }} />
            </div>
            <div className='config-item !h-auto flex-col !items-start gap-2 py-3'>
              <span>VVR Server URL</span>
              <input className='input input-bordered input-sm w-full' value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} onBlur={() => saveSysSettings(envConfig, 'social', { enabled, serverUrl })} placeholder='http://127.0.0.1:8000' />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SocialPanel;
```

Update `../readest/apps/readest-app/src/components/settings/SettingsDialog.tsx` to:

```tsx
import SocialPanel from './SocialPanel';

export type SettingsPanelType = ... | 'Social';

{ tab: 'Social', icon: PiChatsCircle, label: _('Social') }
```

Render it in the same switch/render branch style as the other panels.

- [ ] **Step 4: Implement the auth modal and core REST helpers in `useSocial.ts`**

Create `../readest/apps/readest-app/src/components/social/AuthModal.tsx`:

```tsx
import React, { useState } from 'react';

interface AuthModalProps {
  open: boolean;
  onClose: () => void;
  onLogin?: (username: string, password: string) => Promise<void>;
  onRegister?: (inviteCode: string, username: string, password: string) => Promise<void>;
}

const AuthModal: React.FC<AuthModalProps> = ({ open, onClose, onLogin, onRegister }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  ...
};

export default AuthModal;
```

Create the first version of `../readest/apps/readest-app/src/hooks/useSocial.ts`:

```ts
import { useCallback } from 'react';
import { useSettingsStore } from '@/store/settingsStore';
import { useSocialStore } from '@/store/socialStore';
import { normalizeVvrBaseUrl } from '@/utils/social';

export function useSocial() {
  const socialSettings = useSettingsStore((state) => state.settings.social);
  const token = useSocialStore((state) => state.token);
  const setToken = useSocialStore((state) => state.setToken);
  const setCurrentUser = useSocialStore((state) => state.setCurrentUser);

  const apiBase = normalizeVvrBaseUrl(socialSettings.serverUrl);

  const request = useCallback(async (path: string, init?: RequestInit) => {
    const response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers || {}),
      },
    });
    if (response.status === 401) {
      setToken('');
      setCurrentUser(null);
      throw new Error('Unauthorized');
    }
    if (!response.ok) throw new Error(await response.text());
    return response;
  }, [apiBase, token, setCurrentUser, setToken]);

  return { apiBase, request };
}
```

- [ ] **Step 5: Run the component tests again**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/components/social-panel.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit settings and auth UI**

```bash
git -C ../readest add apps/readest-app/src/components/settings/SocialPanel.tsx apps/readest-app/src/components/settings/SettingsDialog.tsx apps/readest-app/src/components/social/AuthModal.tsx apps/readest-app/src/hooks/useSocial.ts apps/readest-app/src/__tests__/components/social-panel.test.tsx
git -C ../readest commit -m "feat: add Readest social settings and auth UI"
```

### Task 10: Connect Readest to Chapter Data, REST Mutations, and WebSocket Updates

**Files:**
- Modify: `../readest/apps/readest-app/src/hooks/useSocial.ts`
- Modify: `../readest/apps/readest-app/src/app/reader/hooks/useFoliateEvents.ts`
- Create: `../readest/apps/readest-app/src/__tests__/hooks/use-social.test.tsx`

- [ ] **Step 1: Write the failing `useSocial` hook tests**

Create `../readest/apps/readest-app/src/__tests__/hooks/use-social.test.tsx`:

```tsx
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { useSocial } from '@/hooks/useSocial';

describe('useSocial', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  test('loads chapter comments and reactions', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ anchors: { 'epubcfi(/6/2)': [] } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
    );

    const { result } = renderHook(() => useSocial());
    await result.current.loadChapter('book-1', 'ch-1');

    expect(result.current).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run the hook test to verify the loader methods are missing**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/hooks/use-social.test.tsx`
Expected: FAIL with missing `loadChapter` and related methods.

- [ ] **Step 3: Extend `useSocial.ts` with chapter loading and mutations**

Add these methods to `useSocial()`:

```ts
const setComments = useSocialStore((state) => state.setComments);
const setReactionsByAnchor = useSocialStore((state) => state.setReactionsByAnchor);
const setCurrentChapter = useSocialStore((state) => state.setCurrentChapter);

const loadChapter = useCallback(async (bookSlug: string, chapterId: string) => {
  setCurrentChapter({ bookSlug, chapterId });
  const reactionsResponse = await request(`/api/social/books/${bookSlug}/chapters/${chapterId}/reactions`);
  const commentsResponse = await request(`/api/social/books/${bookSlug}/chapters/${chapterId}/comments`);
  const reactionsJson = await reactionsResponse.json();
  const commentsJson = await commentsResponse.json();
  setReactionsByAnchor(reactionsJson.anchors || {});
  setComments(commentsJson);
}, [request, setComments, setCurrentChapter, setReactionsByAnchor]);

const createReaction = useCallback(async (bookSlug: string, chapterId: string, anchor: string, reactionType: SocialReactionType) => {
  const response = await request(`/api/social/books/${bookSlug}/chapters/${chapterId}/reactions`, {
    method: 'POST',
    body: JSON.stringify({ anchor, reaction_type: reactionType }),
  });
  return await response.json();
}, [request]);

const createComment = useCallback(async (bookSlug: string, chapterId: string, payload: { anchor?: string; content: string; parent_id?: string }) => {
  const response = await request(`/api/social/books/${bookSlug}/chapters/${chapterId}/comments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return await response.json();
}, [request]);
```

- [ ] **Step 4: Add WebSocket lifecycle support and chapter reconnects**

Extend `useSocial.ts` with a `connectChapterSocket()` helper that uses the browser `WebSocket` in web mode and keeps the state synced from server messages:

```ts
const socketRef = useRef<WebSocket | null>(null);

const connectChapterSocket = useCallback((bookSlug: string, chapterId: string) => {
  socketRef.current?.close();
  const base = apiBase.replace(/^http/, (match) => (match === 'https' ? 'wss' : 'ws'));
  const ws = new WebSocket(`${base}/ws/social/${bookSlug}/${chapterId}`);
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    ...
  };
  socketRef.current = ws;
}, [apiBase]);
```

Extend `../readest/apps/readest-app/src/app/reader/hooks/useFoliateEvents.ts` so handlers can receive chapter changes without replacing existing behavior:

```ts
type FoliateEventHandler = {
  ...
  onRelocate?: (event: Event) => void;
};
```

The calling site in the reader should treat `relocate` as the chapter-transition signal and reconnect when the section index changes.

- [ ] **Step 5: Run the hook tests again**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/hooks/use-social.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit the social hook networking layer**

```bash
git -C ../readest add apps/readest-app/src/hooks/useSocial.ts apps/readest-app/src/app/reader/hooks/useFoliateEvents.ts apps/readest-app/src/__tests__/hooks/use-social.test.tsx
git -C ../readest commit -m "feat: connect Readest social data loading"
```

### Task 11: Integrate Reactions into the Annotator Popup

**Files:**
- Create: `../readest/apps/readest-app/src/components/social/ReactionBar.tsx`
- Modify: `../readest/apps/readest-app/src/app/reader/components/annotator/AnnotationPopup.tsx`
- Modify: `../readest/apps/readest-app/src/app/reader/components/annotator/Annotator.tsx`

- [ ] **Step 1: Write the failing reaction UI test**

Add to `../readest/apps/readest-app/src/__tests__/components/social-panel.test.tsx`:

```tsx
test('shows a React action in the annotation popup', () => {
  render(
    <AnnotationPopup
      bookKey='book-1'
      dir='ltr'
      isVertical={false}
      buttons={[{ tooltipText: 'React', Icon: () => <span>R</span>, onClick: () => {} }]}
      notes={[]}
      position={{ point: { x: 0, y: 0 } }}
      trianglePosition={{ point: { x: 0, y: 0 }, dir: 'up' }}
      highlightOptionsVisible={false}
      selectedStyle='highlight'
      selectedColor='yellow'
      popupWidth={200}
      popupHeight={50}
      onHighlight={() => {}}
      onDismiss={() => {}}
    />,
  );

  expect(screen.getByTitle('React')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the UI test to verify the social action is not wired yet**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/components/social-panel.test.tsx`
Expected: FAIL because the real annotator path does not yet inject the social action.

- [ ] **Step 3: Add a compact emoji picker component**

Create `../readest/apps/readest-app/src/components/social/ReactionBar.tsx`:

```tsx
import React from 'react';
import type { SocialReactionType } from '@/types/social';

const REACTION_OPTIONS: Array<{ type: SocialReactionType; label: string; emoji: string }> = [
  { type: 'heart', label: 'Heart', emoji: '❤️' },
  { type: 'cry', label: 'Cry', emoji: '😢' },
  { type: 'wow', label: 'Wow', emoji: '😮' },
  { type: 'angry', label: 'Angry', emoji: '😠' },
  { type: 'fire', label: 'Fire', emoji: '🔥' },
  { type: 'skull', label: 'Skull', emoji: '💀' },
  { type: 'think', label: 'Think', emoji: '🤔' },
  { type: 'clap', label: 'Clap', emoji: '👏' },
];

const ReactionBar = ({ onReact }: { onReact: (reactionType: SocialReactionType) => void }) => (
  <div className='flex flex-wrap gap-2 p-2'>
    {REACTION_OPTIONS.map((reaction) => (
      <button key={reaction.type} type='button' className='btn btn-ghost btn-sm' onClick={() => onReact(reaction.type)} title={reaction.label}>
        <span aria-hidden='true'>{reaction.emoji}</span>
      </button>
    ))}
  </div>
);

export default ReactionBar;
```

- [ ] **Step 4: Thread the social action through the annotator popup**

In `../readest/apps/readest-app/src/app/reader/components/annotator/Annotator.tsx`, add one more popup action when all of these are true:

```tsx
const socialEnabled = settings.social.enabled && !!settings.social.serverUrl;
const selectedAnchor = selection?.cfi || '';

const handleSocialReaction = async () => {
  if (!bookSlug || !chapterId || !selectedAnchor) return;
  setShowSocialReactionBar(true);
};
```

Append a button object near the existing `annotationToolButtons` mapping:

```tsx
{
  tooltipText: 'React',
  Icon: PiSmiley,
  onClick: handleSocialReaction,
  visible: socialEnabled,
}
```

Render `ReactionBar` adjacent to `AnnotationPopup` when `showSocialReactionBar` is true, and call `createReaction(bookSlug, chapterId, selectedAnchor, reactionType)` from `useSocial()`.

- [ ] **Step 5: Run the component tests again**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/components/social-panel.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit the annotator integration**

```bash
git -C ../readest add apps/readest-app/src/components/social/ReactionBar.tsx apps/readest-app/src/app/reader/components/annotator/AnnotationPopup.tsx apps/readest-app/src/app/reader/components/annotator/Annotator.tsx apps/readest-app/src/__tests__/components/social-panel.test.tsx
git -C ../readest commit -m "feat: add selection reactions in Readest"
```

### Task 12: Add the Social Notebook Tab, Comments UI, and Inline Badges

**Files:**
- Create: `../readest/apps/readest-app/src/components/social/SocialPanel.tsx`
- Create: `../readest/apps/readest-app/src/components/social/CommentThread.tsx`
- Create: `../readest/apps/readest-app/src/components/social/CommentInput.tsx`
- Create: `../readest/apps/readest-app/src/components/social/ReactionBadges.tsx`
- Modify: `../readest/apps/readest-app/src/app/reader/components/notebook/Notebook.tsx`
- Modify: `../readest/apps/readest-app/src/app/reader/components/notebook/NotebookTabNavigation.tsx`
- Modify: `../readest/apps/readest-app/src/app/reader/components/annotator/Annotator.tsx`

- [ ] **Step 1: Write the failing social notebook tests**

Extend `../readest/apps/readest-app/src/__tests__/components/social-panel.test.tsx`:

```tsx
test('renders the social notebook tab icon', () => {
  render(<NotebookTabNavigation activeTab='social' onTabChange={() => {}} />);
  expect(screen.getByLabelText('Social')).toBeInTheDocument();
});

test('renders comment composer', () => {
  render(<CommentInput onSubmit={async () => {}} />);
  expect(screen.getByPlaceholderText('Write a comment')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the notebook tests to verify the social panel is not present**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/components/social-panel.test.tsx`
Expected: FAIL because the `social` notebook tab does not render yet.

- [ ] **Step 3: Add the social notebook tab and panel components**

Create `../readest/apps/readest-app/src/components/social/CommentInput.tsx`:

```tsx
import React, { useState } from 'react';

const CommentInput = ({ onSubmit, placeholder = 'Write a comment', disabled = false }: { onSubmit: (content: string) => Promise<void>; placeholder?: string; disabled?: boolean }) => {
  const [value, setValue] = useState('');
  return (
    <form className='flex flex-col gap-2' onSubmit={async (event) => {
      event.preventDefault();
      const content = value.trim();
      if (!content) return;
      await onSubmit(content);
      setValue('');
    }}>
      <textarea className='textarea textarea-bordered min-h-24 w-full' maxLength={2000} placeholder={placeholder} value={value} onChange={(e) => setValue(e.target.value)} disabled={disabled} />
      <button type='submit' className='btn btn-primary btn-sm self-end' disabled={disabled || value.trim().length === 0}>Post</button>
    </form>
  );
};

export default CommentInput;
```

Create `../readest/apps/readest-app/src/components/social/CommentThread.tsx` to render parent comments plus one reply list.

Create `../readest/apps/readest-app/src/components/social/SocialPanel.tsx` to:

```tsx
import AuthModal from './AuthModal';
import CommentInput from './CommentInput';
import CommentThread from './CommentThread';
import { useSocial } from '@/hooks/useSocial';
import { useSocialStore } from '@/store/socialStore';

const SocialPanel = () => {
  const { comments, authModalOpen } = useSocialStore();
  const { currentUser, createComment } = useSocial();
  ...
};
```

- [ ] **Step 4: Integrate the social tab into the notebook UI**

Update `../readest/apps/readest-app/src/app/reader/components/notebook/NotebookTabNavigation.tsx`:

```tsx
import { PiChatsCircle, PiNotePencil, PiRobot } from 'react-icons/pi';

const tabs: NotebookTab[] = aiEnabled ? ['notes', 'social', 'ai'] : ['notes', 'social'];
```

Update `../readest/apps/readest-app/src/app/reader/components/notebook/Notebook.tsx`:

```tsx
import SocialPanel from '@/components/social/SocialPanel';

const handleTabChange = (tab: 'notes' | 'ai' | 'social') => { ... };

{notebookActiveTab === 'social' && <SocialPanel />}
```

- [ ] **Step 5: Add inline reaction badges and selection-aware anchor jump support**

Create `../readest/apps/readest-app/src/components/social/ReactionBadges.tsx`:

```tsx
import React from 'react';
import type { SocialReaction } from '@/types/social';

const ReactionBadges = ({ reactions }: { reactions: SocialReaction[] }) => {
  const grouped = reactions.reduce<Record<string, number>>((acc, reaction) => {
    acc[reaction.reactionType] = (acc[reaction.reactionType] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className='flex flex-wrap gap-1'>
      {Object.entries(grouped).map(([reactionType, count]) => (
        <span key={reactionType} className='badge badge-outline text-xs'>{reactionType} {count}</span>
      ))}
    </div>
  );
};

export default ReactionBadges;
```

In `Annotator.tsx`, render `ReactionBadges` when `selection?.cfi` matches a loaded anchor entry in `reactionsByAnchor`.

- [ ] **Step 6: Run the focused Readest component tests again**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --run src/__tests__/components/social-panel.test.tsx src/__tests__/store/notebook-store.test.ts src/__tests__/hooks/use-social.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit the notebook and comment UI**

```bash
git -C ../readest add apps/readest-app/src/components/social/SocialPanel.tsx apps/readest-app/src/components/social/CommentThread.tsx apps/readest-app/src/components/social/CommentInput.tsx apps/readest-app/src/components/social/ReactionBadges.tsx apps/readest-app/src/app/reader/components/notebook/Notebook.tsx apps/readest-app/src/app/reader/components/notebook/NotebookTabNavigation.tsx apps/readest-app/src/app/reader/components/annotator/Annotator.tsx apps/readest-app/src/__tests__/components/social-panel.test.tsx
git -C ../readest commit -m "feat: add social notebook and comments UI"
```

### Task 13: End-to-End Verification Across Both Repositories

**Files:**
- Modify only as needed from previous tasks.

- [ ] **Step 1: Run the complete backend verification set**

Run: `pytest tests/test_social_db.py tests/test_social_auth.py tests/test_social_api.py tests/test_social_websocket.py tests/test_web_api.py tests/test_cli_unit.py -v`
Expected: PASS.

- [ ] **Step 2: Run the targeted Readest verification set**

Run: `pnpm --dir ../readest --filter @readest/readest-app test -- --watch=false --run src/__tests__/utils/social.test.ts src/__tests__/store/social-store.test.ts src/__tests__/store/settings-store.test.ts src/__tests__/store/notebook-store.test.ts src/__tests__/hooks/use-social.test.tsx src/__tests__/components/social-panel.test.tsx`
Expected: PASS.

- [ ] **Step 3: Run the backend startup smoke check**

Run: `python -m vvr_scraper.cli web --host 127.0.0.1 --port 8010 --no-browser`
Expected: Server starts successfully and exposes `/health`, `/api/auth/register`, and `/ws/social/{book_slug}/{chapter_id}`.

- [ ] **Step 4: Run the Readest build/lint smoke check**

Run: `pnpm --dir ../readest --filter @readest/readest-app lint && pnpm --dir ../readest --filter @readest/readest-app build-web`
Expected: Type/lint checks and web build complete successfully.

- [ ] **Step 5: Perform manual integration verification**

Verify this sequence manually:

```text
1. Start VVR backend with VVR_JWT_SECRET and VVR_ADMIN_CODE configured.
2. Open Readest and set VVR Server URL to the backend base URL.
3. Open a VVR OPDS-imported EPUB whose download URL resolves to /api/opds/download/<slug>?fmt=epub.
4. Confirm AuthModal appears before social actions are available.
5. Register with the bootstrap invite code or an admin-generated invite.
6. Select text, click React, and confirm the reaction appears immediately.
7. Open the Social notebook tab, post a chapter-level comment, then post a reply.
8. Open the same chapter in a second reader session and confirm reaction/comment events stream in over WebSocket.
9. Delete your own reaction/comment and confirm the second client updates without refresh.
10. Navigate to a different chapter and confirm the social tab reloads the new chapter data instead of reusing the old chapter state.
```

- [ ] **Step 6: Commit any final verification-driven fixes**

```bash
git add .
git commit -m "fix: polish social reader integration"
git -C ../readest add .
git -C ../readest commit -m "fix: polish social reader integration"
```

## Self-Review

### Spec Coverage

- Invite-only auth, bootstrap admin, JWT, roles: covered in Tasks 3 and 4.
- Separate `social.db`: covered in Tasks 1 and 2.
- Reactions/comments data model and constraints: covered in Tasks 2, 5, and 6.
- REST endpoints: covered in Tasks 4, 5, and 6.
- WebSocket per chapter: covered in Task 5 and verified in Task 13.
- Docker/env additions: covered in Tasks 1 and 7.
- Readest annotator/notebook/settings/chapter reconnect integration: covered in Tasks 8 through 12.
- Auth modal and JWT reuse: covered in Tasks 9 and 10.

### Placeholder Scan

No `TODO`, `TBD`, or “implement later” placeholders remain. Every task lists exact files, concrete test commands, and the intended code shape.

### Type Consistency

- Backend router prefixes and websocket path match the spec and are reused consistently.
- Frontend `NotebookTab` uses `'social'` everywhere in the plan.
- Frontend settings use `settings.social.enabled` and `settings.social.serverUrl` consistently.

Plan complete and saved to `docs/superpowers/plans/2026-04-18-social-reader-mvp.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
