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
- `/novels`: static mount for generated output files
- `/static`: static frontend assets
- `/opds/...`: OPDS catalog and download routes
- `/api/voices/...`: Community Voice Bank (upload, list, vote, preview)
- `/api/correction/...`: character profile correction and voice assignment

## Community Voice Bank

The Web UI integrates with the Community Voice Bank for OmniVoice cloning:

- **Upload voices** via `POST /api/voices/upload`
- **Browse community voices** via `GET /api/voices/community`
- **Preview voices** via `POST /api/voices/{id}/preview`
- **Assign voices to characters** via `PUT /api/correction/{slug}/characters/{name}` with `voice_bank_id`

Character profiles now support `ref_audio_path`, `ref_text`, and `voice_bank_id` for persistent voice assignments.

## WebSocket Logs And Task Updates

The Web UI exposes a WebSocket endpoint at `/ws/tasks`.

That socket is backed by the shared connection manager in `vvr_scraper.web.state`, and Loguru is configured with a `websocket_sink` so runtime logs can be streamed to connected clients.

The current endpoint keeps the connection open by receiving messages until the client disconnects.

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
