# Design Spec: Open Plugin System cho VVR-Scraper

**Date:** 2026-04-22  
**Status:** Draft — awaiting user approval  
**Scope:** `vvr_scraper/sources/`, `vvr_scraper/scraper_core.py`, `vvr_scraper/utils.py`

---

## 1. Mục tiêu

Biến source system từ hardcoded registry thành open plugin framework: drop một file `.py` vào `~/.config/vvr-scraper/plugins/` là có source mới, không cần chạm core code.

**Không thay đổi:** Logic crawl của từng source (Playwright/HTTPX, HTML parsing, endpoint URLs) giữ nguyên hoàn toàn.

---

## 2. Hiện trạng & Vấn đề

### 2.1 Hardcoded registry

`get_source()` trong `sources/__init__.py` hardcode danh sách source bằng if/elif:

```python
sources = [
    ("truyenfull.vision", TruyenFullSource, {"client": client}),
    ("ln.hako.vn",        LnHakoSource,     {"client": client, "browser": browser}),
]
```

Thêm source mới = bắt buộc sửa core code.

### 2.2 Hidden coupling cần fix

| # | Vấn đề | Vị trí | Hậu quả |
|---|--------|--------|---------|
| 1 | `search()` abstract nhưng không có call site production nào | `sources/__init__.py` | Plugin writer bị force implement method vô nghĩa |
| 2 | Cover image chỉ tải trong VVR branch | `scraper_core.py:137–163` | Custom source EPUB output không có cover (silent bug) |
| 3 | Hybrid fallback trigger kể cả khi custom source fail | `scraper_core.py:351–353` | Tốn 60s × MAX_RETRIES timeout vô ích với VVR Playwright selector |
| 4 | `slug_candidates` hardcode TruyenFull + LnHako | `utils.py:325–328` | Plugin mới không được probe khi user dùng slug |
| 5 | kwargs injection hardcode per-source | `sources/__init__.py:79–82` | Plugin mới không được inject `client`/`browser` đúng |

---

## 3. Design

### 3.1 Thay đổi `BaseSource` contract

```python
class BaseSource(ABC):
    # --- Class-level declarations ---
    base_urls: ClassVar[list[str]] = []
    priority: ClassVar[int] = 100        # thấp hơn = ưu tiên cao hơn khi conflict
    name: ClassVar[str] = ""             # human-readable id, e.g. "ln-hako"
    requires_browser: ClassVar[bool] = False

    # --- Abstract: bắt buộc implement ---
    @abstractmethod
    async def get_info(self, url: str) -> StoryInfo: ...

    @abstractmethod
    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]: ...

    @abstractmethod
    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        # PHẢI raise exception nếu thất bại (không return [] hoặc None)
        # để fix hybrid fallback trap
        ...

    @abstractmethod
    async def aclose(self) -> None: ...

    # --- Optional hooks: có default implementation ---
    async def search(self, query: str) -> list[SearchResult]:
        # Fix #1: downgrade từ abstract → optional, default return []
        return []

    async def fetch_cover(self, cover_url: str) -> bytes | None:
        # Fix #2: default GET cover_url bằng self.client nếu có
        # scraper_core sẽ gọi hook này sau get_info() cho mọi source
        if not cover_url or not getattr(self, "client", None):
            return None
        try:
            r = await self.client.get(cover_url, timeout=30.0)
            r.raise_for_status()
            return r.content
        except Exception:
            return None

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        # Fix #4: mỗi source tự biết cách build candidate URL từ slug
        # default: None (không hỗ trợ slug resolution)
        return None

    def matches(self, url: str) -> bool:
        return any(base in url for base in self.base_urls)
```

**Quy ước `get_content()`:**
- Phải raise exception (không return `[]` hoặc `None`) khi thất bại
- Lý do: `scraper_core.scrape_chapters()` dùng `content is None/empty` làm trigger cho Playwright VVR fallback — nếu custom source trả `[]`, fallback VVR chạy và fail timeout vô ích

**Quy ước `get_info()`:**
- Khi không tìm thấy truyện: trả `StoryInfo(title="Unknown", ...)`
- `resolve_story_url()` dùng `title == "Unknown"` làm sentinel

**Quy ước `get_chapter_list()`:**
- Tất cả URL trong `ChapterTreeItem.url` phải là **absolute URL**
- `job_runner._chapter_full_url()` chỉ prepend VVR base URL cho relative paths

**Quy ước `_owns_client` pattern (bắt buộc cho mọi source có HTTP client):**
```python
def __init__(self, client=None, ...):
    self._owns_client = client is None
    self.client = client or httpx.AsyncClient(...)

async def aclose(self):
    if self._owns_client:
        await self.client.aclose()
```

---

### 3.2 `PluginRegistry` class

Thay thế `_SOURCE_CACHE` dict + hardcoded list trong `get_source()`.

```python
class PluginRegistry:
    def __init__(self): ...

    def register(self, cls: type[BaseSource]) -> None:
        """Register một source class. Tự sort theo priority sau mỗi register."""

    def discover(self, plugin_dir: Path) -> None:
        """
        Scan tất cả *.py trong plugin_dir (không đệ quy, bỏ qua _*.py).
        Import từng file, tìm subclass của BaseSource, gọi register().
        Fail soft: log WARNING + skip nếu import error.
        Security: chỉ load nếu file thuộc sở hữu của current user
                  (os.stat(py_file).st_uid == os.getuid()).
        """

    def get(
        self, url: str,
        client: Any | None = None,
        browser: Any | None = None
    ) -> BaseSource | None:
        """
        Tìm source phù hợp theo URL.
        Iterate theo thứ tự priority (thấp nhất trước).
        Inject deps tự động bằng inspect.signature() — fix #5.
        Cache instance khi client=None và browser=None.
        """

    def slug_candidates(self, slug: str) -> list[tuple[type[BaseSource], str]]:
        """
        Gọi cls.slug_to_url(slug) trên từng registered source.
        Trả list (cls, candidate_url) cho các source có kết quả khác None.
        Dùng để refactor resolve_story_url() — fix #4.
        """

    def clear_cache(self) -> None:
        """Xóa instance cache. Dùng trong tests."""
```

**Module-level bootstrap:**

```python
REGISTRY = PluginRegistry()

def _bootstrap() -> None:
    # 1. Built-in sources (priority thấp nhất = ưu tiên cao nhất)
    from .valvrareteam import ValvrareteamSource   # Phase 2
    from .lnhako import LnHakoSource
    from .truyenfull import TruyenFullSource
    REGISTRY.register(ValvrareteamSource)   # priority=10
    REGISTRY.register(TruyenFullSource)     # priority=50
    REGISTRY.register(LnHakoSource)         # priority=50

    # 2. External plugins: ~/.config/vvr-scraper/plugins/
    from ..utils import get_config_dir
    plugin_dir = Path(get_config_dir()) / "plugins"
    if plugin_dir.is_dir():
        REGISTRY.discover(plugin_dir)

    # 3. Extra paths từ env (colon-separated)
    for p in filter(None, os.getenv("VVR_PLUGIN_PATHS", "").split(":")):
        path = Path(p)
        if path.is_dir():
            REGISTRY.discover(path)

_bootstrap()

# Backward-compat alias để không break tests hiện tại
_SOURCE_CACHE = REGISTRY._cache

def get_source(url, client=None, browser=None):
    return REGISTRY.get(url, client, browser)
```

---

### 3.3 Fix `scraper_core.py`

**Fix #3 — Hybrid fallback trap:**

Trong `scrape_chapters()`, thêm kiểm tra URL trước khi trigger Playwright VVR fallback:

```python
# Trước (hiện tại):
if not content:
    content = await lay_chuong_voi_hinh_anh(browser, url, ...)

# Sau:
if not content and "valvrareteam.net" in url:
    # Playwright fallback chỉ hợp lý cho VVR — selector .chapter-content là VVR-specific
    content = await lay_chuong_voi_hinh_anh(browser, url, ...)
elif not content:
    logger.warning(f"Custom source failed, no Playwright fallback for: {url}")
```

Trong `lay_chuong_httpx()`, khi custom source raise exception, **không** swallow:

```python
# Trước (hiện tại):
except Exception as e:
    logger.error(f"Custom source scrape failed for {url}: {e}")
    return None  # triggers VVR fallback

# Sau:
except Exception as e:
    logger.error(f"Custom source scrape failed for {url}: {e}")
    raise  # caller (scrape_chapters) quyết định fallback hay không
```

**Fix #2 — Cover image cho custom sources:**

Trong `lay_thong_tin_truyen()`, sau khi custom source trả `StoryInfo`:

```python
if "valvrareteam.net" not in url:
    source = REGISTRY.get(url, client=client)
    if source:
        info = await source.get_info(url)
        # Tải cover nếu source trả cover_url nhưng không có cover_path
        if info.cover_url and not info.cover_path:
            cover_bytes = await source.fetch_cover(info.cover_url)
            if cover_bytes:
                _fd, cover_path = tempfile.mkstemp(suffix=".jpg", prefix="vvr_cover_")
                os.close(_fd)
                await asyncio.to_thread(lambda: open(cover_path, "wb").write(cover_bytes))
                info.cover_path = cover_path
        return info
```

---

### 3.4 Fix `utils.py:resolve_story_url()`

Thay hardcoded `candidate_urls` bằng `REGISTRY.slug_candidates()`:

```python
# Trước (hiện tại):
candidate_urls = [
    f"https://truyenfull.vision/truyen/{normalized}",
    f"https://ln.hako.vn/truyen/{normalized}",
]

# Sau:
from .sources import REGISTRY
candidate_pairs = REGISTRY.slug_candidates(normalized)
for _cls, candidate in candidate_pairs:
    source = REGISTRY.get(candidate, client=client)
    if source:
        try:
            info = await source.get_info(candidate)
            if info and info.title != "Unknown":
                return candidate
        except Exception as e:
            logger.debug(f"Source URL probe failed for {candidate}: {e}")
```

---

### 3.5 Phase 2: `ValvrareteamSource`

Tạo `vvr_scraper/sources/valvrareteam.py`. Extract toàn bộ VVR-specific logic từ `scraper_core.py` và `tao_so_do_cay.py` vào class này.

**Giữ nguyên hoàn toàn:**
- Logic SSR endpoint (`VVR_SSR_URL` env)
- HTML parsing (`.rd-stat-item`, `.rd-stats-item`, `.rd-info-row`, fallbacks)
- Cover download (inline trong `lay_thong_tin_truyen` hiện tại → `fetch_cover()` override)
- Chapter content: HTTPX fast mode (`.chapter-content`) + Playwright reliable mode (`.chapter-content p, .chapter-card p`)
- `tao_so_do_cay` Playwright logic (`.module-container`, `.module-title`, `.chapter-title-link`)
- Session state + JWT token handling

```python
class ValvrareteamSource(BaseSource):
    base_urls = ["valvrareteam.net"]
    priority = 10
    name = "valvrareteam"
    requires_browser = True  # cần browser cho get_chapter_list + Playwright mode

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        # VVR không dùng slug probe — dùng sitemap thay thế
        # resolve_story_url() vẫn giữ sitemap logic riêng cho VVR
        return None
```

Sau khi extract, `scraper_core.py` bỏ toàn bộ `if "valvrareteam.net" not in url` conditionals — chỉ còn:

```python
source = REGISTRY.get(url, client=client, browser=browser)
if source:
    return await source.get_info(url)
raise ValueError(f"No source found for URL: {url}")
```

---

### 3.6 Phase 3: Chuẩn hóa LnHako & TruyenFull

Không thay đổi logic crawl. Chỉ thêm class-level declarations và adopt contract mới:

**LnHakoSource:**
```python
class LnHakoSource(BaseSource):
    base_urls = ["ln.hako.vn"]
    priority = 50
    name = "ln-hako"
    requires_browser = True  # get_content() yêu cầu browser

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        return f"https://ln.hako.vn/truyen/{slug}"

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        if not self.browser:
            raise RuntimeError("Browser instance required for LnHakoSource")
        # ... logic Playwright hiện tại giữ nguyên ...
        # Thay return [] bằng raise nếu thất bại sau max_attempts
```

**TruyenFullSource:**
```python
class TruyenFullSource(BaseSource):
    base_urls = ["truyenfull.vision"]
    priority = 50
    name = "truyenfull"
    requires_browser = False

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        return f"https://truyenfull.vision/{slug}"

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        # ... logic HTTPX + BeautifulSoup hiện tại giữ nguyên ...
        # Thay return [] cuối thành raise RuntimeError nếu không extract được gì
```

---

## 4. Plugin Writer Guide

### 4.1 Cài đặt & Khởi động

Tạo file Python tại thư mục plugin:

```
~/.config/vvr-scraper/plugins/my_source.py
```

VVR **tự động scan** thư mục này mỗi lần khởi động. Không cần đăng ký, không cần sửa bất kỳ file nào trong core.

Nếu muốn dùng thư mục khác (ví dụ trong quá trình dev), set env:

```bash
export VVR_PLUGIN_PATHS=/path/to/my/plugins:/another/path
```

### 4.2 Minimal plugin

```python
# ~/.config/vvr-scraper/plugins/my_source.py
import httpx
from vvr_scraper.sources import BaseSource, ChapterTreeItem, VolumeTreeItem, SearchResult
from vvr_scraper.models import ContentItem, StoryInfo
from vvr_scraper.utils import HEADERS
from typing import ClassVar

class MySiteSource(BaseSource):
    # --- Khai báo bắt buộc ---
    base_urls: ClassVar = ["mysite.example"]   # domain để matching URL
    priority: ClassVar = 80                    # thấp hơn = ưu tiên cao hơn khi conflict domain
    name: ClassVar = "my-site"                 # id duy nhất, dùng trong log
    requires_browser: ClassVar = False         # True nếu cần Playwright

    def __init__(self, client: httpx.AsyncClient | None = None):
        # Dùng _owns_client pattern để tránh leak connection pool
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        # Cho phép user dùng slug thay vì full URL
        # Trả None nếu site không hỗ trợ slug dạng này
        return f"https://mysite.example/truyen/{slug}"

    async def get_info(self, url: str) -> StoryInfo:
        resp = await self.client.get(url)
        resp.raise_for_status()
        # ... parse HTML ...
        return StoryInfo(
            title=title,          # QUAN TRỌNG: "Unknown" nếu không tìm thấy truyện
            author=author,
            description=description,
            slug=url.rstrip("/").split("/")[-1],  # convention: slug = last path segment
            genres=genres,
            cover_url=cover_url,  # source chỉ cần set cover_url, VVR tự tải về
        )

    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        # ...parse danh sách chapter...
        return [
            VolumeTreeItem(
                volume="Volume 1",
                chapters=[
                    ChapterTreeItem(
                        title="Chương 1",
                        url="https://mysite.example/truyen/ten-truyen/chuong-1",  # PHẢI là absolute URL
                        locked=False,
                    )
                ]
            )
        ]

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        resp = await self.client.get(chapter_url)
        resp.raise_for_status()
        # ...parse nội dung...
        if not content:
            raise RuntimeError(f"Không extract được nội dung từ: {chapter_url}")
        # KHÔNG return [] hoặc None khi thất bại — phải raise
        return content
```

### 4.3 Plugin cần Playwright (browser)

Nếu site dùng JavaScript rendering:

```python
from playwright.async_api import Browser

class MySiteSource(BaseSource):
    base_urls: ClassVar = ["mysite.example"]
    requires_browser: ClassVar = True   # khai báo để VVR biết inject browser

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        browser: Browser | None = None,   # VVR tự inject nếu có
    ):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0)
        self.browser = browser  # KHÔNG tự gọi async_playwright() — sẽ leak Chromium process

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        if not self.browser:
            raise RuntimeError("Browser required for MySiteSource")
        page = await self.browser.new_page()
        try:
            await page.goto(chapter_url, wait_until="networkidle", timeout=60000)
            # ...extract content...
            return content
        finally:
            await page.close()  # luôn đóng page sau khi dùng
```

### 4.4 Rate limiting & retry

Nếu site có rate limit, tự implement retry trong source (VVR không tự retry cho custom sources):

```python
import asyncio

async def get_content(self, chapter_url: str) -> list[ContentItem]:
    for attempt in range(3):
        try:
            resp = await self.client.get(chapter_url)
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            # ...parse...
            return content
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)
```

**Lưu ý về concurrency:** VVR tự động giảm concurrency xuống còn `n // 2` khi phát hiện URL không phải VVR. Nếu site của bạn cần giới hạn chặt hơn, hãy dùng retry + sleep thay vì dựa vào concurrency bên ngoài.

### 4.5 Contracts bắt buộc — tóm tắt

| Method | Behavior khi thất bại | Lý do |
|--------|----------------------|-------|
| `get_content()` | **raise exception** | Không raise → VVR timeout 60s chạy VVR Playwright fallback vô ích |
| `get_info()` | trả `StoryInfo(title="Unknown")` | `resolve_story_url()` dùng làm sentinel check |
| `get_chapter_list()` | raise exception | Rõ ràng hơn so với trả list rỗng |

| Field | Yêu cầu | Lý do |
|-------|---------|-------|
| `ChapterTreeItem.url` | **Absolute URL** | `job_runner` chỉ prepend VVR base URL cho relative paths |
| `StoryInfo.slug` | `url.rstrip("/").split("/")[-1]` | Dùng làm tên thư mục output |
| `StoryInfo.cover_url` | URL đầy đủ | VVR tự tải cover bytes qua `fetch_cover()` |

### 4.6 Debugging plugin

Khi VVR khởi động, log sẽ hiển thị plugin được load:

```
INFO | Plugin loaded: my-site (mysite.example) — priority=80
```

Nếu plugin fail import:

```
WARNING | Failed loading plugin /path/to/my_source.py: ModuleNotFoundError: No module named 'beautifulsoup4'
```

Để test plugin nhanh mà không restart VVR, chạy từ Python shell:

```python
import asyncio
from vvr_scraper.sources import REGISTRY

async def test():
    source = REGISTRY.get("https://mysite.example/truyen/ten-truyen")
    print(source)  # MySiteSource instance hoặc None
    if source:
        info = await source.get_info("https://mysite.example/truyen/ten-truyen")
        print(info)
        await source.aclose()

asyncio.run(test())
```

### 4.7 Ví dụ thực tế: source chỉ dùng HTTPX

Tham khảo `vvr_scraper/sources/truyenfull.py` — source HTTPX-only với retry, pagination AJAX, và `<br><br>` markup parsing.

### 4.8 Ví dụ thực tế: source dùng Playwright

Tham khảo `vvr_scraper/sources/lnhako.py` — source Playwright với lazy-loaded volumes và exponential backoff.

---

## 5. Testing Strategy

Mỗi phase có test riêng trước khi sang phase tiếp theo.

| Phase | Test cần thêm |
|-------|--------------|
| Phase 1 | `PluginRegistry.discover()` với fixture plugin file tạm; priority sort; slug_candidates; cover download cho custom source; fallback không trigger với non-VVR URL |
| Phase 2 | Regression: VVR scrape end-to-end vẫn hoạt động sau extract; `ValvrareteamSource` pass tất cả test hiện tại |
| Phase 3 | LnHako/TruyenFull: `get_content()` raise thay vì return `[]`; `slug_to_url()` trả đúng URL |

Test fixture cho dynamic loading:
```python
# Tạo temp plugin file → gọi REGISTRY.discover(tmp_dir) → assert source được register
```

Backward-compat: `_SOURCE_CACHE = REGISTRY._cache` alias giữ nguyên để tests hiện tại không cần sửa.

---

## 6. File changes summary

| File | Thay đổi |
|------|---------|
| `vvr_scraper/sources/__init__.py` | Thêm `PluginRegistry`; refactor `BaseSource` contract; `_bootstrap()`; alias `_SOURCE_CACHE` |
| `vvr_scraper/scraper_core.py` | Fix fallback trap; fix cover download cho custom sources; xóa VVR conditionals (Phase 2) |
| `vvr_scraper/utils.py` | Refactor `resolve_story_url()` slug probe dùng `REGISTRY.slug_candidates()` |
| `vvr_scraper/sources/valvrareteam.py` | **Tạo mới** — extract VVR logic từ scraper_core + tao_so_do_cay (Phase 2) |
| `vvr_scraper/sources/lnhako.py` | Thêm class attrs, `slug_to_url()`, `get_content()` raise thay vì return `[]` (Phase 3) |
| `vvr_scraper/sources/truyenfull.py` | Thêm class attrs, `slug_to_url()`, `get_content()` raise thay vì return `[]` (Phase 3) |
| `vvr_scraper/tao_so_do_cay.py` | Logic VVR chuyển sang `ValvrareteamSource` (Phase 2) |
| `tests/` | Test mới cho PluginRegistry, slug_candidates, cover fix, fallback fix, regression |
