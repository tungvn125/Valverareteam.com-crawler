# Valvrare Team Web Novel Scraper

## Project Overview

**Purpose:** This project is a high-performance, asynchronous command-line and web-based tool designed to scrape and download web novels from [Valvrare Team](https://valvrareteam.net). It allows users to export stories into multiple formats including **EPUB, PDF, HTML, Markdown, TXT, and MP3 (Audiobook)**, with a focus on speed, reliable content extraction, and a modern user experience.

**Main Technologies:**
- **Python (3.8+):** The core programming language.
- **FastAPI & Uvicorn:** Powers the Web Dashboard and REST API.
- **Playwright (`async_playwright`):** Used for navigating the website and extracting content, providing a "Reliable Mode" that can bypass complex DOM structures or dynamic content.
- **httpx:** Used for fast, asynchronous HTTP requests. It powers the "Fast Mode" scraping via a DigitalOcean SSR fallback.
- **WebSockets:** Provides real-time log streaming and progress updates from the scraper to the Web UI.
- **BeautifulSoup4 & lxml:** Used for parsing HTML and XML (sitemaps).
- **EbookLib & reportlab:** Used for generating EPUB and PDF output files, respectively.
- **VieNeu & numpy:** AI-powered Vietnamese text-to-speech synthesis (TTS) for generating high-quality audiobooks.
- **Loguru & Rich:** Used for structured logging and professional terminal UI elements.

**Architecture:**
The application follows a modular, asynchronous architecture:
- **`vvr_scraper/cli.py`:** The main orchestrator that handles argument parsing, interactive UI, and high-level workflow. It also manages the launch of the web server.
- **`vvr_scraper/web.py`:** Implements the FastAPI web server, including:
    1. **REST Endpoints:** For searching novels and triggering download tasks.
    2. **WebSocket Manager:** Broadcasts real-time logs and progress updates to connected clients.
    3. **Background Tasks:** Orchestrates scraping logic without blocking the web server.
- **`vvr_scraper/scraper_core.py`:** Implements a **Hybrid Scraping Architecture** (Fast Mode via SSR fallback and Reliable Mode via Playwright).
- **`vvr_scraper/exporter.py`:** Handles asynchronous exports with concurrent image downloading and **lazy-loaded AI audiobook generation** (TTS).
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

## Development Conventions

- **Asynchronous First:** All network I/O, file exports, and web server operations must be `async`.
- **Hybrid Scraping:** Always prefer the SSR fallback (Fast Mode) but maintain Playwright as a reliable fallback.
- **WebSocket Communication:** Real-time updates should follow the JSON format: `{"type": "log|progress|status", ...}`.
- **Clean UI:** Maintain the "Modern Clean" aesthetic for the web frontend using Vanilla CSS variables.
- **Structured Logging:** Use the `websocket_sink` in `web.py` to ensure logs are broadcasted to the dashboard.
- **Vietnamese Support:** Ensure all exports and UI elements correctly handle Vietnamese characters.
