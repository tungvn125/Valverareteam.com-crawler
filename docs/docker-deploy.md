# Docker Deployment Guide

## What The Repository Provides

The repository currently includes:

- `Dockerfile`
- `docker-compose.yml`

The default container startup path runs the Web UI server with:

```text
vvrt web --host 0.0.0.0 --port 8000
```

## Docker Image Characteristics

The `Dockerfile` is a multi-stage build based on `python:3.12-slim`.

### Builder Stage

The builder stage:

- creates a virtual environment at `/opt/venv`
- copies `pyproject.toml` and `vvr_scraper/`
- installs the project with `pip install --no-cache-dir -e .`

### Runtime Stage

The runtime stage:

- installs `ffmpeg`
- installs `curl` for health checks
- installs Chromium runtime dependencies needed by Playwright
- runs `playwright install chromium`
- creates a non-root `vvr` user
- exposes port `8000`
- defines a health check against `http://localhost:8000/health`

Persistent locations declared by the image:

- `/home/vvr/app/novels`
- `/home/vvr/.config/vvr-scraper`

## Build The Image

Build from the repository root:

```bash
docker build -t vvr-scraper .
```

## Run The Container Directly

Start the default Web UI server:

```bash
docker run --rm -p 8000:8000 vvr-scraper
```

Because the image entrypoint is `vvrt`, you can also override the default command and run other CLI flows. Example:

```bash
docker run --rm vvr-scraper <slug> -f EPUB
```

If you want persistent output and config state, mount volumes for the novels directory and config directory.

## Docker Compose Services

The current `docker-compose.yml` defines these services:

- `vvr-web`: main application service
- `db-backup`: scheduled SQLite backup sidecar
- `prometheus`: metrics collection
- `grafana`: dashboard service

### `vvr-web`

The main service:

- builds from the local `Dockerfile`
- publishes `${VVR_PORT:-8000}:8000`
- mounts persistent named volumes for downloaded novels and config state
- uses a `/health` HTTP health check

Current named volumes used by `vvr-web`:

- `novels_data`
- `vvr_config`

### `db-backup`

The backup sidecar:

- uses `alpine:latest`
- mounts the config volume read-only at `/data`
- mounts a backup target volume at `/backups`
- mounts `./scripts/backup_sqlite.sh`
- runs a cron schedule at `0 2 * * *`

### `prometheus` And `grafana`

The compose stack also includes:

- Prometheus on port `9090`
- Grafana on port `3000`

These depend on the application service and assume the app exposes metrics when `prometheus_fastapi_instrumentator` is available in the installed environment.

## Start With Compose

From the repository root:

```bash
docker compose up -d
```

This uses the settings and environment variable interpolation from `docker-compose.yml`.

## Environment Variables In Compose

The compose file currently forwards these notable variables into `vvr-web`:

- `OPENAI_API_KEY`
- `VVR_API_KEY`
- `VVR_BASE_URL`
- `VVR_MODEL`
- `ELEVENLABS_API_KEY`
- `VVR_NARRATOR_VOICE_ID`
- `FREESOUND_CLIENT_ID`
- `FREESOUND_CLIENT_SECRET`
- `VVR_SSR_URL`
- `VVR_OPDS_USER`
- `VVR_OPDS_PASS`
- `VVR_AUTO_SYNC`

Important defaults from the compose file:

- `VVR_PORT` defaults to `8000`
- `VVR_OPDS_USER` defaults to `admin`
- `VVR_AUTO_SYNC` defaults to `0`

`VVR_OPDS_PASS` has no secure default, so set it explicitly before exposing the service.

## Operational Notes

- The image already installs Playwright Chromium and the system libraries needed by that browser.
- Media-heavy paths still depend on valid API credentials and any external service availability they use.
- The backup service expects `./scripts/backup_sqlite.sh` to exist and be mountable from the host checkout.
- Prometheus and Grafana are optional operational services, but they are part of the current compose stack.
