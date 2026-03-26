# Valvrare Team Web Novel Scraper

## Project Overview

**Purpose:** This project is a high-performance, asynchronous command-line and web-based tool designed to scrape and download web novels from [Valvrare Team](https://valvrareteam.net). It allows users to export stories into multiple formats including **EPUB, PDF, HTML, Markdown, TXT, and MP3 (Audiobook)**, with a focus on speed, reliable content extraction, and a modern user experience.

**Main Technologies:**
- **Python (3.9+):** The core programming language.
- **FastAPI & Uvicorn:** Powers the Web Dashboard and REST API.
- **Playwright (`async_playwright`):** Used for navigating the website and extracting content, providing a "Reliable Mode" that can bypass complex DOM structures or dynamic content.
- **httpx:** Used for fast, asynchronous HTTP requests. It powers the "Fast Mode" scraping via a DigitalOcean SSR fallback.
- **WebSockets:** Provides real-time log streaming and progress updates from the scraper to the Web UI.
- **aiosqlite:** Async SQLite driver for the library database (`vvr_library.db`).
- **BeautifulSoup4 & lxml:** Used for parsing HTML and XML (sitemaps).
- **EbookLib & reportlab:** Used for generating EPUB and PDF output files, respectively.
- **VieNeu & numpy:** AI-powered Vietnamese text-to-speech synthesis (TTS) for generating high-quality audiobooks. Lazy-loaded to keep startup fast.
- **Loguru & Rich:** Used for structured logging and professional terminal UI elements.

**Architecture:**
The application follows a modular, asynchronous architecture:
- **`vvr_scraper/cli.py`:** The main orchestrator that handles argument parsing, interactive UI, and high-level workflow. It also manages the launch of the web server.
- **`vvr_scraper/web.py`:** Implements the FastAPI web server, including:
    1. **REST Endpoints:** For searching novels, triggering download tasks, batch import, library management, and update checking.
    2. **WebSocket Manager:** Broadcasts real-time logs and progress updates to connected clients.
    3. **DownloadManager:** Worker-pool based task queue with pause/resume/cancel support.
    4. **Background Tasks:** Orchestrates scraping using `scraper_core.scrape_chapters()` with a progress callback — no duplicated scraping logic.
- **`vvr_scraper/scraper_core.py`:** Implements a **Hybrid Scraping Architecture** (Fast Mode via SSR fallback and Reliable Mode via Playwright). The central `scrape_chapters()` function accepts an `on_chapter_done` callback and `pre_scraped` dict for checkpoint resumption, making it reusable by both CLI and Web.
- **`vvr_scraper/exporter.py`:** Handles asynchronous exports with concurrent image downloading and **lazy-loaded AI audiobook generation** (TTS). EPUB export uses the passed `cover_path` parameter (per-novel unique temp file) to avoid race conditions in multi-download.
- **`vvr_scraper/db.py`:** Async SQLite database manager for the novel library. Tracks downloaded novels, chapter counts, download timestamps, and update status.
- **`vvr_scraper/tao_so_do_cay.py`:** Utility module for extracting chapter lists and volume structures from the novel page using Playwright.
- **`vvr_scraper/static/`:** Contains the Vanilla HTML/CSS/JS frontend for the Web Dashboard.

## Building and Running

### Installation

1. **Install the package:**
   ```bash
   pip install vvr-scraper
   ```

2. **Install browser dependencies:**
   ```bash
   playwright install chromium-headless-shell
   ```

3. **Linux Folder Picker (Optional):**
   For the "Browse" feature on Web UI, install `zenity` or `kdialog`.

### Execution

1. **Web Dashboard (Recommended):**
   ```bash
   vvrt web --port 8000
   ```

2. **Interactive CLI:**
   ```bash
   vvrt
   ```

3. **Advanced CLI Mode:**
   ```bash
   vvrt "slug-1" "slug-2" -f EPUB PDF -g tatca -t 10 --verbose
   ```

### Testing
The project uses `pytest` with `pytest-asyncio`:
```bash
pytest
```

## Key Design Decisions

- **Unified Scraping Logic:** Both CLI and Web use `scraper_core.scrape_chapters()`. Web passes an `on_chapter_done` callback for WebSocket progress broadcasting and checkpoint saving. No duplicated scraping code.
- **Per-Novel Cover Files:** Cover images are saved to unique temp files (`tempfile.mkstemp`) instead of a shared `cover.jpg`, preventing cover mix-ups during concurrent multi-novel downloads.
- **Failure Threshold:** If >30% of chapters fail to download, the task aborts without exporting, preventing empty or incomplete output files.
- **Chapter Tree Always Fetched:** The Web server always fetches the full chapter tree (even when `selected_urls` is provided) to ensure proper volume/chapter titles in EPUB TOC, matching CLI output quality.
- **Checkpoint Serialization:** `ContentItem` dataclass objects are converted to plain dicts via `dataclasses.asdict()` before JSON checkpoint serialization. Corrupt checkpoints are auto-deleted and the task starts fresh.

## Development Conventions

- **Asynchronous First:** All network I/O, file exports, and web server operations must be `async`.
- **Hybrid Scraping:** Always prefer the SSR fallback (Fast Mode) but maintain Playwright as a reliable fallback.
- **Single Source of Truth:** Scraping logic lives in `scraper_core.py`. Web and CLI consume it via callbacks/parameters — never duplicate it.
- **WebSocket Communication:** Real-time updates should follow the JSON format: `{"type": "log|progress|status|info|complete|error", ...}`.
- **Clean UI:** Maintain the "Modern Clean" aesthetic for the web frontend using Vanilla CSS variables.
- **Structured Logging:** Use `loguru` everywhere (not `print()`). The `websocket_sink` in `web.py` ensures logs are broadcasted to the dashboard.
- **Vietnamese Support:** Ensure all exports and UI elements correctly handle Vietnamese characters.
- **Resource Cleanup:** Temp files (covers, chapter JSONs) must be cleaned up after use. Use `try/finally` or context managers for Playwright browsers.
