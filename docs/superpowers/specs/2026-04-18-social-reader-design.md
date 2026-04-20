# VVR Social Reader - Design Spec

## Overview

Add a social reading layer to VVR-Scraper by forking Readest (EPUB reader) and extending VVR backend. Users can react and comment anchored to specific text positions while reading. MVP feature: Social Feed (reactions + threaded comments).

## Architecture

```
┌─────────────────────────────────┐
│         Readest Fork            │
│  ┌───────────┐  ┌────────────┐  │
│  │ EPUB      │  │ Social     │  │
│  │ Reader    │  │ Overlay    │  │
│  │ (foliate) │  │ (React)    │  │
│  └─────┬─────┘  └─────┬──────┘  │
│        │              │         │
│   OPDS connect    REST/WS      │
└────────┼──────────────┼─────────┘
         │              │
         ▼              ▼
┌─────────────────────────────────┐
│       VVR Backend (FastAPI)     │
│  ┌────────┐  ┌──────────────┐   │
│  │Scraper │  │ Social Module │   │
│  │Exporter│  │ - Auth/Invite │   │
│  │OPDS    │  │ - Reactions   │   │
│  │Jobs    │  │ - Comments    │   │
│  └────────┘  │ - WebSocket   │   │
│              └──────────────┘   │
│  ┌────────────┐ ┌────────────┐  │
│  │ books.db   │ │ social.db  │  │
│  │ (existing) │ │ (new)      │  │
│  └────────────┘ └────────────┘  │
└─────────────────────────────────┘
```

Readest fork reads EPUBs via VVR's existing OPDS feed. Social overlay calls VVR REST API and WebSocket. Social module is additive - no changes to existing scraper/exporter/job code.

## Access Control

- **Invite-only**: admin generates invite codes, users register with code + username + password
- **First admin**: created via env var `VVR_ADMIN_CODE` or CLI command `vvrt social create-admin`
- **JWT auth**: stateless, suitable for self-hosted single-instance deployment
- **Roles**: `admin` (manage invites) and `member` (read, react, comment)

## Data Model

All tables live in a separate `social.db` SQLite file, independent from existing `books.db`.

### users

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| username | TEXT, UNIQUE | |
| display_name | TEXT | |
| hashed_password | TEXT | bcrypt |
| invite_code_used | TEXT, FK → invite_codes.code | |
| role | TEXT | 'admin' or 'member' |
| created_at | DATETIME | |

### invite_codes

| Column | Type | Notes |
|---|---|---|
| code | TEXT, UNIQUE, PK | random string |
| created_by | UUID, FK → users.id | |
| used_by | UUID, FK → users.id, nullable | |
| max_uses | INTEGER | default 1 |
| use_count | INTEGER | default 0 |
| created_at | DATETIME | |

### reactions

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| user_id | UUID, FK → users.id | |
| book_slug | TEXT | matches VVR slug system |
| chapter_id | TEXT | chapter identifier |
| anchor | TEXT | opaque string from Readest (CFI or similar) |
| reaction_type | TEXT | enum: heart, cry, wow, angry, fire, skull, think, clap |
| created_at | DATETIME | |

UNIQUE constraint on (user_id, book_slug, chapter_id, anchor, reaction_type).

### comments

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| user_id | UUID, FK → users.id | |
| book_slug | TEXT | |
| chapter_id | TEXT | |
| anchor | TEXT, nullable | null = chapter-level comment |
| parent_id | UUID, FK → comments.id, nullable | for threaded replies, max 1 level deep |
| content | TEXT | max 2000 chars |
| created_at | DATETIME | |
| updated_at | DATETIME | |

`anchor` is an opaque string - whatever Readest sends, stored as-is. Not parsed or interpreted by backend.

## API Endpoints

### Auth

```
POST /api/auth/register
  Body: {invite_code, username, password}
  Response: {user, token}

POST /api/auth/login
  Body: {username, password}
  Response: {user, token}

GET /api/auth/me
  Headers: Authorization: Bearer <jwt>
  Response: {user}
```

### Admin (role=admin)

```
POST /api/admin/invites
  Body: {max_uses?: int}  (default 1)
  Response: {code, max_uses, use_count, created_at}

GET /api/admin/invites
  Response: [{code, max_uses, use_count, created_by, used_by, created_at}]
```

### Social (requires JWT)

```
GET /api/social/books/{slug}/chapters/{cid}/reactions
  Query: ?anchor=... (optional, filter by anchor)
  Response: [{id, user, reaction_type, anchor, created_at}]
  Grouped by anchor in response for efficient rendering.

POST /api/social/books/{slug}/chapters/{cid}/reactions
  Body: {anchor, reaction_type}
  Response: {id, reaction_type, anchor, created_at}
  Rate limit: 5/second

DELETE /api/social/reactions/{id}
  Response: 204
  Only own reactions.

GET /api/social/books/{slug}/chapters/{cid}/comments
  Query: ?anchor=... (optional, filter by anchor. null = chapter-level)
  Response: [{id, user, anchor, content, parent_id, created_at, updated_at, replies: [...]}]

POST /api/social/books/{slug}/chapters/{cid}/comments
  Body: {anchor?, content, parent_id?}
  Response: {id, content, anchor, created_at}
  Rate limit: 1 per 3 seconds

PUT /api/social/comments/{id}
  Body: {content}
  Only own comments.

DELETE /api/social/comments/{id}
  Only own comments.
```

### WebSocket

```
WS /ws/social/{book_slug}/{chapter_id}
  Client connects when opening a chapter.
  Server broadcasts to all clients in same chapter:

  Messages (server → client):
    {"type": "reaction", "data": {id, user, reaction_type, anchor}}
    {"type": "comment", "data": {id, user, anchor, content, parent_id}}
    {"type": "reaction_deleted", "data": {id}}
    {"type": "comment_deleted", "data": {id}}

  Messages (client → server):
    none (client uses REST for mutations, WS is receive-only for real-time updates)
```

No persistent queue. Offline clients fetch missed data via REST on reconnect.

## Readest Fork Changes

Readest is a Tauri + Next.js monorepo using foliate-js for EPUB rendering. Key facts from exploring the codebase:

- `BookNote` type (`src/types/book.ts`) already has `cfi: string` field
- `Annotator.tsx` handles text selection and shows popup with action buttons
- `AnnotationPopup.tsx` renders toolbar on text selection
- `Notebook.tsx` is a right-side panel with tabs (annotations, bookmarks, chat)
- `SideBar.tsx` is a left-side panel with TOC, search
- `useTextSelector.ts` captures text selection and position
- `useFoliateEvents.ts` hooks into foliate view events including chapter navigation
- CFI system via `foliate-js/epubcfi.js`

### New files

```
apps/readest-app/src/
├── components/social/
│   ├── SocialPanel.tsx        # right-side panel, reactions + comments
│   ├── ReactionBar.tsx        # inline emoji picker on text selection
│   ├── ReactionBadges.tsx     # small emoji counts rendered inline in text
│   ├── CommentThread.tsx      # threaded comment list
│   ├── CommentInput.tsx       # comment input field
│   └── AuthModal.tsx          # login/register modal
├── hooks/
│   └── useSocial.ts           # API calls + WebSocket connection
├── store/
│   └── socialStore.ts         # zustand store for social state
```

### Modified files

1. **`Annotator.tsx`** - add "React" button to the annotation toolbar buttons array alongside highlight/copy/search
2. **`AnnotationPopup.tsx`** - pass social reaction callback through props
3. **`Notebook.tsx`** - add "Social" tab alongside existing annotations/bookmarks/chat tabs
4. **`NotebookTabNavigation.tsx`** (if exists) or equivalent tab component - add Social tab icon
5. **Settings page** - add VVR server URL configuration field
6. **`useFoliateEvents.ts`** - hook chapter change events to reconnect WebSocket for new chapter

### Integration points

- Text selection flow: user selects text → `useTextSelector` captures CFI → show popup with "React" button → call VVR API
- Chapter navigation: `useFoliateEvents` fires on chapter change → `useSocial` reconnects WebSocket to new chapter → fetch existing reactions/comments via REST
- Social panel: tab in Notebook panel → shows all reactions/comments for current chapter, grouped by anchor → tap to jump to position

### Auth flow in Readest

- First launch with VVR server configured → show AuthModal
- Login/register → store JWT in app storage
- JWT attached to all social API calls
- If 401 → show AuthModal again

## Deployment

### Docker Compose additions

No new services. Add env vars to existing VVR container:

```yaml
environment:
  - VVR_JWT_SECRET=<random-string>
  - VVR_ADMIN_CODE=<initial-admin-invite-code>
```

### New files in VVR backend

```
vvr_scraper/
├── social/
│   ├── __init__.py
│   ├── router.py              # FastAPI routers (auth, admin, social)
│   ├── models.py              # Pydantic request/response models
│   ├── db.py                  # social.db connection, table creation, queries
│   ├── auth.py                # JWT generation/validation, password hashing, invite logic
│   └── websocket.py           # connection manager, broadcast per chapter
```

Mount into existing FastAPI app:

```python
from vvr_scraper.social.router import router as social_router
from vvr_scraper.social.auth import router as auth_router, admin_router

app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(social_router, prefix="/api/social")
```

## Future expansions (out of scope for MVP)

These features build on top of the social foundation:

1. **Emotional Heatmap** - aggregate reaction data by chapter/position, render as visual overlay showing community emotional peaks. Data already captured via reactions.

2. **Mystery/Clue Hunt** - admin hides clues in EPUB/audio/video exports. Community cooperates to find them. Requires leaderboard and achievement system.

3. **Community Dubbing** - users submit voice recordings for characters. Voting and ranking system.

4. **AI Moderation** - auto-flag inappropriate comments/reactions using LLM.

5. **Federation** - allow multiple VVR instances to sync social data. Requires ActivityPub or similar protocol.

## Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Reader client | Fork Readest | Modern stack (Tauri + Next.js), already has CFI, annotations, OPDS support |
| Backend approach | Extend VVR backend | Avoid microservice overhead for self-hosted single-instance |
| Database | Separate social.db | Independent backup/migrate/drop without affecting library data |
| Anchor format | Opaque string from Readest | Don't parse or interpret, let client handle it |
| Auth | Invite code + JWT | Simple, self-hosted friendly, no OAuth dependency |
| Real-time | WebSocket per chapter | Receive-only, REST for mutations, no persistent queue |
| Comments threading | Max 1 level deep | Keeps MVP simple, can deepen later |
| Reaction types | 8 fixed emojis | Prevent chaos at launch, extensible later |
