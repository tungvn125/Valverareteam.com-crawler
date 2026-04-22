# Running The Server

This guide covers every way to start the VVR Scraper web server, configure it, and verify it is healthy.

---

## Quick Start

### Local (pip)

```bash
pip install -e .
vvrt web
```

The server starts on `http://127.0.0.1:8000` and opens a browser window automatically.

### Docker Compose

```bash
cp .env.example .env
# edit .env — at minimum set VVR_OPDS_PASS, VVR_JWT_SECRET, VVR_ADMIN_CODE
docker compose up -d
```

The server starts on `http://localhost:8000` (or `${VVR_PORT}`).

---

## CLI Reference

The entry point is `vvrt` (installed from `pyproject.toml [project.scripts]`).

```bash
vvrt web [options]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--host` | str | `127.0.0.1` | Bind address. Use `0.0.0.0` to accept external connections. |
| `--port` | int | `8000` | Bind port. |
| `--workers` | int | `1` | Number of concurrent download queue workers. |
| `--no-browser` | flag | `false` | Do not auto-open a browser window. |
| `--head-playwright` | flag | — | Run Playwright with a visible browser window. |
| `--headless-playwright` | flag | — | Force Playwright headless mode. |

Examples:

```bash
# production-like: all interfaces, 4 workers, no browser
vvrt web --host 0.0.0.0 --port 8000 --workers 4 --no-browser

# force headless scraping in CI
vvrt web --headless-playwright --no-browser

# social admin bootstrap (run once after first start)
vvrt social create-admin --username admin --password "your-secure-password" --display-name "Admin"
```

---

## What Happens At Startup

When the server starts, the FastAPI lifespan handler:

1. **Initializes the main database** at `~/.config/vvr-scraper/vvr_library.db` (SQLite with WAL mode).
2. **Initializes the social database** at `~/.config/vvr-scraper/social.db` (SQLite with WAL mode).
3. **Starts the job worker** for the Universal Task Runner.
4. **Starts download queue workers** (count from `--workers` or persisted settings).
5. **Schedules auto-sync** if `VVR_AUTO_SYNC=1` (checks for novel updates hourly).
6. **Registers Prometheus instrumentation** if `prometheus_fastapi_instrumentator` is installed.

On shutdown, it stops all workers and closes both databases cleanly.

---

## Environment Variables

All variables can be set in the shell environment, a `.env` file in the project root, or via `docker-compose.yml` interpolation.

### Core Server

| Variable | Default | Purpose |
|---|---|---|
| `VVR_PORT` | `8000` | Host port mapping (Docker Compose only). Container always listens on 8000 internally. |
| `VVR_PLAYWRIGHT_MODE` | — | Set to `head` or `headless`. Overridden by CLI flags when present. |
| `VVR_AUTO_SYNC` | `0` | Set to `1` to enable hourly library sync checks. |

### Scraping & Media

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for AI-powered image generation and script parsing. |
| `VVR_API_KEY` | — | API key for the AI Script Parser (Audio Drama / Video). |
| `VVR_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible API endpoints. |
| `VVR_MODEL` | `gpt-4o-mini` | Model name for AI requests. |
| `ELEVENLABS_API_KEY` | — | Required for text-to-speech narration. |
| `VVR_NARRATOR_VOICE_ID` | `ywBZEqUhld86Jeajq94o` | ElevenLabs voice ID for the narrator. |
| `FREESOUND_CLIENT_ID` | — | Optional. Freesound API for BGM/SFX. |
| `FREESOUND_CLIENT_SECRET` | — | Optional. Freesound API secret. |
| `VVR_SSR_URL` | `val-ssr-2kzit.ondigitalocean.app` | SSR proxy hostname (optional). |
| `VVR_NARRATOR_REF_AUDIO` | — | Path to reference audio file for narrator voice cloning. |
| `VVR_OMNIVOICE_DEVICE` | `cuda:0` | Device for OmniVoice TTS (e.g., `cuda:0`, `cpu`). |
| `VVR_VOICE_BANK_DIR` | — | Custom directory for voice bank storage. |
| `VVR_LOG_JSON` | `0` | Set to `1` to enable JSON formatted logging. |

### OPDS Catalog

| Variable | Default | Purpose |
|---|---|---|
| `VVR_OPDS_USER` | `admin` | HTTP Basic Auth username for OPDS routes. |
| `VVR_OPDS_PASS` | — | HTTP Basic Auth password for OPDS routes. **Set this before exposing the service.** |

### Social Reader Auth

| Variable | Default | Purpose |
|---|---|---|
| `VVR_JWT_SECRET` | `change-this-random-secret` | Secret key for signing JWT tokens. |

> ⚠️ **Security Warning**
> - This secret is used to sign all JWT tokens. If compromised, attackers can forge authentication tokens.
> - The default value `change-this-random-secret` is NOT safe for production.
> - Use `openssl rand -hex 32` to generate a strong secret before deploying.
| `VVR_ADMIN_CODE` | — | Bootstrap invite code used by the **web registration endpoint** (`/api/auth/register`) to create the first admin user. The CLI command `vvrt social create-admin` creates an admin directly and does NOT require this code. |

---

## Docker Deployment

### Build

```bash
docker build -t vvr-scraper .
```

The image is a multi-stage build on `python:3.12-slim` that installs Playwright Chromium, ffmpeg, CJK fonts, and creates a non-root `vvr` user.

### Run Standalone

```bash
docker run --rm \
  -p 8000:8000 \
  -v novels_data:/home/vvr/app/novels \
  -v vvr_config:/home/vvr/.config/vvr-scraper \
  -e VVR_JWT_SECRET="$(openssl rand -hex 32)" \
  -e VVR_OPDS_PASS="your-opds-password" \
  vvr-scraper
```

Because the image entrypoint is `vvrt`, you can override the command for one-off tasks:

```bash
# bootstrap a social admin user
docker run --rm \
  -v vvr_config:/home/vvr/.config/vvr-scraper \
  -e VVR_JWT_SECRET="$(openssl rand -hex 32)" \
  vvr-scraper \
  social create-admin --username admin --password "secret1234"
```

### Docker Compose Stack

```bash
cp .env.example .env
# edit .env with your secrets
docker compose up -d
```

The stack includes:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `vvr-web` | built from `Dockerfile` | `${VVR_PORT:-8000}:8000` | Main application |
| `db-backup` | `alpine:latest` | — | Daily SQLite backup at 02:00, keeps 7 days |
| `prometheus` | `prom/prometheus:latest` | `9090:9090` | Metrics collection from `/metrics` |
| `grafana` | `grafana/grafana:latest` | `3000:3000` | Dashboards (admin/admin) |

Named volumes:

| Volume | Mount Point | Content |
|---|---|---|
| `novels_data` | `/home/vvr/app/novels` | Downloaded novel output files |
| `vvr_config` | `/home/vvr/.config/vvr-scraper` | Settings JSON, `vvr_library.db`, `social.db` |
| `vvr_backups` | `/backups` | Timestamped database snapshots |

### Viewing Logs

```bash
# follow application logs
docker compose logs -f vvr-web

# check backup cron output
docker compose logs db-backup
```

---

## API Route Map

### Core Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Health check (`{"status": "ok"}`) |
| GET | `/` | none | Main frontend |
| GET | `/api/search` | none | Proxy search |
| GET | `/api/browse` | none | Native folder picker (desktop only) |
| GET | `/api/chapters` | none | Chapter tree for a slug |
| GET | `/api/story_info` | none | Story metadata |
| GET/PUT | `/api/settings` | none | Server settings |
| POST | `/api/download` | none | Legacy direct download |
| GET/POST | `/api/jobs` | none | Job runner CRUD |
| GET | `/api/tasks/{id}/logs` | none | Buffered task logs |
| POST | `/api/tasks/{id}/pause` | none | Pause a task |
| POST | `/api/tasks/{id}/resume` | none | Resume a task |
| POST | `/api/tasks/{id}/cancel` | none | Cancel a task |
| WS | `/ws/tasks` | none | Real-time task log stream |

### Library Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/library` | none | List all library novels |
| POST | `/api/library/sync-all` | none | Queue incremental sync for all novels |
| POST | `/api/library/check` | none | Check which novels have updates |
| POST | `/api/library/scan` | none | Scan for existing download folders |
| POST | `/api/batch-import` | none | Import slugs in bulk |

### OPDS Catalog

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/opds/v1/root` | Basic Auth | OPDS root navigation |
| GET | `/opds/v1/newest` | Basic Auth | Recently added novels |
| GET | `/opds/v1/all` | Basic Auth | All novels (paginated) |
| GET | `/opds/v1/search` | Basic Auth | Search by query |
| GET | `/opds/v1/genres` | Basic Auth | Browse by genre |
| GET | `/opds/v1/authors` | Basic Auth | Browse by author |
| GET | `/api/opds/download/{slug}` | Basic Auth | Download novel file (epub/pdf/mobi/azw3) |

### Social Auth Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | none | Register with invite code. Returns `{user, token}`. |
| POST | `/api/auth/login` | none | Login. Returns `{user, token}`. |
| GET | `/api/auth/me` | Bearer JWT | Get current user profile. |

### Social Admin Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/admin/invites` | Bearer JWT (admin) | Generate an invite code. |
| GET | `/api/admin/invites` | Bearer JWT (admin) | List all invite codes. |

### Social Reader Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/social/books/{slug}/chapters/{cid}/reactions` | Bearer JWT | List reactions (grouped by anchor). |
| POST | `/api/social/books/{slug}/chapters/{cid}/reactions` | Bearer JWT | Add a reaction. Rate limited: 5/second. |
| DELETE | `/api/social/reactions/{id}` | Bearer JWT (owner) | Remove own reaction. |
| GET | `/api/social/books/{slug}/chapters/{cid}/comments` | Bearer JWT | List comments (nested replies). |
| POST | `/api/social/books/{slug}/chapters/{cid}/comments` | Bearer JWT | Add a comment or reply. Rate limited: 1/3seconds. |
| PUT | `/api/social/comments/{id}` | Bearer JWT (owner) | Edit own comment. |
| DELETE | `/api/social/comments/{id}` | Bearer JWT (owner) | Delete own comment. |
| WS | `/ws/social/{book_slug}/{chapter_id}` | none | Real-time reaction/comment updates for a chapter. |

### Static Mounts

| Path | Source |
|---|---|
| `/novels` | Configured output folder (default: `novels/`) |
| `/static` | `vvr_scraper/static/` |

### Download Routes

The legacy download endpoint queues scraping tasks directly:

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/download` | none | Queue a direct download request |

**Request Body** (`DownloadRequest` model):

| Field | Type | Default | Description |
|---|---|---|---|
| `slug` | string | required | Novel slug or full URL for custom sources |
| `formats` | list[string] | `["EPUB"]` | Output formats: `EPUB`, `PDF`, `HTML`, `MD`, `TXT`, `MP3`, `AD-MP3` |
| `grouping` | string | `"tatca"` | Chapter grouping strategy |
| `tasks` | integer | `5` | Number of concurrent scraping tasks |
| `skip_illustrations` | boolean | `false` | Skip chapters with "Minh họa" in the title |
| `output_folder` | string | `null` | Custom output path (auto-generated if null) |
| `selected_urls` | list[string] | `null` | Specific chapter URLs to download (partial export) |

**Background Task Runner Interaction:**

When a download request is received:

1. The request is validated and a unique `task_id` is generated
2. The task is added to the `DownloadManager` queue via `download_queue.add_task()`
3. `DownloadManager` maintains a pool of worker tasks (configured by `--workers` or `num_workers` setting)
4. Workers run `run_scrape_task()` from `vvr_scraper/web/routes/download.py` which:
   - Resolves story metadata
   - Scrapes chapters with checkpoint/resume support
   - Exports to requested formats
   - Updates the library database
5. Progress is broadcast via WebSocket (`/ws/tasks`) throughout execution

**Checkpoint System:**

Downloads support automatic resume via checkpoint files (`.vvr_checkpoint.json`) stored in the output folder. If a task is interrupted, subsequent runs will skip already-scraped chapters.

---

## Social Database Schema

The social reader uses a separate SQLite database (`social.db`) with the following schema:

### Tables

**`users`** — Registered user accounts

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | UUID v4 user identifier |
| `username` | TEXT | UNIQUE NOT NULL | Unique login name (3-32 chars) |
| `display_name` | TEXT | NOT NULL | Display name shown in UI |
| `hashed_password` | TEXT | NOT NULL | Bcrypt-hashed password |
| `invite_code_used` | TEXT | — | Invite code used for registration |
| `role` | TEXT | NOT NULL | `admin` or `member` |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp |

**`invite_codes`** — Invite code management

| Column | Type | Constraints | Description |
|---|---|---|---|
| `code` | TEXT | PRIMARY KEY | Unique invite code (8-char UUID prefix) |
| `created_by` | TEXT | NOT NULL | User ID who created the code |
| `used_by` | TEXT | — | User ID who used the code (null if unused) |
| `max_uses` | INTEGER | NOT NULL DEFAULT 1 | Maximum number of uses |
| `use_count` | INTEGER | NOT NULL DEFAULT 0 | Current use count |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp |

**`reactions`** — Chapter/paragraph emoji reactions

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | UUID v4 reaction identifier |
| `user_id` | TEXT | NOT NULL | User who created the reaction |
| `book_slug` | TEXT | NOT NULL | Novel identifier |
| `chapter_id` | TEXT | NOT NULL | Chapter identifier |
| `anchor` | TEXT | NOT NULL | EPUB CFI or text anchor location |
| `reaction_type` | TEXT | NOT NULL | One of: `heart`, `cry`, `wow`, `angry`, `fire`, `skull`, `think`, `clap`, `nerd`, `laugh`, `eyes`, `pray`, `sparkles` |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp |

Unique constraint: `(user_id, book_slug, chapter_id, anchor, reaction_type)`

**`comments`** — Chapter comments and replies

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | UUID v4 comment identifier |
| `user_id` | TEXT | NOT NULL | User who created the comment |
| `book_slug` | TEXT | NOT NULL | Novel identifier |
| `chapter_id` | TEXT | NOT NULL | Chapter identifier |
| `anchor` | TEXT | — | Optional EPUB CFI anchor (null for chapter-level) |
| `parent_id` | TEXT | — | Parent comment ID for replies (one level deep only) |
| `content` | TEXT | NOT NULL | Comment text (1-2000 chars) |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp |
| `updated_at` | TEXT | NOT NULL | ISO 8601 timestamp |

### Implementation

The schema is managed by `SocialDatabaseManager` in `vvr_scraper/social/db.py`. Database initialization:

- Sets `PRAGMA journal_mode=WAL` for concurrent reads
- Creates tables if they don't exist
- Located at `~/.config/vvr-scraper/social.db` (or Docker volume `vvr_config`)

---

## Social Reader Setup

The social module adds invite-only authentication and real-time reading features. It uses a separate SQLite database (`social.db`) so it can be enabled or disabled independently.

### First-Time Setup

1. **Generate a strong JWT secret:**

```bash
export VVR_JWT_SECRET="$(openssl rand -hex 32)"
```

2. **Start the server** (or restart if already running).

3. **Create the first admin user:**

```bash
vvrt social create-admin --username admin --password "your-password"
```

Or set `VVR_ADMIN_CODE` in the environment and register through the API:

```bash
export VVR_ADMIN_CODE="my-secret-invite"
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"invite_code": "my-secret-invite", "username": "admin", "password": "your-password"}'
```

4. **Generate invite codes for other users:**

```bash
# get a token first
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}' | jq -r '.token')

# create an invite code
curl -X POST http://localhost:8000/api/admin/invites \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_uses": 1}'
```

### JWT Details

- Algorithm: HS256
- Expiry: 7 days
- Payload: `sub` (user ID), `username`, `role` (`admin` or `member`), `iat`, `exp`
- Header: `Authorization: Bearer <token>`

### Rate Limits

| Action | Limit | Window |
|---|---|---|
| Reactions | 5 | 1 second |
| Comments | 1 | 3 seconds |

Rate limits are per-user, in-process, and return HTTP 429 when exceeded.

### WebSocket Protocol

Connect to `/ws/social/{book_slug}/{chapter_id}` to receive real-time updates.

Messages received from the server:

```json
{"type": "reaction", "data": {"id": "...", "user_id": "...", "reaction_type": "heart", "anchor": "epubcfi(/6/2)", ...}}
{"type": "reaction_deleted", "data": {"id": "..."}}
{"type": "comment", "data": {"id": "...", "content": "...", "parent_id": null, ...}}
{"type": "comment_deleted", "data": {"id": "..."}}
```

Clients can send arbitrary text to keep the connection alive. The server disconnects cleanly when the client closes.

---

## Health Checks & Monitoring

### HTTP Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

The Docker image and compose stack both use this endpoint:

```text
curl -f http://localhost:8000/health
# interval: 30s, timeout: 5s, retries: 3
```

### Prometheus Metrics

If `prometheus_fastapi_instrumentator` is installed, metrics are available at `/metrics`.

In the compose stack, Prometheus scrapes `vvr-web:8000/metrics` every 15 seconds and Grafana is pre-configured at `http://localhost:3000` (admin/admin).

---

## File Locations

| Path | Description |
|---|---|
| `~/.config/vvr-scraper/vvr_library.db` | Main library database (novels, metadata) |
| `~/.config/vvr-scraper/social.db` | Social reader database (users, reactions, comments, invites) |
| `~/.config/vvr-scraper/vvr_settings.json` | Persisted server settings |
| `./novels/` (or configured output folder) | Downloaded novel output files |
| `./error-logs/` | Error logs from failed scraping tasks |

In Docker, these are inside the named volumes `vvr_config` and `novels_data`.

---

## Troubleshooting

### Port already in use

```bash
# find what is using port 8000
lsof -i :8000
# or use a different port
vvrt web --port 8010
```

### Database locked errors

Both databases use WAL mode, which supports concurrent reads. If you see lock errors, ensure no other process has the database open (e.g., a SQLite browser tool or a second server instance).

### Social endpoints return 503

The social database is initialized during the lifespan. If you see `{"detail": "Social database not initialized"}`, the server may not have completed startup. Check the logs for errors during `init_db()`.

### Playwright browser not found

The Docker image installs Chromium automatically. For local runs:

```bash
playwright install chromium
```

### OPDS authentication fails

OPDS routes use HTTP Basic Auth with `VVR_OPDS_USER` and `VVR_OPDS_PASS`. If `VVR_OPDS_PASS` is not set, OPDS routes will reject all requests. Set it in `.env` or the compose environment.
