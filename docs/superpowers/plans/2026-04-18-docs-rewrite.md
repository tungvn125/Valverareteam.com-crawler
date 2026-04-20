# Documentation Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the repository's canonical documentation so GitHub readers and contributors get accurate instructions that match the current codebase and verified Docker workflow.

**Architecture:** Create two top-level canonical entry documents (`README.md`, `CONTRIBUTING.md`) plus a small focused `docs/` set for operational surfaces that are too detailed for the README. Each document is written directly from current code and validated with targeted grep/read/build commands instead of relying on archived wording in `old-doc-bak/`.

**Tech Stack:** Markdown, GitHub-flavored Markdown, Python package metadata from `pyproject.toml`, FastAPI routes, Pydantic job models, Docker, Docker Compose

---

## File Structure

- Create: `README.md`
  Main GitHub landing page with overview, install, quickstart, env summary, docs map, and disclaimer.
- Create: `CONTRIBUTING.md`
  Contributor-focused guide for setup, testing, linting, codebase map, and commit conventions.
- Create: `docs/cli.md`
  CLI modes, flags, and real command examples based on `vvr_scraper/cli.py`.
- Create: `docs/web-ui.md`
  Web server startup, route surface, settings, websocket, and operational notes from `vvr_scraper/web/*`.
- Create: `docs/job-runner.md`
  Manifest schema and execution behavior from `vvr_scraper/job_models.py`, `job_parser.py`, and `job_runner.py`.
- Create: `docs/library-opds.md`
  Library sync/scan/check and OPDS behavior based on web routes and auth dependency.
- Create: `docs/media-pipeline.md`
  Export formats and prerequisite services from exporter, audio drama, image generation, and video renderer code.
- Create: `docs/docker-deploy.md`
  Docker image build, compose usage, env vars, volumes, and ports based on the verified `Dockerfile` and `docker-compose.yml`.
- Reference only: `old-doc-bak/README.md`, `old-doc-bak/CONTRIBUTING.md`, `old-doc-bak/task_runner.md`
  Historical wording/examples only; not source of truth.

### Task 1: Create Canonical `README.md`

**Files:**
- Create: `README.md`
- Reference: `pyproject.toml:5-59`
- Reference: `vvr_scraper/cli.py:179-240`
- Reference: `vvr_scraper/web/__init__.py:82-163`
- Reference: `Dockerfile:1-100`
- Reference: `docker-compose.yml:1-100`

- [ ] **Step 1: Confirm the file does not already exist**

Run: `test -f README.md && echo present || echo missing`
Expected: `missing`

- [ ] **Step 2: Gather the facts that must appear in the README**

Run: `rg -n "name =|version =|requires-python =|dependencies =|project.scripts|def main\(|add_argument\(|async def run_web_server|FastAPI\(|playwright install chromium|ENTRYPOINT|CMD" pyproject.toml vvr_scraper/cli.py vvr_scraper/web/__init__.py Dockerfile docker-compose.yml`
Expected: Output includes package name/version, Python requirement, `vvrt` entry point, CLI flags, web startup path, and Docker defaults.

- [ ] **Step 3: Write `README.md` with the agreed sections**

Write a new `README.md` containing these sections in this order:

```md
# VVR-Scraper

## Tổng quan
## Tính năng hiện có
## Yêu cầu hệ thống
## Cài đặt
## Quickstart CLI
## Quickstart Web UI
## Cấu hình môi trường
## Tài liệu chi tiết
## Miễn trách nhiệm
```

The content must explicitly include:

```md
- Python 3.12+
- `vvrt` là entry point CLI
- Playwright browser install requirement for scraping/rendering paths
- FFmpeg requirement for audio/video workflows
- Quickstart for `vvrt <slug> -f EPUB`
- Quickstart for `vvrt web --host 0.0.0.0 --port 8000`
- Links to `docs/cli.md`, `docs/web-ui.md`, `docs/job-runner.md`, `docs/library-opds.md`, `docs/media-pipeline.md`, `docs/docker-deploy.md`, `CONTRIBUTING.md`
- Disclaimer covering personal-use intent, copyright respect, and avoiding abusive scraping
```

- [ ] **Step 4: Verify the README references only real commands and capabilities**

Run: `rg -n "vvrt <slug> -f EPUB|vvrt web --host 0.0.0.0 --port 8000|Playwright|FFmpeg|Miễn trách nhiệm|docs/docker-deploy.md|CONTRIBUTING.md" README.md`
Expected: All required sections and commands appear exactly once or more.

- [ ] **Step 5: Commit the README work**

```bash
git add README.md
git commit -m "docs: add canonical project README"
```

### Task 2: Create Canonical `CONTRIBUTING.md`

**Files:**
- Create: `CONTRIBUTING.md`
- Reference: `pyproject.toml:52-97`
- Reference: `old-doc-bak/CONTRIBUTING.md:1-66`
- Reference: `vvr_scraper/cli.py:711-739`
- Reference: `vvr_scraper/web/__init__.py:82-163`

- [ ] **Step 1: Confirm the file does not already exist**

Run: `test -f CONTRIBUTING.md && echo present || echo missing`
Expected: `missing`

- [ ] **Step 2: Gather the contributor workflow facts**

Run: `rg -n "optional-dependencies|pytest|ruff|semantic_release|branch =|commit_message|target-version|line-length" pyproject.toml`
Expected: Output shows dev dependencies, linting config, and semantic release commit metadata.

- [ ] **Step 3: Write `CONTRIBUTING.md`**

Write a new `CONTRIBUTING.md` with these sections:

```md
# Contributing to VVR-Scraper

## Setup môi trường local
## Chạy test và lint
## Bản đồ codebase
## Quy ước commit
## Quy tắc khi sửa docs
## Quy trình gửi thay đổi
```

The content must mention these exact commands where appropriate:

```bash
uv pip install -e .[dev]
pytest
ruff check .
ruff format .
```

The commit section must retain Conventional Commits guidance because `pyproject.toml` still configures semantic release.

- [ ] **Step 4: Verify the contributor commands and policy references are present**

Run: `rg -n "uv pip install -e \.\[dev\]|pytest|ruff check \.|ruff format \.|Conventional Commits|semantic release" CONTRIBUTING.md`
Expected: All contributor workflow references are present.

- [ ] **Step 5: Commit the contributing guide**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add contributing guide"
```

### Task 3: Write `docs/cli.md`

**Files:**
- Create: `docs/cli.md`
- Reference: `vvr_scraper/cli.py:179-240`
- Reference: `vvr_scraper/cli.py:242-739`

- [ ] **Step 1: Gather the current CLI argument surface**

Run: `rg -n "add_argument\(|choices=|help=|run_manifest\(|run_web_server\(|--head-playwright|--headless-playwright|--all|--volumes|--chapters" vvr_scraper/cli.py`
Expected: Output enumerates the supported flags and mode-specific behavior.

- [ ] **Step 2: Write `docs/cli.md`**

Write a new `docs/cli.md` with these sections:

```md
# CLI Guide

## Entry point `vvrt`
## Chế độ tải truyện thông thường
## Chế độ `web`
## Chế độ `run`
## Lựa chọn chương / volume
## Format xuất file
## Playwright modes
## Ví dụ lệnh
```

Use real flag names from `vvr_scraper/cli.py`. Do not document removed or guessed subcommands.

- [ ] **Step 3: Verify all documented flags exist in code**

Run: `python - <<'PY'
from pathlib import Path
import re
cli = Path('docs/cli.md').read_text(encoding='utf-8')
flags = sorted(set(re.findall(r'`(--[a-z0-9-]+)`', cli)))
print('\n'.join(flags))
PY`
Expected: Prints the flags documented in `docs/cli.md` for manual comparison.

- [ ] **Step 4: Cross-check printed flags against source**

Run: `rg -n "--host|--port|--workers|--no-browser|--head-playwright|--headless-playwright|--all|--volumes|--chapters|--khong-minh-hoa|--render-format|--fps|--format|--gop" vvr_scraper/cli.py`
Expected: Every flag documented in `docs/cli.md` appears in source.

- [ ] **Step 5: Commit the CLI guide**

```bash
git add docs/cli.md
git commit -m "docs: add cli guide"
```

### Task 4: Write `docs/web-ui.md`

**Files:**
- Create: `docs/web-ui.md`
- Reference: `vvr_scraper/web/__init__.py:53-163`
- Reference: `vvr_scraper/web/routes/api.py:27-249`
- Reference: `vvr_scraper/web/routes/jobs.py:20-135`
- Reference: `vvr_scraper/web/models.py:16-69`

- [ ] **Step 1: Gather the current web surface and settings facts**

Run: `rg -n "@router\.(get|post|websocket)|FastAPI\(|Instrumentator|load_vvr_settings|save_vvr_settings|/health|/api/settings|/ws/tasks|/api/jobs|/api/library|/opds" vvr_scraper/web/__init__.py vvr_scraper/web/routes/*.py`
Expected: Output lists the main web endpoints and settings behavior.

- [ ] **Step 2: Write `docs/web-ui.md`**

Write a new `docs/web-ui.md` with these sections:

```md
# Web UI Guide

## Khởi động server
## Các route/chức năng chính
## WebSocket log và task updates
## Settings lưu ở đâu
## Metrics và healthcheck
## Ghi chú vận hành
```

The document must mention `/health`, `/ws/tasks`, settings persistence via `vvr_settings.json`, and Prometheus metrics exposure when instrumentation is available.

- [ ] **Step 3: Verify all named routes/settings files exist in code**

Run: `rg -n "/health|/ws/tasks|vvr_settings.json|metrics|Instrumentator" docs/web-ui.md vvr_scraper/web/__init__.py vvr_scraper/web/routes/*.py vvr_scraper/web/models.py`
Expected: Each route or file named in the guide is present in the code references.

- [ ] **Step 4: Commit the Web UI guide**

```bash
git add docs/web-ui.md
git commit -m "docs: add web ui guide"
```

### Task 5: Write `docs/job-runner.md`

**Files:**
- Create: `docs/job-runner.md`
- Reference: `vvr_scraper/job_models.py:1-82`
- Reference: `vvr_scraper/job_parser.py:1-68`
- Reference: `vvr_scraper/job_runner.py:272-398`
- Reference: `old-doc-bak/task_runner.md:1-82`

- [ ] **Step 1: Gather the current manifest schema and validation rules**

Run: `rg -n "class .*Payload|class .*Job|JobManifest|depends_on|alias_id|priority|playwright_mode|parse_manifest|Cyclic dependency|Dependency .* not found" vvr_scraper/job_models.py vvr_scraper/job_parser.py vvr_scraper/job_runner.py`
Expected: Output shows the supported job types, payload fields, and validation errors.

- [ ] **Step 2: Write `docs/job-runner.md`**

Write a new `docs/job-runner.md` with these sections:

```md
# Job Runner Guide

## Chạy `vvrt run`
## Schema manifest hiện tại
## Crawl job
## Render job
## Server job
## Dependency và validation rules
## Ví dụ manifest
```

The examples must match the current field names from `ScrapePayload`, `RenderPayload`, and `ServerPayload`.

- [ ] **Step 3: Verify example field names match the Pydantic models**

Run: `rg -n "slug|chapters|from_chapter|to_chapter|grouping|skip_illustrations|output_folder|formats|playwright_mode|manifest_path|output_path|fps|render_format|vfx_scale|host|port|opds_password" docs/job-runner.md vvr_scraper/job_models.py`
Expected: All field names used in docs are present in both the guide and the source models.

- [ ] **Step 4: Commit the job runner guide**

```bash
git add docs/job-runner.md
git commit -m "docs: add job runner guide"
```

### Task 6: Write `docs/library-opds.md`

**Files:**
- Create: `docs/library-opds.md`
- Reference: `vvr_scraper/web/routes/library.py:29-275`
- Reference: `vvr_scraper/web/deps.py:15-36`
- Reference: `vvr_scraper/web/__init__.py:66-124`

- [ ] **Step 1: Gather the library and OPDS behavior from code**

Run: `rg -n "library|sync-all|check|scan|batch-import|VVR_AUTO_SYNC|VVR_OPDS_USER|VVR_OPDS_PASS|OPDS" vvr_scraper/web/routes/library.py vvr_scraper/web/deps.py vvr_scraper/web/__init__.py`
Expected: Output shows auto-sync behavior, auth env vars, and library routes.

- [ ] **Step 2: Write `docs/library-opds.md`**

Write a new `docs/library-opds.md` with these sections:

```md
# Library and OPDS Guide

## Library database và metadata
## Scan thư viện hiện có
## Check cập nhật và sync-all
## Auto-sync với `VVR_AUTO_SYNC`
## OPDS auth và feed usage
## Lưu ý vận hành
```

Mention that OPDS auth depends on `VVR_OPDS_USER` and `VVR_OPDS_PASS`, and that missing values disable proper auth.

- [ ] **Step 3: Verify environment variable names and route names**

Run: `rg -n "VVR_AUTO_SYNC|VVR_OPDS_USER|VVR_OPDS_PASS|sync-all|scan|check" docs/library-opds.md vvr_scraper/web/routes/library.py vvr_scraper/web/deps.py`
Expected: All documented env vars and route names exist in source.

- [ ] **Step 4: Commit the library/OPDS guide**

```bash
git add docs/library-opds.md
git commit -m "docs: add library and opds guide"
```

### Task 7: Write `docs/media-pipeline.md`

**Files:**
- Create: `docs/media-pipeline.md`
- Reference: `vvr_scraper/exporter.py:137-829`
- Reference: `vvr_scraper/audio_drama.py:64-511`
- Reference: `vvr_scraper/video_renderer.py:18-262`
- Reference: `vvr_scraper/image_gen.py:1-120`

- [ ] **Step 1: Gather the output formats and external dependencies**

Run: `rg -n "tao_file_epub|tao_file_pdf|tao_file_html|tao_file_md|tao_file_txt|tao_file_mp3|tao_file_audiodrama|tao_file_mp4|ELEVENLABS_API_KEY|VVR_API_KEY|VVR_BASE_URL|VVR_MODEL|OPENAI_API_KEY|FREESOUND_CLIENT_ID|FREESOUND_CLIENT_SECRET|ffmpeg|playwright" vvr_scraper/exporter.py vvr_scraper/audio_drama.py vvr_scraper/video_renderer.py vvr_scraper/image_gen.py`
Expected: Output enumerates real export paths and required env vars/tools.

- [ ] **Step 2: Write `docs/media-pipeline.md`**

Write a new `docs/media-pipeline.md` with these sections:

```md
# Media Pipeline Guide

## Ebook và text outputs
## MP3 output
## Audio Drama output
## Cinematic MP4 output
## Image generation dependencies
## Biến môi trường theo tính năng
```

Make the dependency split explicit:

```md
- `ELEVENLABS_API_KEY` for voice synthesis
- `VVR_API_KEY`, `VVR_BASE_URL`, `VVR_MODEL` for AI parsing / drama logic
- `OPENAI_API_KEY` for image generation paths
- `FREESOUND_CLIENT_ID`, `FREESOUND_CLIENT_SECRET` for Freesound integration
- `ffmpeg` and Playwright browser for cinematic/video workflows
```

- [ ] **Step 3: Verify env var names and output names against code**

Run: `rg -n "ELEVENLABS_API_KEY|VVR_API_KEY|VVR_BASE_URL|VVR_MODEL|OPENAI_API_KEY|FREESOUND_CLIENT_ID|FREESOUND_CLIENT_SECRET|EPUB|PDF|HTML|MD|TXT|MP3|AD-MP3|MP4" docs/media-pipeline.md vvr_scraper/exporter.py vvr_scraper/audio_drama.py vvr_scraper/image_gen.py vvr_scraper/cli.py`
Expected: Every env var and format named in the guide exists in source.

- [ ] **Step 4: Commit the media pipeline guide**

```bash
git add docs/media-pipeline.md
git commit -m "docs: add media pipeline guide"
```

### Task 8: Write `docs/docker-deploy.md`

**Files:**
- Create: `docs/docker-deploy.md`
- Reference: `Dockerfile:1-100`
- Reference: `docker-compose.yml:1-100`
- Reference: `scripts/backup_sqlite.sh:1-35`
- Reference: `prometheus.yml:1-8`

- [ ] **Step 1: Gather the verified Docker facts**

Run: `rg -n "FROM python:3.12-slim|PLAYWRIGHT_BROWSERS_PATH|ENTRYPOINT|CMD|VVR_OPDS_PASS|VVR_API_KEY|VVR_BASE_URL|OPENAI_API_KEY|VVR_AUTO_SYNC|healthcheck|prometheus|grafana|backup_sqlite" Dockerfile docker-compose.yml scripts/backup_sqlite.sh prometheus.yml`
Expected: Output lists the image/runtime assumptions and compose services that are actually present.

- [ ] **Step 2: Re-run Docker verification commands before writing examples**

Run: `docker compose config && docker build -t vvr-scraper-test .`
Expected: Compose renders successfully and Docker image builds successfully.

- [ ] **Step 3: Write `docs/docker-deploy.md`**

Write a new `docs/docker-deploy.md` with these sections:

```md
# Docker Deployment Guide

## Build image
## Chạy container trực tiếp
## Chạy bằng Docker Compose
## Biến môi trường quan trọng
## Volumes và dữ liệu persistent
## Healthcheck, backup, metrics
## Giới hạn và lưu ý vận hành
```

The doc must use examples consistent with the current Docker files, including:

```bash
docker build -t vvr-scraper .
docker run --rm -p 8000:8000 vvr-scraper
docker compose up -d
```

- [ ] **Step 4: Verify all Docker doc examples match the current files**

Run: `rg -n "docker build -t vvr-scraper \.|docker run --rm -p 8000:8000 vvr-scraper|docker compose up -d|VVR_OPDS_PASS|PLAYWRIGHT_BROWSERS_PATH|vvr-web|db-backup|prometheus|grafana" docs/docker-deploy.md Dockerfile docker-compose.yml`
Expected: The Docker guide references only names and commands that exist in the verified setup.

- [ ] **Step 5: Commit the Docker deployment guide**

```bash
git add docs/docker-deploy.md
git commit -m "docs: add docker deployment guide"
```

### Task 9: Final Documentation Sweep

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/cli.md`
- Modify: `docs/web-ui.md`
- Modify: `docs/job-runner.md`
- Modify: `docs/library-opds.md`
- Modify: `docs/media-pipeline.md`
- Modify: `docs/docker-deploy.md`

- [ ] **Step 1: Check that the docs map is internally linked**

Run: `rg -n "docs/cli.md|docs/web-ui.md|docs/job-runner.md|docs/library-opds.md|docs/media-pipeline.md|docs/docker-deploy.md|CONTRIBUTING.md" README.md`
Expected: README links to every canonical companion doc.

- [ ] **Step 2: Check for archived-doc confusion or stale placeholders**

Run: `rg -n "old-doc-bak|TBD|TODO|fill in details|implement later|coming soon|crawl <slug>" README.md CONTRIBUTING.md docs/*.md`
Expected: No stale placeholders. Any `old-doc-bak` mention must clearly say archive/reference only.

- [ ] **Step 3: Check all env var names across canonical docs**

Run: `rg -n "OPENAI_API_KEY|ELEVENLABS_API_KEY|FREESOUND_CLIENT_ID|FREESOUND_CLIENT_SECRET|VVR_API_KEY|VVR_BASE_URL|VVR_MODEL|VVR_NARRATOR_VOICE_ID|VVR_AUTO_SYNC|VVR_OPDS_USER|VVR_OPDS_PASS|VVR_SSR_URL" README.md CONTRIBUTING.md docs/*.md`
Expected: Canonical docs use the exact env var names that exist in code and compose.

- [ ] **Step 4: Commit the final documentation sweep**

```bash
git add README.md CONTRIBUTING.md docs/cli.md docs/web-ui.md docs/job-runner.md docs/library-opds.md docs/media-pipeline.md docs/docker-deploy.md
git commit -m "docs: complete documentation rewrite"
```
