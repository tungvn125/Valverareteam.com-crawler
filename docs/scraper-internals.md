# Scraper Internals Documentation

This document provides detailed information about the core scraping logic, data models, source adapters, and utility functions in the VVR-Scraper project.

## Overview

The VVR-Scraper is a Python-based web novel scraper designed to extract content from multiple Vietnamese web novel platforms. It uses a hybrid approach combining HTTPX for fast scraping and Playwright for JavaScript-rendered content, with a pluggable source adapter system for supporting multiple websites.

## Data Models

All data models are implemented as Python dataclasses in `vvr_scraper/models.py`.

### StoryInfo

Contains metadata about a web novel story.

```python
@dataclass
class StoryInfo:
    title: str                    # Story title
    author: str                   # Author name(s)
    description: str              # Story synopsis
    slug: str | None = None       # URL slug identifier
    genres: list[str] = field(default_factory=list)  # Genre tags
    cover_path: str | None = None # Local path to downloaded cover
    cover_url: str | None = None  # URL of cover image
    total_chapters: str = "Unknown"  # Total chapter count
    word_count: str = "Unknown"   # Total word count
    views: str = "-"              # View count
```

### ContentItem

Represents a single piece of chapter content (text or image).

```python
@dataclass
class ContentItem:
    type: Literal["text", "image"]  # Content type
    data: str                       # Text content or image URL
```

### Chapter

Represents a single chapter with its content.

```python
@dataclass
class Chapter:
    title: str                # Chapter title
    content: list[ContentItem]  # List of content items
    url: str | None = None    # Source URL
```

### Volume

Groups chapters into volumes (story arcs).

```python
@dataclass
class Volume:
    title: str           # Volume title
    chapters: list[Chapter]  # Chapters in this volume
```

### CharacterProfile

Detailed profile for text-to-speech character voices.

```python
@dataclass
class CharacterProfile:
    name: str                    # Canonical character name
    story_id: str                # Associated story ID
    aliases: list[str] = field(default_factory=list)  # Alternative names
    gender: str = "unknown"      # Character gender
    voice_id: str | None = None  # TTS voice identifier
    ref_audio_path: str | None = None  # Reference audio file
    ref_text: str | None = None  # Reference text sample
    personality: str | None = None     # Personality description
    speaking_style: str | None = None  # Speaking style notes
    emotion_range: float = 0.5   # Emotional expressiveness (0-1)
    color: str | None = None     # UI color for character
```

## Enums

Type-safe enumerations defined in `vvr_scraper/enums.py`.

### JobStatus

Status values for background job tracking.

| Value       | Description                                   |
|-------------|-----------------------------------------------|
| `PENDING`   | Job is queued but not yet started            |
| `WAITING`   | Job is waiting for dependencies              |
| `RUNNING`   | Job is currently executing                   |
| `SUCCESS`   | Job completed successfully                   |
| `FAILED`    | Job failed with an error                     |
| `CANCELLED` | Job was cancelled by user or system          |

### NovelStatus

Status values for novel tracking.

| Value         | Description                                 |
|---------------|---------------------------------------------|
| `PENDING`     | Novel is pending processing                 |
| `SYNCED`      | Novel is fully synchronized                 |
| `UNAVAILABLE` | Novel is temporarily unavailable            |
| `ARCHIVED`    | Novel has been archived                     |

### Allowed Columns

The module also defines whitelisted column names for safe SQL construction:

- `ALLOWED_NOVEL_COLUMNS`: Safe columns for novel table operations
- `ALLOWED_JOB_COLUMNS`: Safe columns for job table operations

## Scraper Core

Core scraping logic in `vvr_scraper/scraper_core.py`.

### Main Functions

#### `lay_thong_tin_truyen(client, ten_truyen, verbose)`

Scrapes story metadata from the main story page.

**Parameters:**
- `client`: HTTPX async client instance
- `ten_truyen`: Story slug or full URL
- `verbose`: Enable debug logging

**Flow:**
1. Detects if input is a URL or slug
2. Routes to custom source adapter for non-VVR domains
3. For VVR domains, uses SSR (Server-Side Rendering) URL
4. Extracts title, author, description, genres, stats
5. Downloads cover image to temp file

**Stats Extraction Priority:**
1. Modern `.rd-stat-item` elements
2. Legacy `.rd-stats-item` elements
3. `.rd-info-row` fallback
4. `.rd-chapter-count-value` final fallback

#### `lay_chuong_httpx(client, url, verbose, token, browser)`

Fast mode chapter scraping using HTTPX.

**Parameters:**
- `client`: HTTPX async client
- `url`: Chapter URL
- `verbose`: Debug logging flag
- `token`: Optional JWT authentication token
- `browser`: Optional Playwright browser (for custom sources)

**Returns:** List of `ContentItem` objects or `None` on failure

**Content Extraction:**
- Selects `.chapter-content` container
- Extracts `<p>` tags as text items
- Extracts `<img>` tags as image items

#### `lay_chuong_voi_hinh_anh(browser, url, session_state, verbose)`

Reliable mode chapter scraping using Playwright.

**Parameters:**
- `browser`: Playwright browser instance
- `url`: Chapter URL
- `session_state`: Storage state with cookies/auth
- `verbose`: Debug logging flag

**Features:**
- Waits for `domcontentloaded` event
- Uses CSS selector `.chapter-content p, .chapter-content img`
- Retries up to 2 times on failure
- Handles both text and image extraction

#### `scrape_chapters(browser, urls, concurrent_tasks, ...)`

Main entry point for batch chapter scraping with hybrid fallback logic.

**Hybrid Approach:**
1. **Fast Mode First**: Attempts HTTPX scraping for speed
2. **Reliable Mode Fallback**: Uses Playwright if HTTPX fails
3. **Custom Source Handling**: Reduces concurrency for rate-limited sources

**Parameters:**
- `browser`: Playwright browser instance
- `urls`: List of chapter URLs to scrape
- `concurrent_tasks`: Max concurrent tasks (default: 5)
- `skipped_urls`: List to collect failed URLs
- `session_state`: Playwright storage state for auth
- `verbose`: Debug logging
- `token`: JWT token for API requests
- `pre_scraped`: Previously scraped content (checkpoint support)
- `on_chapter_done`: Optional async callback

**Concurrency Adjustment:**
- Detects custom source URLs (non-VVR domains)
- Automatically reduces concurrency by half for rate-limited sources

## Source Adapter System

Pluggable architecture for supporting multiple novel websites, defined in `vvr_scraper/sources/`.

### Base Interface

#### `BaseSource` (Abstract Class)

All source adapters must inherit from `BaseSource` and implement:

```python
class BaseSource(ABC):
    base_urls: list[str] = []  # Domain patterns to match

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        """Search for novels by query."""
        pass

    @abstractmethod
    async def get_info(self, url: str) -> StoryInfo:
        """Get novel metadata."""
        pass

    @abstractmethod
    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        """Get structured chapter/volume list."""
        pass

    @abstractmethod
    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        """Get chapter content."""
        pass

    @abstractmethod
    async def aclose(self) -> None:
        """Cleanup resources."""
        pass

    def matches(self, url: str) -> bool:
        """Check if this source handles the URL."""
        return any(base in url for base in self.base_urls)
```

### Support Classes

#### `SearchResult`
```python
@dataclass
class SearchResult:
    title: str
    url: str
    author: str | None = None
    cover: str | None = None
```

#### `ChapterTreeItem`
```python
@dataclass
class ChapterTreeItem:
    title: str
    url: str
    locked: bool = False  # Paywalled/premium chapters
```

#### `VolumeTreeItem`
```python
@dataclass
class VolumeTreeItem:
    volume: str
    chapters: list[ChapterTreeItem] = field(default_factory=list)
```

### Factory Function

#### `get_source(url, client, browser)`

Returns the appropriate source instance for a URL.

**Supported Sources:**
- **TruyenFull** (`truyenfull.vision`): HTTPX-only, no JavaScript required
- **LnHako** (`ln.hako.vn`): Requires Playwright browser for content extraction

**Caching:**
- Source instances are cached when no client/browser is injected
- Injected dependencies bypass cache for explicit lifecycle control

### LnHako Adapter

Implementation in `vvr_scraper/sources/lnhako.py`.

**Characteristics:**
- **Domain**: `ln.hako.vn`
- **Requires Browser**: Yes (Playwright needed for chapter content)
- **Client Ownership**: Tracks if it owns the HTTPX client for cleanup

**Implementation Details:**

```python
class LnHakoSource(BaseSource):
    base_urls = ["ln.hako.vn"]

    def __init__(self, client=None, browser=None):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0)
        self.browser = browser  # Required for get_content()
```

**Search:** Uses `/tim-kiem?keywords={query}` endpoint, parses `.thumb_attr.series-title` elements, filters out `/ai-dich/` results.

**Info Extraction:**
- Title: `.series-name` span or h1
- Author: `/tac-gia/` link
- Description: `.summary-content` div
- Cover: `og:image` meta or CSS background-url
- Stats: `.statistic-item` elements
- Chapters: Counted from chapter link pattern `/truyen/\d+-[^/]+/c\d+-`

**Chapter List:**
- Parses `<section class="volume-list">` elements
- Each volume has header with `.sect-title`
- Chapters in `<ul class="list-chapters">`
- Falls back to flat chapter list if no volumes found

**Content Extraction:**
- Requires browser instance
- Navigates to chapter URL with `networkidle` wait
- Waits for `#chapter-content` selector
- Extracts paragraphs and images
- Retries up to 3 times with exponential backoff

### TruyenFull Adapter

Implementation in `vvr_scraper/sources/truyenfull.py`.

**Characteristics:**
- **Domain**: `truyenfull.vision`
- **Requires Browser**: No (pure HTTPX)
- **Rate Limiting**: Implements retry with exponential backoff

**Implementation Details:**

```python
class TruyenFullSource(BaseSource):
    base_urls = ["truyenfull.vision"]

    def __init__(self, client=None):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(...)
```

**Retry Logic:**
- Max 3 retries
- Exponential backoff: 2s, 4s, 8s
- Handles HTTP 429 (Too Many Requests) and 503 (Service Unavailable)

**Search:** Uses AJAX endpoint `/ajax.php?type=quick_search&str={query}`, parses `.list-group-item` elements.

**Info Extraction:**
- Title: `h3.title`
- Author: `a[itemprop='author']`
- Description: `div.desc-text`
- Cover: `div.book-thumb img`
- Genres: `a[itemprop='genre']`
- Stats: `div.info div` (chapter count)

**Chapter List:**
1. Extracts `truyen-id` and `total-page` from HTML
2. Iterates through AJAX pages
3. Endpoint: `/ajax.php?type=list_chapter&tid={id}&page={n}`
4. Returns flat list as single volume

**Content Extraction:**
- Target: `div#chapter-c`
- Removes ad elements (class containing "ads")
- Uses `_extract_text_segments()` to split `<br><br>` markup into paragraphs
- Fallback to raw text if structured parsing fails

## Session Manager

Browser session management for authentication and Cloudflare bypass in `vvr_scraper/session_manager.py`.

### Functions

#### `save_session(state, file_path)`

Saves browser storage state to JSON file with 0o600 permissions.

**Parameters:**
- `state`: Playwright storage state dict (cookies + localStorage)
- `file_path`: Destination file path

#### `load_session(file_path)`

Loads browser storage state from JSON file.

**Returns:** State dict or `None` if file doesn't exist or is invalid.

#### `capture_session(url)`

Interactive session capture for Cloudflare bypass.

**Flow:**
1. Launches non-headless Chromium browser
2. Navigates to target URL
3. Displays instructions in terminal:
   ```
   VUI LÒNG ĐĂNG NHẬP HOẶC GIẢI CLOUDFLARE TRONG TRÌNH DUYỆT.
   Sau khi hoàn tất và thấy nội dung truyện ĐÃ MỞ KHÓA, hãy quay lại đây.
   Nhấn phím ENTER trong terminal này để tiếp tục...
   ```
4. Waits for user to press Enter
5. Captures storage state (cookies + localStorage)
6. Reports cookie count
7. Returns state dict

**Use Case:** Required for accessing premium/locked chapters on valvrareteam.net when Cloudflare protection is active.

## Utility Functions

Common utilities in `vvr_scraper/utils.py`.

### Logging Configuration

#### `configure_logger(verbose)`

Configures Loguru logger with appropriate formatting.

**Format:**
```
HH:mm:ss | LEVEL    | message
```

**Modes:**
- Normal: INFO level and above
- Verbose: DEBUG level and above
- JSON mode: Set `VVR_LOG_JSON=1` for structured logging

### HTTP Headers

#### `HEADERS`

Default HTTP headers mimicking Chrome browser:
- User-Agent: Chrome 146 on Linux
- Accept: HTML, XML, images, avif, webp
- Accept-Language: en-US, en, vi
- Referer: valvrareteam.net
- DNT: 1 (Do Not Track)
- Sec-* headers for modern browser fingerprint

### Playwright Configuration

#### `resolve_playwright_headless(cli_mode)`

Resolves headless mode with precedence:
1. CLI flag (`--head` or `--headless`)
2. Environment variable `VVR_PLAYWRIGHT_MODE`
3. Default: headless (True)

### Filename Sanitization

#### `sanitize_filename(name)`

Sanitizes strings for safe filesystem usage.

**Transformations:**
1. Removes illegal characters: `\/*?:"<>|`
2. Strips leading/trailing spaces and dots
3. Collapses multiple spaces
4. Prefixes underscore to Windows reserved names:
   - CON, PRN, AUX, NUL
   - COM1-9, LPT1-9

**Example:**
```python
sanitize_filename("My: Story?")  # "My Story"
sanitize_filename("CON")         # "_CON"
```

### Directory Creation

#### `create_folders_from_tree(tree_file, base_folder)`

Creates directory structure from a tree map file.

**Input Format:** One folder name per line
**Behavior:** Sanitizes each name before creating

### Vietnamese URL Normalization

#### `normalize_vietnamese_url(text)`

Normalizes Vietnamese text for URL matching.

**Steps:**
1. Lowercase conversion
2. Vietnamese diacritic removal (à→a, đ→d, etc.)
3. Remove all non-alphanumeric except spaces
4. Replace spaces with hyphens
5. Collapse multiple hyphens

**Example:**
```python
normalize_vietnamese_url("Tiếng Việt: Bài 1!")
# "tieng-viet-bai-1"
```

### Configuration Paths

#### `get_config_dir()`

Returns `~/.config/vvr-scraper/`, creating if needed.

#### `get_config_path(filename)`

Returns path for config file with auto-migration from CWD.

**Migration:** If file exists in current working directory but not in config dir, automatically copies it.

### Token Extraction

#### `get_token_from_state(state)`

Extracts JWT token from Playwright storage state.

**Searches:**
- localStorage keys: `accessToken`, `token`, `jwt`
- Nested in `auth-storage` JSON (state.token, state.accessToken)

**Returns:** Token string or `None`

### URL Resolution

#### `resolve_story_url(name_raw, cookies)`

Resolves story URLs from slugs or partial names.

**Supports:**
- Full URLs (returned as-is)
- VVR slugs with path prefixes (`truyen/`, `sang-tac/`, `xuat-ban/`)
- Custom source slugs (TruyenFull, LnHako)

**Resolution Order:**
1. If starts with `http`: return as-is
2. Strip known path prefixes
3. Normalize Vietnamese characters
4. Search VVR sitemap.xml
5. Probe custom sources with candidate URLs

**Returns:** Full URL or `None` if not found

## Chapter Tree Extraction

Chapter/volume structure extraction in `vvr_scraper/tao_so_do_cay.py`.

### Functions

#### `get_chapter_tree(url, output_file, cookies)`

Extracts chapter tree as human-readable text.

**Output Format:**
```
■ Volume Title 1
  - Chapter 1 Title
  - Chapter 2 Title

■ Volume Title 2
  - Chapter 3 Title
```

**Implementation:**
- Uses HTTPX to fetch story page
- Parses `.module-container` elements
- Extracts `.module-title` for volume names
- Extracts `.chapter-title-link` for chapter names

#### `get_chapter_tree_folder(url, output_file, cookies)`

Extracts only volume names for folder creation.

**Output Format:** One volume name per line (sanitized for filesystem)

#### `get_chapter_tree_list(url, output_file, session_state, browser)`

Extracts structured chapter tree as JSON.

**Priority:**
1. Custom source adapters (TruyenFull, LnHako)
2. VVR Playwright-based extraction

**JSON Output Format:**
```json
[
  {
    "volume": "Volume Title",
    "chapters": [
      {"title": "Chapter 1", "url": "/chuong/1", "locked": false},
      {"title": "Chapter 2", "url": "/chuong/2", "locked": true}
    ]
  }
]
```

**VVR Extraction Details:**
- Uses Playwright to render dynamic content
- Detects locked chapters via CSS classes: `locked-chapter`, `chapter-mode-protected`
- Handles chapters without links (locked premium content)

#### `get_chapters_by_volume_index(file_path, index)`

Returns chapters for a specific volume from saved JSON.

**Parameters:**
- `file_path`: Path to chapter_list.json
- `index`: 0-based volume index

**Returns:** List of chapter dicts or empty list on error

#### `get_chapter_range_urls(slug_or_url, start_index, end_index, session_state, browser)`

Extracts a slice of chapter URLs for batch operations.

**Parameters:**
- `slug_or_url`: Story slug or full URL
- `start_index`: 0-based start (inclusive)
- `end_index`: 0-based end (exclusive)
- `session_state`: Optional auth state
- `browser`: Optional browser instance

**Returns:** List of chapter URLs

**Flow:**
1. Generates temporary JSON file with UUID
2. Calls `get_chapter_tree_list()`
3. Flattens all chapters across volumes
4. Slices the list
5. Returns URLs only
6. Cleans up temp file

### Helper Functions

#### `_fetch_chapter_page(browser, url, session_state)`

Internal function to fetch story page HTML via Playwright.

**Features:**
- Applies user-agent from HEADERS
- Uses session state for authentication
- Waits for `.module-chapter-item` selector
- 2-second delay for dynamic content
