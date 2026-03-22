# Valvrare Team Web Novel Scraper

## Project Overview

**Purpose:** This project is a Python-based command-line tool (CLI) designed to scrape and download web novels from [Valvrare Team](https://valvrareteam.net). It allows users to save stories in various formats including PDF, EPUB, HTML, Markdown, and TXT. It is distributed as a standard Python package named `vvr-scraper`.

**Main Technologies:**
- **Python (3.8+)**
- **Playwright (`async_playwright`):** Used for navigating pages and extracting content, ensuring compatibility with dynamic or heavily structured DOM elements.
- **BeautifulSoup4:** Used for parsing simpler HTML structures, like the site's sitemap.
- **httpx:** Used for efficient, asynchronous HTTP requests.
- **prompt-toolkit:** Provides the live search feature with real-time suggestions as the user types.
- **EbookLib & reportlab:** Used for generating EPUB and PDF output files, respectively.
- **simple-term-menu:** Provides an interactive terminal menu for users running the script without command-line arguments.
- **Loguru:** Structured logging for better debugging and cleaner output control.
- **Rich:** Professional UI elements including tables, spinners, and progress bars.

**Architecture:**
The application follows a standard Python package structure (PEP 517/518) with logic encapsulated in the `vvr_scraper` package:
- `vvr_scraper/`: Core package directory.
    - `cli.py`: Contains `ValvrareScraperCLI` (orchestrator) and `InteractiveUI` classes. Handles arguments, UI logic, and workflow coordination.
    - `scraper_core.py`: Core functions for extracting metadata (with automatic title cleaning), text, and images.
    - `exporter.py`: Asynchronous export logic. Handles bulk image downloading and file compilation.
    - `models.py` & `utils.py`: Shared data structures and utility functions (logging configuration, normalization, session management).
- `scraper.py`: A convenience wrapper for local execution.
- `pyproject.toml`: Modern packaging configuration defining dependencies and the `vvrt` entry point.

## Technical Implementation Details

### Hybrid Scraping Architecture
The scraper uses a multi-layered approach to balance speed and reliability:
1.  **Fast Mode (`httpx`):** Attempts to fetch chapter content directly from the DigitalOcean SSR fallback (`val-ssr-2kzit.ondigitalocean.app`). This bypasses the main domain's heavy Cloudflare protection.
2.  **Reliable Mode (`Playwright`):** Fallback to a full headless browser session on the main domain if Fast Mode fails.

### Optimized Asynchronous Export
The export process is fully asynchronous to maximize I/O performance:
- **Bulk Image Downloading:** Instead of sequential downloads, the `exporter` identifies all image URLs in a document and fetches them concurrently using `asyncio.gather` and an `asyncio.Semaphore` (default limit: 10).
- **In-Memory Assembly:** Images are downloaded into memory and injected directly into EPUB/PDF structures, significantly reducing disk I/O overhead.

### Live Search & Slug Resolution
- **Interactive Search:** Powered by `prompt-toolkit` and `ThreadedCompleter`, providing real-time suggestions from the Valvrare Team API.
- **Slug Discovery:** Resolves story URLs from the sitemap. The logic preserves the full relative path (e.g., `/truyen/novel-slug`) to ensure compatibility with all website sections and avoid 404 errors.

### Metadata & Title Cleaning
- **Automatic Sanitization:** Automatically removes status suffixes from novel titles (e.g., `+Đang tiến hành`, `+Hoàn thành`, `+Tạm ngưng`) for cleaner file naming.
- **Output Structure:** Uses the novel's slug for the directory name and the full (cleaned) title for the filename.

### Authentication & Authorization
- **Session Capture:** Uses a non-headless browser for manual Cloudflare bypass or login.
- **JWT Extraction:** Extracts Bearer tokens from `localStorage` within the `storage_state`.
- **Authenticated SSR:** Injects JWT tokens into Fast Mode requests for access to locked/protected content.

## Building and Running

### Installation

**1. From PyPI (Recommended):**
```bash
pip install vvr-scraper
playwright install chromium-headless-shell
```

**2. Development Install:**
```bash
git clone https://github.com/your-repo/valvrareteam-net-crawler.git
cd valvrareteam-net-crawler
pip install -e .
playwright install chromium-headless-shell
```

### Execution

**1. Global Command:**
```bash
vvrt
```

**2. Interactive Mode (Local Script):**
```bash
python scraper.py
```

**3. CLI Mode:**
```bash
# Example: Download a specific novel with verbose logging and 10 concurrent tasks
vvrt "novel-slug" -f EPUB PDF -g tatca -t 10 --verbose
```

### Testing
```bash
# Runs the full test suite (compatible with package structure)
pytest
```

## Development Conventions

- **Standard Package Structure:** Always use relative imports within the `vvr_scraper` package (e.g., `from .models import ...`).
- **Strict Asynchronous Workflow:** All network and I/O bound operations must be `async`.
- **Structured Logging:** Use `loguru`'s `logger` instead of `print`.
- **UI Consistency:** Use `rich` for terminal feedback. Display summary tables in verbose mode.
- **Type Safety:** Maintain comprehensive Type Hinting for all new functions.
- **Language:** UI and core documentation are in Vietnamese; internal code/logic uses English naming conventions (PEP 8).
