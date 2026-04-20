# Spec: Bug Fix Sweep — All Known Bugs

**Date:** 2026-04-16
**Status:** Approved
**Scope:** Fix 17 confirmed bugs across the VVR-Scraper codebase. Minimal, surgical fixes only — no refactoring.

## Context

A comprehensive codebase review identified 18 bugs (3 critical security, 7 high-priority data/rendering, 8 medium). API authentication is deferred — remaining 17 bugs are addressed in this spec.

**Approach:** Each fix is 1-5 lines, touches exactly the affected location, and does not introduce new abstractions or refactors.

---

## Section 1: Critical Security (2 bugs)

### Bug #2 — Path traversal via `fmt` param in OPDS download

**File:** `vvr_scraper/web/routes/opds.py`, line ~190
**Problem:** `fmt` query param is injected directly into `os.path.join(output_folder, f"{filename}.{fmt.lower()}")` without validation. Attacker can send `fmt=../../../etc/passwd` to read arbitrary files.

**Fix:**
- Define a constant `ALLOWED_OPDS_FORMATS = {"epub", "pdf", "mobi", "azw3"}` at module level.
- Before constructing the file path, validate `fmt.lower() in ALLOWED_OPDS_FORMATS`. If not, return HTTP 400.

### Bug #3 — Session cookies saved with world-readable permissions

**File:** `vvr_scraper/session_manager.py`, line ~10
**Problem:** `save_session()` writes session JSON without restricting file permissions. Default umask creates 0o644 (readable by all users).

**Fix:**
- After writing the file, call `os.chmod(file_path, 0o600)` to restrict to owner-only read/write.

---

## Section 2: High-Priority Bugs — Data & Rendering (7 bugs)

### Bug #4 — BytesIO seek bug in PDF image rendering

**File:** `vvr_scraper/exporter.py`, lines 271-275
**Problem:** `PILImage.open(img_data)` consumes the stream, then `Image(img_data, ...)` (ReportLab) tries to read from the same stream at the end position. Produces empty/broken images.

**Fix:**
- Add `img_data.seek(0)` between `PILImage.open(img_data)` and the `Image(img_data, ...)` call.

### Bug #5 — Blocking `run_until_complete` in sync helper (dead code)

**File:** `vvr_scraper/web/routes/correction.py`, lines 88-114
**Problem:** `_get_output_dir_for_slug` uses `asyncio.get_event_loop().run_until_complete()` inside an async context. Will crash on Python 3.10+ with nested event loops. The function is dead code — all routes use `_async_get_output_dir`.

**Fix:**
- Delete the entire `_get_output_dir_for_slug` function (lines 88-114).

### Bug #6 — Dead WebSocket connections never cleaned up

**File:** `vvr_scraper/web/state.py`, lines 34-39
**Problem:** `broadcast()` swallows exceptions but never removes failed connections. Stale sockets accumulate, slowing every broadcast.

**Fix:**
- Collect failed connections during iteration, then remove them after the loop:
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

### Bug #7 — Port race condition in video renderer

**File:** `vvr_scraper/video_renderer.py`, lines 120-123
**Problem:** Socket is bound to get a free port, then immediately closed before uvicorn binds. Another process can claim the port in the gap.

**Fix:**
- Keep the socket open and pass the file descriptor to uvicorn, or delay closing until after the server is confirmed started. Simplest fix: keep the socket open, set `SO_REUSEADDR`, and close it in a `finally` block after `server.serve()` completes.

### Bug #8 — Recursive `cancel_dependents` hits recursion limit

**File:** `vvr_scraper/job_worker.py`, line ~257
**Problem:** `cancel_dependents` calls itself recursively. Long dependency chains hit Python's ~1000 recursion limit.

**Fix:**
- Replace recursion with iterative BFS using a queue/stack:
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

### Bug #9 — Priority default mismatch between model and worker

**File:** `vvr_scraper/job_worker.py`, line ~25
**Problem:** `job_models.py` defaults `priority` to 0, but `getattr(job.root, "priority", 3)` in the worker defaults to 3.

**Fix:**
- Change the fallback in `job_worker.py` to `getattr(job.root, "priority", 0)`.

### Bug #10 — XSS in EPUB HTML generation

**File:** `vvr_scraper/exporter.py`, lines 187, 191
**Problem:** Chapter title and text content are injected raw into HTML strings: `f"<h1>{title}</h1>"` and `f"<p>{norm.data}</p>"`. Malicious titles like `<script>alert(1)</script>` end up in the EPUB.

**Fix:**
- Import `html.escape` and apply it to title and text content:
```python
from html import escape
html = f"<h1>{escape(title)}</h1>"
...
html += f"<p>{escape(norm.data)}</p>"
```

---

## Section 3: Medium-Priority Bugs (8 bugs)

### Bug #11 — Unencoded query parameter in SSR search

**File:** `vvr_scraper/web/routes/api.py`, line 46; `vvr_scraper/cli.py`, line 87
**Problem:** User input `q` is interpolated directly into the URL: `f"{SSR_API_URL}?title={q}"`. Special characters break the request.

**Fix:**
- In `api.py`: use httpx `params` argument: `response = await client.get(SSR_API_URL, params={"title": q})`.
- In `cli.py`: same pattern: `response = self.client.get(url, params={"title": text}, headers=headers)`.

### Bug #12 — Aggressive file deletion on correction save

**File:** `vvr_scraper/web/routes/correction.py`, lines 265-275
**Problem:** After saving corrections, deletes ALL `*.mp3`, `*.wav`, `manifest.json` in the chapter directory. Destroys files from other chapters sharing the same directory.

**Fix:**
- Only delete files whose name contains the chapter's index pattern (e.g., `f".{chapter_idx}."` or `f"-{chapter_idx}."`).
- Skip `manifest.json` deletion (too broad); only delete if the file is chapter-scoped.

### Bug #13 — Duplicate library check endpoints

**File:** `vvr_scraper/web/routes/library.py`, lines 201-214
**Problem:** `GET /library/check-updates` and `POST /library/check` do exactly the same thing. No rate limiting on either.

**Fix:**
- Remove `GET /library/check-updates`. Keep `POST /library/check` (POST is correct for mutation actions).

### Bug #14 — Sequential HTTP in library update check

**File:** `vvr_scraper/web/routes/library.py`, line ~113
**Problem:** `check_library_updates` iterates novels sequentially in a `for` loop. With a large library, this is very slow.

**Fix:**
- Add `asyncio.gather` with a semaphore (e.g., 5 concurrent) matching the pattern already used in `sync_all_novels`.

### Bug #15 — Source adapters lack `aclose()` method

**Files:** `vvr_scraper/sources/truyenfull.py` (line 38), `vvr_scraper/sources/lnhako.py` (line 17)
**Problem:** When no external `client` is passed, each source creates its own `httpx.AsyncClient` that is never closed.

**Fix:**
- Add `aclose()` method to `BaseSource` ABC.
- Implement in `TruyenFullSource` and `LnHakoSource` to close their client if they own it.
- Optionally add `__aenter__`/`__aexit__` for context manager usage.

### Bug #16 — Temp file accumulation on crash

**Files:** `vvr_scraper/scraper_core.py` (line 148), `vvr_scraper/tao_so_do_cay.py` (line 301)
**Problem:** `tempfile.mkstemp` creates temp files that are only cleaned up in happy paths. Process crashes leave orphaned temp files.

**Fix:**
- In `scraper_core.py`: use `tempfile.TemporaryDirectory` as a context manager wrapping the cover download logic.
- In `tao_so_do_cay.py`: wrap temp file usage in `try/finally` with guaranteed cleanup.

### Bug #17 — `get_source()` re-instantiates on every call

**File:** `vvr_scraper/sources/__init__.py`, line 66
**Problem:** `get_source()` creates new `TruyenFullSource` and `LnHakoSource` on every call. If no client is passed, each creates a new `httpx.AsyncClient` that is never closed.

**Fix:**
- Cache source instances by domain in a module-level dict:
```python
_source_cache: dict[str, BaseSource] = {}
def get_source(url, client=None, browser=None) -> BaseSource | None:
    domain = urlparse(url).netloc
    if domain in _source_cache:
        return _source_cache[domain]
    # ... instantiate and cache before returning
```

### Bug #18 — Non-UTC datetime in OPDS feeds

**Files:** `vvr_scraper/opds.py` (line 36), `vvr_scraper/web/routes/opds.py` (lines 54, 146, 166)
**Problem:** `datetime.now()` is used, then `"Z"` is appended claiming UTC. Local time ≠ UTC.

**Fix:**
- Replace all `datetime.now()` with `datetime.now(timezone.utc)` in OPDS-related code.

---

## Verification

After all fixes are applied:

1. `ruff check .` — no new lint errors
2. `pytest` — all existing tests pass
3. Manual verification for:
   - OPDS download with invalid `fmt` returns 400
   - Session file has 0o600 permissions after `save_session()`
   - PDF export with images produces valid output
   - EPUB export with `<script>` in title produces escaped output
   - WebSocket broadcast removes dead connections
   - `correction.py` save doesn't delete unrelated files

## Files Modified

| File | Bugs Fixed |
|------|-----------|
| `vvr_scraper/web/routes/opds.py` | #2 |
| `vvr_scraper/session_manager.py` | #3 |
| `vvr_scraper/exporter.py` | #4, #10 |
| `vvr_scraper/web/routes/correction.py` | #5, #12 |
| `vvr_scraper/web/state.py` | #6 |
| `vvr_scraper/video_renderer.py` | #7 |
| `vvr_scraper/job_worker.py` | #8, #9 |
| `vvr_scraper/web/routes/api.py` | #11 |
| `vvr_scraper/cli.py` | #11 |
| `vvr_scraper/web/routes/library.py` | #13, #14 |
| `vvr_scraper/sources/truyenfull.py` | #15 |
| `vvr_scraper/sources/lnhako.py` | #15 |
| `vvr_scraper/sources/__init__.py` | #15, #17 |
| `vvr_scraper/scraper_core.py` | #16 |
| `vvr_scraper/tao_so_do_cay.py` | #16 |
| `vvr_scraper/opds.py` | #18 |
