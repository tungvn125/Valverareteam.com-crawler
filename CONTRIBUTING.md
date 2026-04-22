# Contributing to VVR-Scraper

## Local Setup

This repository uses Python 3.12+ according to `pyproject.toml`, and its CLI entry point is `vvrt`, which maps to `vvr_scraper.cli:main`.

1. Create and activate a virtual environment using your usual workflow.
2. Install the project together with the development dependency group:

```bash
uv pip install -e .[dev]
```

3. If you are working on scraping or rendering flows that use Playwright, install the browser runtime after installing dependencies:

```bash
playwright install chromium
```

4. If you touch audio or video workflows, make sure `ffmpeg` is available on your `PATH`.

## Run Tests And Lint

Before opening a change, run at least the following commands from the repository root:

```bash
pytest
ruff check .
ruff format .
```

`pytest` covers the Python test suite. `ruff check .` catches lint and import-ordering issues. `ruff format .` rewrites files to match the current formatting rules (`line-length = 120`), so review the diff after running it.

If your change touches the CLI, Web UI, Docker docs, or other user-visible behavior, run the additional verification commands that match the part of the system you changed.

## Codebase Map

- `vvr_scraper/cli.py`: the `vvrt` entry point, argument parsing for normal story downloads, `web`, and `run <file>`.
- `vvr_scraper/web/__init__.py`: FastAPI app setup, router registration, static/novels mounts, and `run_web_server()`.
- `vvr_scraper/web/routes/`: routes for settings, jobs, library, OPDS, correction, download, and other web APIs.
- `vvr_scraper/job_models.py`, `vvr_scraper/job_parser.py`, `vvr_scraper/job_runner.py`: manifest schema, dependency validation, and job execution.
- `vvr_scraper/job_worker.py`: Universal Task Runner worker for executing background jobs from the job queue.
- `vvr_scraper/exporter.py`, `vvr_scraper/audio_drama.py`, `vvr_scraper/video_renderer.py`: ebook, audio, audio drama, and video export pipelines.
- `vvr_scraper/scraper_core.py`: Core scraping logic for fetching and parsing story content from source sites.
- `vvr_scraper/session_manager.py`: HTTP session management with connection pooling and retry handling.
- `vvr_scraper/tao_so_do_cay.py`: Story tree builder and chapter hierarchy management utilities.
- `vvr_scraper/utils.py`: Shared utility functions for file operations, text processing, and data formatting.
- `vvr_scraper/models.py`: Pydantic data models for stories, chapters, and API responses.
- `vvr_scraper/enums.py`: Enumerated types for output formats, download states, and provider options.
- `vvr_scraper/social/`: Social reader module with authentication, reactions, comments, and WebSocket support.
- `vvr_scraper/voice_bank/`: Voice bank management for character-specific TTS voices.
- `vvr_scraper/cli_client/`: CLI client utilities for interactive command-line workflows.
- `vvr_scraper/tts/`: Text-to-speech providers and voice synthesis implementations.
- `vvr_scraper/sources/`: Custom source adapters for different story websites (e.g., lnhako.py, truyenfull.py).
- `tests/`: test suite.
- `docs/`: detailed operational documentation. Prefer adding new long-form docs here when the content is too large for `README.md` or `CONTRIBUTING.md`.

## Commit Conventions

The project still configures `semantic_release` in `pyproject.toml`, so commit messages should follow **Conventional Commits** to keep history readable and avoid breaking release automation.

Basic shape:

```text
<type>[optional scope]: <description>
```

Common commit types:

- `feat`: add a feature.
- `fix`: fix a bug.
- `docs`: change documentation.
- `refactor`: restructure code without directly adding a feature or fixing a bug.
- `test`: add or update tests.
- `chore`: maintenance, build, tooling, or release work.

If your change is breaking, use `feat!:` or add a `BREAKING CHANGE:` footer.

Because `tool.semantic_release` still targets the `master` branch and uses the release commit template `chore(release): {version} [skip ci]`, avoid ad-hoc commit message formats outside these conventions.

## Rules For Docs Changes

- Treat current code and configuration as the source of truth; do not copy old wording forward unless it still matches the repository.
- Use command names, flags, file paths, routes, and environment variables exactly as they appear in code.
- If you mention CLI or web behavior, re-check `vvr_scraper/cli.py` or `vvr_scraper/web/` before merging.
- If documentation mentions setup, testing, linting, or release policy, cross-check `pyproject.toml` first.

## Submitting Changes

1. Create a working branch from `master`.
2. Keep the scope of the change as small as possible.
3. Run `pytest`, `ruff check .`, and `ruff format .` before submitting. If your change affects runtime behavior or operational docs, also run the verification commands that match the part you changed.
4. Review your own diff to make sure the docs and code still agree and that you are not adding guessed instructions.
5. Commit using Conventional Commits.
6. Push the branch and open a pull request with a short summary of the change and how you verified it.
