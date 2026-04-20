# Documentation Rewrite Design

## Goal

Rewrite the repository's user-facing and developer-facing documentation so that it matches the current codebase behavior instead of the archived documentation in `old-doc-bak/`.

## Scope

This documentation rewrite covers the canonical GitHub entry points and the main operational surfaces exposed by the current code:

- Rewrite `README.md` as the main entry document for GitHub visitors.
- Rewrite `CONTRIBUTING.md` as the main contributor and developer guide.
- Add focused documentation under `docs/` for CLI usage, Web UI/API, job manifests, library/OPDS behavior, media pipelines, and Docker deployment.
- Preserve `old-doc-bak/` as archival material only.

This work does not change application code or remove archived documents.

## Audience

The new documentation should serve two audiences equally:

- End users who want to install, configure, and run `vvrt` through CLI or Web UI.
- Developers who need to understand the project structure, local development workflow, testing, and contribution expectations.

## Source Of Truth

The source of truth is the current codebase, especially:

- `pyproject.toml` for package metadata, Python version, dependencies, entry points, and dev tooling.
- `vvr_scraper/cli.py` for CLI modes, flags, and runtime requirements.
- `vvr_scraper/web/__init__.py` and `vvr_scraper/web/routes/*.py` for Web UI, API, library, OPDS, and job endpoints.
- `vvr_scraper/job_models.py` and `vvr_scraper/job_parser.py` for manifest structure and dependency rules.
- `vvr_scraper/exporter.py`, `vvr_scraper/audio_drama.py`, and `vvr_scraper/video_renderer.py` for output formats and external service requirements.

The archived files in `old-doc-bak/` may be used only as historical reference for terminology, examples, or wording. They are not authoritative.

## Information Architecture

The documentation set should be organized as follows:

- `README.md`
- `CONTRIBUTING.md`
- `docs/cli.md`
- `docs/web-ui.md`
- `docs/job-runner.md`
- `docs/library-opds.md`
- `docs/media-pipeline.md`
- `docs/docker-deploy.md`

## Document Responsibilities

### `README.md`

`README.md` should be the onboarding document for GitHub readers. It should include:

- A concise description of what the project does today.
- Key capabilities that are confirmed by the current codebase.
- System requirements, including Python, Playwright browser installation, and FFmpeg where relevant.
- Installation paths for normal users and local source usage.
- Quickstart examples for CLI and Web UI.
- A configuration overview for important environment variables and runtime files.
- A short documentation map linking to the detailed docs under `docs/`.
- A disclaimer section covering personal-use intent, copyright respect, and the need to avoid abusive scraping.

`README.md` should stay high signal. Deep reference material belongs in the dedicated docs.

### `CONTRIBUTING.md`

`CONTRIBUTING.md` should be optimized for GitHub contributors and local developers. It should include:

- Repository setup from source.
- Development dependencies and how to install them.
- Test and lint commands that are actually configured in the repo.
- A concise codebase map for the major modules.
- Commit message expectations, keeping the Conventional Commits guidance that still matches the repo configuration.
- Practical contribution guidance for code changes and documentation changes.

### `docs/cli.md`

This file should document the current CLI behavior exposed through `vvrt`, including:

- Positional modes such as standard scraping, `web`, and `run`.
- Core flags from `vvr_scraper/cli.py`.
- Format choices and grouping choices.
- Playwright mode options.
- Examples that reflect real supported arguments.

### `docs/web-ui.md`

This file should cover the FastAPI-based Web UI and API surface, including:

- How to start the web server.
- Main routes and operational capabilities.
- WebSocket logging/task updates.
- Settings behavior and persistence.
- What the UI manages versus what still requires files or environment setup.

### `docs/job-runner.md`

This file should document the manifest-driven task runner based on the current Pydantic models and parser rules, including:

- Supported job types from `vvr_scraper/job_models.py`.
- Current payload fields and defaults.
- Dependency handling using aliases.
- Validation constraints such as missing dependencies and cycle rejection.
- Examples for crawl and render jobs that match the current schema.

If the current code exposes a `server` job type, the doc should mention it accurately, even if it is lightly documented.

### `docs/library-opds.md`

This file should explain the local library and OPDS behavior confirmed by the web routes, including:

- Library scan and sync endpoints/flows.
- Update checking and `VVR_AUTO_SYNC` behavior.
- Database-backed metadata expectations.
- OPDS availability and any operational caveats visible from the current implementation.

### `docs/media-pipeline.md`

This file should describe the output formats and pipeline prerequisites, including:

- Text and ebook exports.
- MP3 and Audio Drama requirements.
- MP4/cinematic rendering requirements.
- External services or keys used by audio/image generation paths.
- Which dependencies are optional versus required for specific features.

### `docs/docker-deploy.md`

This file should be a dedicated deployment guide for containerized usage, including:

- Build and run flows.
- Docker Compose examples.
- Required environment variables and volumes.
- Port exposure for the Web UI and related services.
- Operational notes specific to running this project in containers.

## Writing Rules

All rewritten docs should follow these rules:

- Prefer factual statements tied to current code over marketing language.
- Avoid listing features that no longer exist or are not visible in the current codebase.
- Separate quickstart instructions from deep reference material.
- Make optional capabilities explicit, especially when they require API keys or native tools.
- Use examples that can be traced back to real commands, flags, routes, or schemas in the repository.
- Keep the tone clear and direct, with Vietnamese content where that matches the existing project voice.

## Verification Strategy

Before considering the rewrite complete, the documentation work should verify:

- Every documented CLI flag or mode appears in the current code.
- Every documented manifest example matches the current `JobManifest` schema.
- Environment variable references align with current code usage.
- File and route references point to existing paths.
- The new docs clearly distinguish canonical docs from archived docs.

## Implementation Notes

The rewrite should prefer updating top-level canonical docs and adding a small set of focused files, rather than creating a large docs tree with duplicated material. The result should be easy to navigate on GitHub and easy to maintain as the code evolves.
