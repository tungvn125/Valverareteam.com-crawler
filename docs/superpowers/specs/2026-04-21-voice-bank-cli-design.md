# Voice Bank CLI Client — Design Spec

**Date:** 2026-04-21  
**Status:** Draft, awaiting review  
**Scope:** CLI-based client for the Voice Bank feature (`vvrt-client`)  

---

## 1. Objective

Build a standalone CLI binary (`vvrt-client`) that interacts with the Voice Bank API over HTTP. The client is **not** a scraper replacement — it is a remote client for managing voice samples (upload, browse, vote, preview) on a running VVR server.

---

## 2. Constraints & Assumptions

| Item | Value |
|------|-------|
| Server API | Must be running (FastAPI). Base URL configurable via `--host`/`--port`. |
| Auth | Requires Bearer JWT. Token sourced from: `VVR_TOKEN` env var → `~/.config/vvr/token.json` → interactive login prompt. |
| Entry point | `vvrt-client` (new binary, does not touch existing `vvrt` CLI). |
| Language | Python 3.12+, async (`asyncio` + `httpx`). |
| Output | Rich terminal tables (`rich` library), consistent with existing `vvrt` CLI style. |
| No Social commands | Readest fork already handles social UI. This CLI is Voice Bank **only**. |

---

## 3. Architecture

```
pyproject.toml
└── [project.scripts]
    vvrt-client = "vvr_scraper.cli_client.main:main"

vvr_scraper/
└── cli_client/
    ├── __init__.py
    ├── main.py            # argparse entry point, route dispatch
    ├── client.py          # APIClient: httpx.AsyncClient + auth + error handling
    ├── auth_manager.py    # TokenManager: env → file → login
    ├── voice_commands.py  # all Voice Bank subcommands
    └── display.py         # Rich formatters (tables, colors)
```

**Boundary rule:** `cli_client/` must not import from `scraper_core`, `exporter`, `job_runner`, etc. It may import `utils.get_config_path` for token file location only.

---

## 4. Component Details

### 4.1 `client.py` — `APIClient`

Responsibilities:
- Hold `httpx.AsyncClient` with configurable `base_url`.
- Auto-inject `Authorization: Bearer <token>` on every request via `TokenManager.get_token()`.
- Map HTTP errors to human-readable Vietnamese messages:
  - `401` → "Chưa đăng nhập. Chạy `vvrt-client login`"
  - `403` → "Không có quyền thực hiện"
  - `404` → "Không tìm thấy voice sample"
  - `413` → "File quá lớn (tối đa 30MB)"
  - `429` → "Quá nhiều request, thử lại sau"
  - `500` → "Lỗi server"
- Return parsed JSON dict or raise `CLIError`.

Constructor signature:
```python
class APIClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8000, token: str | None = None):
        # token overrides TokenManager entirely
```

### 4.2 `auth_manager.py` — `TokenManager`

Responsibilities:
- Resolve token from 3 sources (in order):
  1. Constructor-provided token (highest priority)
  2. `VVR_TOKEN` environment variable
  3. `~/.config/vvr/token.json` file
- Validate token expiry before use. JWT tokens expire after **7 days** (`exp` claim).
- If token is expired: delete file, raise `AuthenticationRequired` so caller can prompt re-login.
- If no token found, raise `AuthenticationRequired` so caller can prompt login.
- `login(username, password)` → `POST /api/auth/login` → write file → return user info.
- `logout()` → delete token file.

Token file format:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "alice",
  "user_id": "uuid-from-api-user-id",
  "role": "member",
  "created_at": "2026-04-21T10:00:00Z"
}
```
**Note:** API returns `user["id"]`, stored as `user_id` in the file. `created_at` is generated locally at login time.

### 4.3 `voice_commands.py` — Voice Bank Commands

Each command is an async function that takes `(client: APIClient, args: argparse.Namespace)` and prints output.

| Command | HTTP Method | Endpoint | Description |
|---------|------------|----------|-------------|
| `upload` | `POST` | `/api/voices/upload` | Multipart upload with audio + metadata. Interactive prompt for missing fields. |
| `list` | `GET` | `/api/voices/me` | Paginated list of user's own voices. |
| `community` | `GET` | `/api/voices/community` | Browse public voices with optional tag/gender/age filters. |
| `show <id>` | `GET` | `/api/voices/{id}` | Full detail of one voice sample. |
| `update <id>` | `PATCH` | `/api/voices/{id}` | Update metadata: name, description, mood, tags. Owner only. |
| `delete <id>` | `DELETE` | `/api/voices/{id}` | Delete own voice. Owner only. **Note:** Backend does not support admin deletion of other users' voices. |
| `publish <id>` | `PATCH` | `/api/voices/{id}/publish` | Set visibility to `public`. Owner only. Prints updated voice detail. |
| `delist <id>` | `PATCH` | `/api/voices/{id}/delist` | Set visibility to `delisted`. Owner only. **Note:** Backend does not support admin delisting of other users' voices. |
| `vote <id>` | `POST` | `/api/voices/{id}/vote` | Upvote (`vote=1`) or downvote (`vote=-1`). Prints the new vote score. |
| `download <id>` | `GET` | `/api/voices/{id}/audio` | Download the original reference audio file (WAV). |
| `preview <id>` | `POST` | `/api/voices/{id}/preview` | Generate TTS preview. Save response bytes to temp file via `tempfile`, attempt playback with `aplay`/`ffplay`; otherwise print path. |
| `login` | `POST` | `/api/auth/login` | Delegates to `TokenManager.login()`. |
| `logout` | — | — | Delegates to `TokenManager.logout()`. |

**Upload flags (all):**
- `--audio` / `-a` (required): Path to audio file
- `--name` / `-n` (required): Voice name (3-100 chars)
- `--ref-text` / `-t` (required): Transcript text (min 10 chars)
- `--gender` / `-g` (required): `male` | `female` | `other`
- `--age-group` (required): `child` | `teen` | `young_adult` | `adult` | `elder`
- `--description` (optional): Description text (max 500 chars)
- `--language` (optional, default `vi`): Language code
- `--mood` / `-m` (optional): Mood tag
- `--tags` (optional): Comma-separated tags (max 5)

**Interactive upload flow:**
If any required field is missing, prompt the user via `PromptSession` (same pattern as existing `vvrt voice upload`). Optional fields are skipped if not provided.

**Preview playback:**
- Save to `tempfile.gettempdir()/vvr_preview_{voice_id}.wav` using `tempfile` module.
- Try `aplay` first, then `ffplay`, then `mpv`.
- If none available: print `"File preview saved to: {path}"`.
- Clean up temp file after playback or on exit.

### 4.4 `display.py` — Rich Formatters

Functions:
- `print_voice_table(items, title)` → `rich.Table` with columns: ID, Name, Gender, Age, Duration, Tags, Votes, Visibility.
- `print_voice_detail(voice)` → key-value panel with all fields.
- `print_error(msg)` → `[bold red]Error:[/bold red] {msg}`
- `print_success(msg)` → `[bold green]✓ {msg}[/bold green]`

Visibility color mapping:
- `public` → green
- `private` → yellow
- `delisted` → red

### 4.5 `main.py` — Entry Point & Argparse

Global flags (applies to all commands):
```bash
vvrt-client --host 127.0.0.1 --port 8000 --token "..." <command> ...
```

Subcommands mapped directly to functions in `voice_commands.py`.

---

## 5. CLI Usage Examples

```bash
# Login
vvrt-client login --username alice

# Upload with all flags
vvrt-client upload -a ./voice.wav -n "Minh" -t "Xin chào các bạn" \
  --gender male --age-group young_adult --tags male,vietnamese \
  --description "Giọng nam trẻ" --language vi --mood calm

# Interactive upload (prompts for missing required fields)
vvrt-client upload -a ./voice.wav

# List my voices (paginated)
vvrt-client list --limit 20 --offset 0

# Browse community with filters
vvrt-client community --tag male --gender male --age-group young_adult --sort votes --limit 10

# Show detail
vvrt-client show abc-123-def

# Update metadata
vvrt-client update abc-123-def --name "Minh (updated)" --mood serious

# Publish / delist / delete
vvrt-client publish abc-123-def
vvrt-client delist abc-123-def
vvrt-client delete abc-123-def

# Vote (prints new score)
vvrt-client vote abc-123-def --up

# Download original audio
vvrt-client download abc-123-def --output ./my_voice.wav

# Preview (auto-play if player available)
vvrt-client preview abc-123-def --text "Xin chào thế giới"

# Logout
vvrt-client logout

# Connect to remote server
vvrt-client --host 192.168.1.100 --port 8080 list
```

---

## 6. Data Flow

```
User Input
    ↓
main.py (argparse)
    ↓
voice_commands.py
    ↓
APIClient.request(method, path, **kwargs)
    ↓
TokenManager.get_token()  →  Authorization header
    ↓
httpx.AsyncClient  →  FastAPI Server
    ↓
JSON response  →  display.py  →  Terminal output
```

---

## 7. Error Handling

- All command functions wrapped in try/except `CLIError` (custom exception with message + exit code).
- `httpx.ConnectError` → "Không thể kết nối đến server. Kiểm tra host/port."
- `AuthenticationRequired` → "Chưa có token. Chạy `vvrt-client login`."
- `KeyboardInterrupt` → graceful exit, no stack trace.

**Special HTTP behaviors:**
- `404` on `show`: API returns 404 (not 403) for private voices you don't own, to avoid leaking existence. CLI should display "Không tìm thấy voice sample" without implying permission denied.
- `204` on `delete`: API returns No Content (no body). `display.py` must handle empty responses gracefully — print success message without attempting JSON parse.

---

## 8. Testing Strategy

| Test Type | Scope |
|-----------|-------|
| Unit | `TokenManager` (mock file I/O, mock `httpx` post) |
| Unit | `APIClient` (mock `httpx.AsyncClient` responses) |
| Unit | Each voice command (mock `APIClient` methods) |
| Unit | `display.py` functions (snapshot output) |
| Integration | Start real server, run full CLI workflow via `subprocess` |

---

## 9. Dependencies

No new dependencies. Reuse existing ones from `pyproject.toml`:
- `httpx` (already required)
- `rich` (already required)
- `prompt-toolkit` (already required)
- `loguru` (already required)

---

## 10. Open Questions (Resolved During Brainstorming)

| Question | Decision |
|----------|----------|
| API client or direct DB? | **API client** (configurable host/port). |
| Include Social commands? | **No** — Readest fork handles social UI. |
| Auth flow? | **3-tier**: env var → file → interactive login. |
| Entry point separate or extend `vvrt`? | **Separate binary** `vvrt-client`. |
| Publish need admin approval? | **No** — push immediately (verified in codebase). |

---

## 11. Files to Create (No Modifications to Existing Code)

```
vvr_scraper/cli_client/__init__.py
vvr_scraper/cli_client/main.py
vvr_scraper/cli_client/client.py
vvr_scraper/cli_client/auth_manager.py
vvr_scraper/cli_client/voice_commands.py
vvr_scraper/cli_client/display.py
```

And add to `pyproject.toml`:
```toml
[project.scripts]
vvrt-client = "vvr_scraper.cli_client.main:main"
```

---

## 12. Spec Self-Review Checklist

- [ ] No placeholders/TBD remaining
- [ ] Internal consistency: auth flow matches API requirements
- [ ] Scope check: Voice Bank only, no social, no scraper
- [ ] Ambiguity check: all commands have clear HTTP mappings
