# Web UI Guide

## Starting The Server

Start the Web UI through the CLI:

```bash
vvrt web --host 0.0.0.0 --port 8000
```

Key runtime flags:

- `--host`: bind address. Default: `127.0.0.1`
- `--port`: bind port. Default: `8000`
- `--workers`: number of concurrent download workers to start for web mode
- `--no-browser`: do not auto-open a local browser window
- `--head-playwright` / `--headless-playwright`: override `VVR_PLAYWRIGHT_MODE` for the current server run

At startup, the server initializes the SQLite-backed library database, starts the job worker, launches the download queue workers, and schedules the library auto-sync background task.

## Main Routes And Features

The current FastAPI app includes these major surfaces:

- `/`: serves the main frontend from `static/index.html`
- `/health`: basic health check endpoint returning `{"status": "ok"}`
- `/api/search`: proxy search endpoint for Valvrare Team search
- `/api/chapters`: returns the chapter tree for a given `slug`
- `/api/story_info`: returns detailed story metadata
- `/api/settings`: reads and updates persisted server settings
- `/api/download`: queues a legacy direct download request
- `/api/jobs`, `/api/jobs/{job_id}`: list and inspect queued job-runner jobs
- `/api/tasks/{task_id}/logs`: read buffered task logs
- `/api/tasks/{task_id}/pause`, `/resume`, `/cancel`: task lifecycle controls
- `/api/novels/manifest`: returns a generated `manifest.json` under the novels output tree
- `/api/browse`: opens a host-native folder picker when the environment supports it
- `/api/freesound/auth`, `/api/freesound/callback`: Freesound OAuth endpoints
- `/novels`: static mount for generated output files
- `/static`: static frontend assets
- `/opds/...`: OPDS catalog and download routes
- `/api/voices/...`: Community Voice Bank (upload, list, vote, preview, etc.)
- `/api/correction/...`: character profile correction and voice assignment

## Community Voice Bank

The Web UI integrates with the Community Voice Bank for OmniVoice cloning:

### Voice Bank Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/voices/upload` | Upload a new voice sample with audio, ref_text, name, gender, age_group |
| GET | `/api/voices/me` | List current user's uploaded voices |
| GET | `/api/voices/community` | Browse public community voices (filter by tag, gender, age_group, sort) |
| GET | `/api/voices/{voice_id}` | Get voice details |
| GET | `/api/voices/{voice_id}/audio` | Download voice audio file |
| PATCH | `/api/voices/{voice_id}` | Update voice metadata (name, description, mood, tags) |
| PATCH | `/api/voices/{voice_id}/publish` | Make voice public in community gallery |
| PATCH | `/api/voices/{voice_id}/delist` | Remove voice from community gallery |
| DELETE | `/api/voices/{voice_id}` | Delete voice sample |
| POST | `/api/voices/{voice_id}/vote` | Vote on a voice (`{"vote": 1}` or `{"vote": -1}`) |
| POST | `/api/voices/{voice_id}/preview` | Generate TTS preview using the voice |

### Character Correction Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/correction/{slug}/chapters` | List chapters with .script.json files |
| GET | `/api/correction/{slug}/chapter/{chapter_idx}/script` | Get script JSON for editing |
| POST | `/api/correction/{slug}/chapter/{chapter_idx}/save` | Save corrected script segments |
| POST | `/api/correction/{slug}/apply-similar` | Apply role change to similar segments across chapters |
| GET | `/api/correction/{slug}/characters` | Get character profiles for the novel |
| PUT | `/api/correction/{slug}/characters/{character_name}` | Update character (voice_id, color, aliases, voice_bank_id) |
| GET | `/api/correction/voices/list` | List available TTS voices |
| GET | `/api/correction/voices/preview` | Generate preview with voice_id or ref_audio_path |

Character profiles now support `ref_audio_path`, `ref_text`, and `voice_bank_id` for persistent voice assignments.

## WebSocket Logs And Task Updates

The Web UI exposes a WebSocket endpoint at `/ws/tasks`.

That socket is backed by the shared connection manager in `vvr_scraper.web.state`, and Loguru is configured with a `websocket_sink` so runtime logs can be streamed to connected clients.

The current endpoint keeps the connection open by receiving messages until the client disconnects.

## Task WebSocket Protocol

The `/ws/tasks` endpoint provides real-time updates for download and scraping tasks.

### Connection Lifecycle

1. **Connect**: Client opens a WebSocket connection to `/ws/tasks`
2. **Accept**: Server accepts the connection via `ConnectionManager.connect()`
3. **Receive**: Client listens for JSON messages until disconnected
4. **Disconnect**: Server removes the connection via `ConnectionManager.disconnect()` when the client closes

### Message Types

All messages are JSON objects with a `type` field:

| Type | Fields | Description |
|---|---|---|
| `status` | `task_id`, `status` | Task state change (queue, start, pause, export) |
| `info` | `task_id`, `title` | Story metadata when resolved |
| `progress` | `task_id`, `percent`, `msg` | Download progress update |
| `complete` | `task_id`, `path` | Task finished successfully |
| `error` | `task_id`, `error` | Task failed with error message |
| `log` | `task_id`, `level`, `message`, `time` | Runtime log entry |

### Example Messages

**Task queued:**
```json
{"type": "status", "task_id": "abc-123", "status": "In Queue..."}
```

**Story resolved:**
```json
{"type": "info", "task_id": "abc-123", "title": "My Novel Title"}
```

**Progress update:**
```json
{"type": "progress", "task_id": "abc-123", "percent": 45, "msg": "Downloaded 45/100 chapters"}
```

**Export starting:**
```json
{"type": "status", "task_id": "abc-123", "status": "Exporting files..."}
```

**Task completed:**
```json
{"type": "complete", "task_id": "abc-123", "path": "/path/to/output/My Novel Title"}
```

**Task error:**
```json
{"type": "error", "task_id": "abc-123", "error": "Too many chapters failed to download"}
```

**Task paused:**
```json
{"type": "status", "task_id": "abc-123", "status": "Paused"}
```

**Log entry:**
```json
{"type": "log", "task_id": "abc-123", "level": "INFO", "message": "Chapter 10 downloaded", "time": "14:32:15"}
```

### Implementation Details

The WebSocket system is implemented in `vvr_scraper/web/state.py`:

- **ConnectionManager**: Manages active WebSocket connections and broadcasts messages to all connected clients
- **websocket_sink**: Loguru sink that captures log records and broadcasts them as `log` type messages
- **DownloadManager**: Queues tasks and broadcasts status updates via `manager.broadcast()`

## Where Settings Are Stored

Web settings are loaded from and saved to `vvr_settings.json` through `load_vvr_settings()` and `save_vvr_settings()`.

Current persisted settings include:

- `num_workers`
- `default_output_folder`
- audio drama timing and mix defaults such as `crossfade_default_ms`, `crossfade_battle_ms`, `voice_overlay_offset_ms`, `gap_between_segments_ms`, and `bgm_volume_db`

The settings file is stored through the project config-path helper, not directly in the repository root.

## Metrics And Health Checks

- `/health` is the simplest availability probe.
- Prometheus metrics are exposed when `prometheus_fastapi_instrumentator` is importable.

The app currently calls `Instrumentator().instrument(app).expose(app)`, so in normal installs with that dependency present, the metrics endpoint is available without extra application code changes.

## Operational Notes

- The `/api/browse` endpoint depends on host-native desktop tooling such as `zenity`, `kdialog`, or `tkinter`. It is mainly useful in local desktop runs and may not work in headless or containerized deployments.
- The app mounts `/novels` from the configured `default_output_folder`, creating that directory if needed at startup.
- OPDS routes are part of the same app, but access depends on the configured OPDS authentication environment variables documented in `docs/library-opds.md`.
- The web server temporarily sets `VVR_PLAYWRIGHT_MODE` for the current run when a CLI override is passed, then restores the previous environment state on shutdown.
