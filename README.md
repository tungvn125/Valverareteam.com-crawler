# VVR-Scraper

> This repo have gone wrong, and it is so slopy.

## Overview

VVR-Scraper is a Python 3.12+ command-line and web tool for downloading and exporting stories from Valvrare Team into multiple output formats. The package exposes `vvrt` as its CLI entry point and also includes a FastAPI-based Web UI for managing downloads, job execution, and library sync, alongside separate OPDS feed endpoints for reader clients.

## Current Capabilities

- Download stories by slug from the `vvrt` CLI.
- Export output as `PDF`, `EPUB`, `HTML`, `MD`, `TXT`, `MP3`, `AD-MP3`, or `MP4`.
- Choose download scope with all chapters, selected volumes, or selected chapters.
- Run a Web UI with task queue workers, health checks, and Prometheus metrics endpoints.
- Persist local library and settings data under the app config directory.
- Run the containerized Web UI with Docker or Docker Compose.

## System Requirements

- Python 3.12+
- FFmpeg for audio and video workflows
- Playwright with Chromium installed for scraping and rendering paths

## Installation

Install the package in your current environment:

```bash
pip install -e .
```

Install the Playwright browser runtime required by the scraper:

```bash
playwright install chromium
```

If you plan to generate `MP3`, `AD-MP3`, or `MP4` output, make sure `ffmpeg` is available on your system path before running `vvrt`.

## CLI Quickstart

`vvrt` is the package entry point defined in `pyproject.toml`.

Download a story as EPUB:

```bash
vvrt <slug> -f EPUB
```

Notes:

- `<slug>` is passed as the positional story argument.
- The CLI also supports `--all`, `--volumes`, `--chapters`, `--output`, `--gop`, `--head-playwright`, and `--headless-playwright`.
- `EPUB` is the default format, but the explicit example above matches the supported `--format` choices in code.

## Web UI Quickstart

Start the web server from the CLI:

```bash
vvrt web --host 0.0.0.0 --port 8000
```

Useful related flags:

- `--workers` to control concurrent download workers in web mode
- `--no-browser` to avoid opening a local browser automatically
- `--head-playwright` or `--headless-playwright` to control browser mode used by scraping tasks

The underlying server is implemented with FastAPI and Uvicorn. In local CLI usage, the default host is `127.0.0.1` and the default port is `8000` unless you override them.

## Environment Configuration

The project can run with no extra environment variables for basic CLI scraping and local web usage, but some features depend on optional configuration:

- `VVR_API_KEY`, `VVR_BASE_URL` for AI-assisted audio drama and related workflows
- `ELEVENLABS_API_KEY`, `VVR_NARRATOR_VOICE_ID` for voice generation
- `OPENAI_API_KEY` for image generation features
- `FREESOUND_CLIENT_ID`, `FREESOUND_CLIENT_SECRET` for Freesound integration
- `VVR_SSR_URL` to override the SSR endpoint used during scraping
- `VVR_OPDS_USER`, `VVR_OPDS_PASS` to configure OPDS access; current OPDS routes expect both values and return a configuration error when they are missing
- `VVR_AUTO_SYNC=1` to enable periodic library auto-sync in web mode
- `VVR_PLAYWRIGHT_MODE` to control Playwright mode at runtime
- `VVR_TTS_PROVIDER` to select the TTS provider (`elevenlabs`, `openai`, or `omnivoice`)
- `OPENAI_TTS_API_KEY` for OpenAI TTS API access (when using OpenAI TTS provider)
- `OPENAI_TTS_BASE_URL` for custom OpenAI-compatible TTS endpoints
- `OMNIVOICE_MODEL_PATH` for local OmniVoice TTS model path
- `VVR_OMNIVOICE_DEVICE` to specify the device for OmniVoice TTS (e.g., `cuda:0`, default: `cuda:0`)
- `VVR_VOICE_BANK_DIR` to specify a custom voice bank storage directory
- `VVR_NARRATOR_REF_AUDIO` to provide a reference audio file for the narrator voice
- `VVR_LOG_JSON` to enable JSON logging format (set to `1`)
- `VVR_JWT_SECRET` for signing JWT tokens in the social reader (change in production)
- `VVR_ADMIN_CODE` for bootstrapping the first admin user in the social reader
- `VVR_MODEL` for AI model selection (default: `gpt-4o-mini`)

The provided Docker Compose setup exposes the Web UI on `${VVR_PORT:-8000}`, Prometheus on `9090`, Grafana on `3000`, and maps persistent data with named volumes.

## Detailed Docs

- [CLI guide](docs/cli.md)
- [Web UI guide](docs/web-ui.md)
- [Job runner guide](docs/job-runner.md)
- [Library and OPDS guide](docs/library-opds.md)
- [Media pipeline guide](docs/media-pipeline.md)
- [Docker deployment guide](docs/docker-deploy.md)
- [Contributing guide](CONTRIBUTING.md)

The Web UI is designed primarily for local desktop usage. Features that rely on host-native dialogs, such as the folder picker used by the `Browse...` action, may not work in headless or containerized deployments.

## Disclaimer

This project is intended for personal-use automation and local archival workflows. You are responsible for respecting copyright, site terms, and any applicable laws when using it. Do not use the scraper in abusive ways, including aggressive repeated requests or other behavior that could disrupt the source service.
