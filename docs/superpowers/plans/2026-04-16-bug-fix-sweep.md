# Bug Fix Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 17 confirmed bugs across the VVR-Scraper codebase with minimal, surgical changes (no refactoring).

**Architecture:** Each bug fix is 1-5 lines, targets exactly the affected file/location. Grouped by file to minimize context switching. 11 tasks total covering 16 files.

**Tech Stack:** Python 3.12+, httpx, Playwright, FastAPI, ReportLab, pydub, aiosqlite

**Spec:** `docs/superpowers/specs/2026-04-16-bug-fix-sweep.md`

---

## File Map

| Task | Files Modified | Bugs |
|------|---------------|------|
| 1 | `vvr_scraper/web/routes/opds.py` | #2 |
| 2 | `vvr_scraper/opds.py` | #18 |
| 3 | `vvr_scraper/session_manager.py` | #3 |
| 4 | `vvr_scraper/exporter.py` | #4, #10 |
| 5 | `vvr_scraper/web/routes/correction.py` | #5, #12 |
| 6 | `vvr_scraper/web/state.py` | #6 |
| 7 | `vvr_scraper/video_renderer.py` | #7 |
| 8 | `vvr_scraper/job_worker.py` | #8, #9 |
| 9 | `vvr_scraper/web/routes/api.py`, `vvr_scraper/cli.py` | #11 |
| 10 | `vvr_scraper/web/routes/library.py` | #13, #14 |
| 11 | `vvr_scraper/sources/__init__.py`, `vvr_scraper/sources/truyenfull.py`, `vvr_scraper/sources/lnhako.py`, `vvr_scraper/scraper_core.py`, `vvr_scraper/tao_so_do_cay.py` | #15, #16, #17 |

---

### Task 1: OPDS path traversal fix (Bug #2)

**Files:**
- Modify: `vvr_scraper/web/routes/opds.py`

- [ ] **Step 1: Add format whitelist**

At the top of `vvr_scraper/web/routes/opds.py`, after existing imports, add:

```python
ALLOWED_OPDS_FORMATS = {"epub", "pdf", "mobi", "azw3"}
```

- [ ] **Step 2: Add validation in `opds_download` route**

Find the `opds_download` function (around line 177). Before the line that constructs `file_path` (around line 190), add:

```python
    if fmt.lower() not in ALLOWED_OPDS_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")
```

This should go right after the `filename` construction and before `file_path = os.path.join(...)`.

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/web/routes/opds.py
```

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/web/routes/opds.py
git commit -m "fix(security): block path traversal via fmt param in OPDS download"
```

---

### Task 2: Fix non-UTC datetime in OPDS feeds (Bug #18)

**Files:**
- Modify: `vvr_scraper/opds.py`
- Modify: `vvr_scraper/web/routes/opds.py`

- [ ] **Step 1: Fix `opds.py`**

At line 36 and any other occurrences of `datetime.now()`:

```python
# Change from:
from datetime import datetime
# To (add timezone to import):
from datetime import datetime, timezone
```

Then replace every `datetime.now().isoformat() + "Z"` with `datetime.now(timezone.utc).isoformat()` (no + "Z" needed since the timezone is included).

In `opds.py`, find and replace:
- Line 36: `datetime.now().isoformat() + "Z"` → `datetime.now(timezone.utc).isoformat()`

- [ ] **Step 2: Fix `web/routes/opds.py`**

Same pattern — change import and replace `datetime.now().isoformat() + "Z"` at lines 54, 146, 166.

```python
# Change import from:
from datetime import datetime
# To:
from datetime import datetime, timezone
```

Replace each occurrence of `datetime.now().isoformat() + "Z"` with `datetime.now(timezone.utc).isoformat()`.

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/opds.py vvr_scraper/web/routes/opds.py
```

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/opds.py vvr_scraper/web/routes/opds.py
git commit -m "fix: use timezone-aware UTC datetime in OPDS feeds"
```

---

### Task 3: Restrict session file permissions (Bug #3)

**Files:**
- Modify: `vvr_scraper/session_manager.py`

- [ ] **Step 1: Add `os.chmod` after file write**

In `session_manager.py`, find the `save_session` function. After the `json.dump` call that writes the session file, add:

```python
    os.chmod(file_path, 0o600)
```

Make sure `os` is imported (it should already be imported at the top of the file).

- [ ] **Step 2: Verify**

```bash
ruff check vvr_scraper/session_manager.py
```

- [ ] **Step 3: Commit**

```bash
git add vvr_scraper/session_manager.py
git commit -m "fix(security): restrict session file to owner-only permissions (0o600)"
```

---

### Task 4: Fix BytesIO seek bug and XSS in EPUB export (Bugs #4, #10)

**Files:**
- Modify: `vvr_scraper/exporter.py`

- [ ] **Step 1: Fix BytesIO seek (Bug #4)**

In `exporter.py`, find the PDF image rendering section (around lines 271-275). Add `img_data.seek(0)` between `PILImage.open()` and `Image()`:

```python
            img_data = BytesIO(image_cache[item.data])
            pil_img = PILImage.open(img_data)
            w, h = pil_img.size
            ratio = min(max_w / w, max_h / h, 1)
            img_data.seek(0)  # Reset stream for ReportLab Image
            story.append(Image(img_data, width=w * ratio, height=h * ratio))
```

- [ ] **Step 2: Fix XSS in EPUB (Bug #10)**

At the top of `exporter.py`, add to imports:

```python
from html import escape
```

Then find the EPUB chapter HTML building section (around lines 187-191) and add `escape()`:

```python
            html = f"<h1>{escape(title)}</h1>"
            ...
                    html += f"<p>{escape(norm.data)}</p>"
```

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/exporter.py
```

- [ ] **Step 4: Run exporter tests**

```bash
pytest tests/test_exporter_audio.py -v
```

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/exporter.py
git commit -m "fix: BytesIO seek for PDF images + escape HTML in EPUB generation"
```

---

### Task 5: Fix correction.py dead code and aggressive file deletion (Bugs #5, #12)

**Files:**
- Modify: `vvr_scraper/web/routes/correction.py`

- [ ] **Step 1: Remove dead `_get_output_dir_for_slug` function (Bug #5)**

Delete the entire function `_get_output_dir_for_slug` (lines 88-114). It's dead code — all routes use `_async_get_output_dir`.

- [ ] **Step 2: Fix aggressive file deletion (Bug #12)**

Find the section that deletes MP3/WAV files after saving corrections (around lines 265-275). Replace it with chapter-scoped deletion:

```python
    chapter_dir = script_path.parent
    deleted = []
    for pattern in ["*.mp3", "*.wav"]:
        for f in chapter_dir.glob(pattern):
            if f".{chapter_idx}." in f.name or f"-{chapter_idx}." in f.name:
                try:
                    f.unlink()
                    deleted.append(str(f.name))
                except OSError:
                    pass
```

Remove the `"manifest.json"` pattern from the loop (too aggressive — may delete shared manifest).

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/web/routes/correction.py
```

- [ ] **Step 4: Run correction tests**

```bash
pytest tests/test_correction.py -v
```

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/web/routes/correction.py
git commit -m "fix: remove dead sync helper + scope file deletion to chapter index"
```

---

### Task 6: Fix dead WebSocket connection cleanup (Bug #6)

**Files:**
- Modify: `vvr_scraper/web/state.py`

- [ ] **Step 1: Update `broadcast` method**

Find the `broadcast` method in the `ConnectionManager` class (around lines 34-39). Replace:

```python
    async def broadcast(self, message: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.active_connections.remove(conn)
```

- [ ] **Step 2: Verify**

```bash
ruff check vvr_scraper/web/state.py
```

- [ ] **Step 3: Commit**

```bash
git add vvr_scraper/web/state.py
git commit -m "fix: remove dead WebSocket connections on broadcast failure"
```

---

### Task 7: Fix port race condition in video renderer (Bug #7)

**Files:**
- Modify: `vvr_scraper/video_renderer.py`

- [ ] **Step 1: Prevent port race by using SO_REUSEADDR and polling**

The server runs in a thread (line 128-130), not via `await`. Replace the port allocation block (lines 120-123):

```python
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
```

Then replace the fragile `time.sleep(1)` at line 134 with a health poll:

```python
                # Poll for server readiness instead of sleeping
                for _ in range(30):
                    try:
                        async with httpx.AsyncClient() as hc:
                            resp = await hc.get(f"http://127.0.0.1:{port}/static/cinema.html")
                            if resp.status_code == 200:
                                break
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)
```

Note: `SO_REUSEADDR` alone solves the race — uvicorn can bind even though we briefly had the port. The health poll replaces the fragile `time.sleep(1)`.

- [ ] **Step 2: Verify**

```bash
ruff check vvr_scraper/video_renderer.py
```

- [ ] **Step 3: Commit**

```bash
git add vvr_scraper/video_renderer.py
git commit -m "fix: prevent port race by keeping socket open until uvicorn binds"
```

---

### Task 8: Fix recursive cancel_dependents and priority mismatch (Bugs #8, #9)

**Files:**
- Modify: `vvr_scraper/job_worker.py`

- [ ] **Step 1: Fix priority default mismatch (Bug #9)**

Find the line that reads priority from the job (around line 25):

```python
priority = getattr(job.root, "priority", 0)
```

Change the fallback from `3` to `0`.

- [ ] **Step 2: Convert recursive `cancel_dependents` to iterative BFS (Bug #8)**

Find the `cancel_dependents` method (around line 257). Replace the recursive implementation with:

```python
    async def cancel_dependents(self, failed_job_id: str):
        queue = [failed_job_id]
        while queue:
            current_id = queue.pop(0)
            dependents = await self.db.get_dependents(current_id)
            for dep in dependents:
                if dep["status"] in ("waiting", "pending"):
                    await self.db.update_job_status(dep["id"], "cancelled")
                    queue.append(dep["id"])
```

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/job_worker.py
```

- [ ] **Step 4: Run job tests**

```bash
pytest tests/test_job_worker.py tests/test_job_worker_concurrency.py -v
```

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/job_worker.py
git commit -m "fix: iterative BFS for cancel_dependents + align priority default to 0"
```

---

### Task 9: Fix URL encoding in SSR search (Bug #11)

**Files:**
- Modify: `vvr_scraper/web/routes/api.py`
- Modify: `vvr_scraper/cli.py`

- [ ] **Step 1: Fix `api.py`**

Find the SSR search request (around line 46). Replace the manually-constructed URL with `params` argument:

```python
response = await client.get(SSR_API_URL, params={"title": q})
```

- [ ] **Step 2: Fix `cli.py`**

Find the `NovelCompleter.get_completions` method (around line 87). Replace:

```python
response = self.client.get(url, params={"title": text}, headers=headers)
```

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/web/routes/api.py vvr_scraper/cli.py
```

- [ ] **Step 4: Run API tests**

```bash
pytest tests/test_web_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/web/routes/api.py vvr_scraper/cli.py
git commit -m "fix: URL-encode SSR search query parameters"
```

---

### Task 10: Fix duplicate library endpoints and sequential HTTP (Bugs #13, #14)

**Files:**
- Modify: `vvr_scraper/web/routes/library.py`

- [ ] **Step 1: Remove duplicate endpoint (Bug #13)**

Find the `GET /library/check-updates` route (around lines 201-206). Delete the entire route handler. Keep `POST /library/check` (around lines 209-214).

- [ ] **Step 2: Add concurrency to `check_library_updates` (Bug #14)**

Find the sequential `for` loop in `check_library_updates` (around line 113). Replace with `asyncio.gather` with semaphore:

```python
    sem = asyncio.Semaphore(5)

    async def check_one(novel, i):
        async with sem:
            slug = novel.get("slug", "")
            if not slug:
                return
            try:
                from .download import run_scrape_task
                from .state import active_tasks, task_log_buffers, manager
                # ... existing per-novel logic ...
            except Exception as e:
                logger.error(f"Error checking {slug}: {e}")

    await asyncio.gather(*(check_one(n, i) for i, n in enumerate(novels)))
```

Note: Extract the per-novel body from the existing `for` loop into the `check_one` coroutine.

- [ ] **Step 3: Verify**

```bash
ruff check vvr_scraper/web/routes/library.py
```

- [ ] **Step 4: Run library tests**

```bash
pytest tests/test_library_sync.py -v
```

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/web/routes/library.py
git commit -m "fix: remove duplicate check endpoint + add concurrency to library update"
```

---

### Task 11: Fix source adapters, temp files, and get_source caching (Bugs #15, #16, #17)

**Files:**
- Modify: `vvr_scraper/sources/__init__.py`
- Modify: `vvr_scraper/sources/truyenfull.py`
- Modify: `vvr_scraper/sources/lnhako.py`
- Modify: `vvr_scraper/scraper_core.py`
- Modify: `vvr_scraper/tao_so_do_cay.py`

- [ ] **Step 1: Add `aclose()` to `BaseSource` (Bug #15)**

In `vvr_scraper/sources/__init__.py`, add to the `BaseSource` ABC:

```python
    async def aclose(self):
        """Clean up resources (e.g., httpx client)."""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()
```

- [ ] **Step 2: Implement `aclose()` in `TruyenFullSource`**

In `vvr_scraper/sources/truyenfull.py`, add:

```python
    async def aclose(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()
```

Make sure to track whether the client was externally provided or created internally. Add a `_owns_client` flag:

```python
def __init__(self, client=None):
    self.client = client or httpx.AsyncClient()
    self._owns_client = client is None
```

Then in `aclose()`:
```python
    async def aclose(self):
        if self._owns_client and self.client and not self.client.is_closed:
            await self.client.aclose()
```

- [ ] **Step 3: Implement `aclose()` in `LnHakoSource`**

Same pattern as TruyenFullSource — add `_owns_client` flag and `aclose()` method.

- [ ] **Step 4: Cache source instances in `get_source()` (Bug #17)**

In `vvr_scraper/sources/__init__.py`, add a cache dict at module level:

```python
from urllib.parse import urlparse

_source_cache: dict[str, BaseSource] = {}
```

Update `get_source()` to use the cache:

```python
def get_source(url, client=None, browser=None) -> BaseSource | None:
    domain = urlparse(url).netloc

    if domain in _source_cache:
        return _source_cache[domain]

    source = None
    if "truyenfull" in domain:
        source = TruyenFullSource(client=client)
    elif any(d in domain for d in ["lnhako.vn", "hako.vn"]):
        source = LnHakoSource(client=client, browser=browser)

    if source:
        _source_cache[domain] = source

    return source
```

- [ ] **Step 5: Fix temp file accumulation in `scraper_core.py` (Bug #16)**

In `scraper_core.py`, find the cover download section (around lines 146-163). Wrap the temp file in a try/finally:

```python
            def save_cover():
                _fd, _cover_path = tempfile.mkstemp(suffix=".jpg", prefix="vvr_cover_")
                os.close(_fd)
                try:
                    with open(_cover_path, "wb") as f:
                        f.write(response.content)
                    return _cover_path
                except Exception:
                    os.remove(_cover_path)
                    raise
```

- [ ] **Step 6: Fix temp file accumulation in `tao_so_do_cay.py` (Bug #16)**

In `tao_so_do_cay.py`, find the temp file creation (around line 301). Wrap in try/finally:

```python
    temp_filename = f"temp_sync_{uuid.uuid4().hex[:8]}.json"
    try:
        with open(temp_filename, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        # ... use temp_filename ...
    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError:
                pass
```

- [ ] **Step 7: Verify all changes**

```bash
ruff check vvr_scraper/sources/ vvr_scraper/scraper_core.py vvr_scraper/tao_so_do_cay.py
```

- [ ] **Step 8: Run source and scraper tests**

```bash
pytest tests/test_sources.py tests/test_scraper_core_unit.py tests/test_tao_so_do_cay.py -v
```

- [ ] **Step 9: Commit**

```bash
git add vvr_scraper/sources/ vvr_scraper/scraper_core.py vvr_scraper/tao_so_do_cay.py
git commit -m "fix: add aclose() to source adapters, cache get_source(), fix temp file cleanup"
```

---

## Final Verification

After all 11 tasks are complete:

- [ ] **Run full test suite**

```bash
ruff check .
pytest -v --timeout=300
```

- [ ] **Run typecheck if available**

```bash
# Check if typecheck command exists in pyproject.toml or package.json
```

- [ ] **Final commit (if any test fixes needed)**

```bash
git add -A
git commit -m "fix: address test failures from bug fix sweep"
```
