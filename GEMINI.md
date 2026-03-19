# Valvrare Team Web Novel Scraper

## Project Overview

**Purpose:** This project is a Python-based command-line tool (CLI) designed to scrape and download web novels from [Valvrare Team](https://valvrareteam.net). It allows users to save stories in various formats including PDF, EPUB, HTML, Markdown, and TXT.

**Main Technologies:**
- **Python (3.8+)**
- **Playwright (`async_playwright`):** Used for navigating pages and extracting content, ensuring compatibility with dynamic or heavily structured DOM elements.
- **BeautifulSoup4:** Used for parsing simpler HTML structures, like the site's sitemap.
- **httpx:** Used for efficient, asynchronous HTTP requests.
- **prompt-toolkit:** Provides the live search feature with real-time suggestions as the user types.
- **EbookLib & reportlab:** Used for generating EPUB and PDF output files, respectively.
- **simple-term-menu:** Provides an interactive terminal menu for users running the script without command-line arguments.

**Architecture:**
The application is structured logically with distinct responsibilities:
- `scraper.py`: The main entry point script.
- `cli.py`: Handles command-line arguments, live novel search, and orchestrates the high-level workflow.
- `scraper_core.py`: Contains functions for extracting metadata (including genres), text, and images.
- `exporter.py`: Handles compiling scraped data into various formats with full metadata support.
- `models.py` & `utils.py`: Provide shared data structures (including the updated `StoryInfo` with genres) and utility functions (like the improved Unicode-aware sanitization).

## Technical Implementation Details

### Hybrid Scraping Architecture
The scraper uses a multi-layered approach to balance speed and reliability:
1.  **Fast Mode (`httpx`):** Attempts to fetch chapter content directly from the DigitalOcean SSR fallback (`val-ssr-2kzit.ondigitalocean.app`). This bypasses the main domain's heavy Cloudflare protection and browser rendering overhead.
2.  **Reliable Mode (`Playwright`):** If Fast Mode fails or returns empty content, the scraper falls back to a full headless browser session on the main domain. This ensures content is captured even if SSR is unavailable or blocked.

### Live Search & Slug Resolution
- **Interactive Search:** Powered by `prompt-toolkit` and `ThreadedCompleter`, providing real-time suggestions from the Valvrare Team API as the user types (triggering after 3 characters).
- **Slug Discovery:** The search automatically resolves the required URL slug using the logic: `normalize_vietnamese_url(title) + "-" + mongodb_id[-8:]`. This removes the need for users to manually find story slugs.

### Authentication & Authorization
- **Session Capture:** Uses a non-headless browser to allow users to solve Cloudflare challenges or log in manually.
- **JWT Extraction:** Automatically parses the saved `storage_state` to extract Bearer tokens from `localStorage` (specifically looking for `accessToken` or keys within `auth-storage`).
- **Authenticated SSR:** These tokens are automatically injected into the `Authorization` header for `httpx` requests to the SSR fallback, allowing authorized access to protected/locked chapters in Fast Mode.

### Advanced Normalization
- The `utils.normalize_vietnamese_url` function implements an aggressive sanitization logic that:
    1.  Maps Vietnamese diacritics to base ASCII.
    2.  Strips all non-alphanumeric special characters (tildes, commas, colons, etc.).
    3.  Collapses spaces and preserves readability while matching the website's internal slug generation.

## Building and Running

### Installation

1.  **Prerequisites:** Ensure Python 3.8+ is installed.
2.  **Automated Setup (Recommended):**
    *   **Linux/macOS:** Run `./setup.sh`. This script creates a virtual environment, installs dependencies, installs Playwright browsers, and sets up a `vvrt` alias in your shell.
    *   **Windows:** Run `install.bat`.
3.  **Manual Setup:**
    ```bash
    pip install -r requirements.txt
    playwright install chromium-headless-shell
    ```

### Execution

The application can be run in two modes:

**1. Interactive Mode:**
Run the script without arguments to be guided by interactive menus.
```bash
python scraper.py
# OR, if setup.sh was used:
vvrt
```

**2. CLI Mode:**
Provide command-line arguments for automated or scriptable usage.
```bash
# Example: Download a specific novel, save as EPUB and PDF, merge by volume, using 10 concurrent tasks
python scraper.py "ten-truyen" -f EPUB PDF -g volume -t 10
```
Use `python scraper.py -h` or `vvrt -h` for a full list of available options.

### Testing
To run tests (if the development dependencies are installed):
```bash
pytest
```

## Development Conventions

- **Asynchronous Programming:** The project heavily utilizes `asyncio` to achieve high performance through concurrent scraping tasks. When adding new network or I/O bound features, ensure they are asynchronous.
- **Type Hinting:** The codebase uses Python type hints (e.g., `from typing import List, Dict, Optional`). New code should maintain this practice for clarity and maintainability.
- **Separation of Concerns:** Logic is cleanly separated between CLI interaction, scraping, and exporting. Modifications should respect these boundaries (e.g., don't put HTML parsing logic in `exporter.py`).
- **Error Handling:** The scraper is designed to be resilient. It attempts retries for failing pages and logs skipped URLs to a file (`cac_chuong_da_bo_qua.txt`) rather than crashing the entire process. Maintain this robust approach when modifying scraping logic.
- **Language:** The user interface and comments/docstrings are predominantly in Vietnamese.
