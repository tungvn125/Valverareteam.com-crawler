# LnHako Retry + Playwright Head Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add retry for `LnHakoSource.get_content()` and add global Playwright mode resolution with CLI-first precedence (`--head-playwright` / `--headless-playwright` > `VVR_PLAYWRIGHT_MODE` > default headless).

**Architecture:** Keep behavior centralized by adding one resolver helper in `vvr_scraper/utils.py` and using it at all Playwright launch sites. Keep LnHako retry local to `get_content()` with capped attempts and backoff. Drive all changes with TDD in small red-green-refactor steps.

**Tech Stack:** Python 3.12+, pytest, playwright async API, argparse, FastAPI routes, pydantic models.

---

## File Structure / Responsibilities

- Modify: `vvr_scraper/utils.py`
  - Add Playwright mode resolver (CLI/env/default precedence).
- Modify: `vvr_scraper/sources/lnhako.py`
  - Add retry loop for chapter content fetch only.
- Modify: `vvr_scraper/cli.py`
  - Add mutually exclusive CLI flags and propagate mode.
- Modify: `vvr_scraper/job_models.py`
  - Optional per-job Playwright mode for `run` flow propagation.
- Modify: `vvr_scraper/job_runner.py`
  - Use resolved mode when launching browser in crawl jobs.
- Modify: `vvr_scraper/web/routes/download.py`
  - Use resolved mode at web scrape launch site.
- Modify: `vvr_scraper/web/routes/library.py`
  - Use resolved mode at library sync launch site.
- Modify: `vvr_scraper/tao_so_do_cay.py`
  - Make fallback launch explicit with resolved mode.
- Modify: `vvr_scraper/video_renderer.py`
  - Use resolved mode for renderer launch.
- Modify: `vvr_scraper/web/models.py` (optional if web API should accept explicit mode override later; keep minimal if not required now).
- Test: `tests/test_sources.py`
  - LnHako retry behavior tests.
- Test: `tests/test_cli_unit.py`
  - CLI parse and precedence tests.
- Test: `tests/test_utils_extended.py`
  - Unit tests for resolver behavior.

---

### Task 1: Add failing tests for Playwright mode resolver

**Files:**
- Modify: `tests/test_utils_extended.py`
- Test: `tests/test_utils_extended.py`

- [ ] **Step 1: Write failing test for default behavior (none set => headless)**

```python
# tests/test_utils_extended.py
from vvr_scraper.utils import resolve_playwright_headless

def test_resolve_playwright_headless_defaults_to_true(monkeypatch):
    monkeypatch.delenv("VVR_PLAYWRIGHT_MODE", raising=False)
    assert resolve_playwright_headless() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_utils_extended.py::test_resolve_playwright_headless_defaults_to_true -v`
Expected: FAIL with `ImportError` or `AttributeError` because resolver does not exist yet.

- [ ] **Step 3: Write failing tests for env values + invalid env fallback**

```python
def test_resolve_playwright_headless_from_env_head(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "head")
    assert resolve_playwright_headless() is False


def test_resolve_playwright_headless_from_env_headless(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "headless")
    assert resolve_playwright_headless() is True


def test_resolve_playwright_headless_invalid_env_falls_back_default(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "invalid")
    assert resolve_playwright_headless() is True
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_utils_extended.py -k resolve_playwright_headless -v`
Expected: FAIL because function is not implemented.

- [ ] **Step 5: Write failing tests for CLI override precedence**

```python
def test_resolve_playwright_headless_cli_head_overrides_env(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "headless")
    assert resolve_playwright_headless(cli_mode="head") is False


def test_resolve_playwright_headless_cli_headless_overrides_env(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "head")
    assert resolve_playwright_headless(cli_mode="headless") is True
```

- [ ] **Step 6: Run tests to verify they fail for expected reason**

Run: `pytest tests/test_utils_extended.py -k resolve_playwright_headless -v`
Expected: FAIL due to missing function/signature.

- [ ] **Step 7: Commit test-only red phase**

```bash
git add tests/test_utils_extended.py
git commit -m "test: add failing playwright mode resolver coverage"
```

---

### Task 2: Implement resolver in utils.py and make tests pass

**Files:**
- Modify: `vvr_scraper/utils.py`
- Test: `tests/test_utils_extended.py`

- [ ] **Step 1: Implement minimal resolver function**

```python
# vvr_scraper/utils.py

def resolve_playwright_headless(cli_mode: str | None = None) -> bool:
    """
    Resolve Playwright headless mode.

    Precedence:
    1) cli_mode ('head' | 'headless')
    2) VVR_PLAYWRIGHT_MODE env ('head' | 'headless')
    3) default headless=True
    """
    if cli_mode == "head":
        return False
    if cli_mode == "headless":
        return True

    env_mode = (os.getenv("VVR_PLAYWRIGHT_MODE") or "").strip().lower()
    if env_mode == "head":
        return False
    if env_mode == "headless":
        return True

    return True
```

- [ ] **Step 2: Run resolver tests**

Run: `pytest tests/test_utils_extended.py -k resolve_playwright_headless -v`
Expected: PASS.

- [ ] **Step 3: Refactor (if needed) without changing behavior**

```python
# optional micro-refactor for readability
VALID_PLAYWRIGHT_MODES = {"head", "headless"}
```

- [ ] **Step 4: Re-run resolver tests after refactor**

Run: `pytest tests/test_utils_extended.py -k resolve_playwright_headless -v`
Expected: PASS.

- [ ] **Step 5: Commit implementation**

```bash
git add vvr_scraper/utils.py tests/test_utils_extended.py
git commit -m "feat: add centralized playwright headless mode resolver"
```

---

### Task 3: Add failing tests for CLI flags and parsing rules

**Files:**
- Modify: `tests/test_cli_unit.py`
- Test: `tests/test_cli_unit.py`

- [ ] **Step 1: Add failing parse test for `--head-playwright`**

```python
def test_head_playwright_flag(self):
    cli = self._parse(["ten-truyen", "--head-playwright"])
    assert cli.args.head_playwright is True
    assert cli.args.headless_playwright is False
```

- [ ] **Step 2: Add failing parse test for `--headless-playwright`**

```python
def test_headless_playwright_flag(self):
    cli = self._parse(["ten-truyen", "--headless-playwright"])
    assert cli.args.headless_playwright is True
    assert cli.args.head_playwright is False
```

- [ ] **Step 3: Add failing test for mutual exclusion**

```python
def test_playwright_head_flags_are_mutually_exclusive(self):
    with pytest.raises(SystemExit):
        self._parse(["ten-truyen", "--head-playwright", "--headless-playwright"])
```

- [ ] **Step 4: Run tests to verify red state**

Run: `pytest tests/test_cli_unit.py -k playwright -v`
Expected: FAIL because flags not defined yet.

- [ ] **Step 5: Commit test-only red phase**

```bash
git add tests/test_cli_unit.py
git commit -m "test: add failing CLI playwright mode flag coverage"
```

---

### Task 4: Implement CLI flags + mode propagation entrypoints

**Files:**
- Modify: `vvr_scraper/cli.py`
- Modify: `vvr_scraper/job_models.py`
- Modify: `vvr_scraper/job_runner.py`
- Modify: `vvr_scraper/web/__init__.py`
- Test: `tests/test_cli_unit.py`

- [ ] **Step 1: Add mutually-exclusive CLI flags**

```python
# vvr_scraper/cli.py inside _parse_arguments()
playwright_group = parser.add_mutually_exclusive_group()
playwright_group.add_argument("--head-playwright", action="store_true", help="Chạy Playwright ở chế độ có giao diện.")
playwright_group.add_argument(
    "--headless-playwright", action="store_true", help="Buộc Playwright chạy headless."
)
```

- [ ] **Step 2: Add small helper in CLI to compute explicit mode**

```python
# vvr_scraper/cli.py

def _cli_playwright_mode(self) -> str | None:
    if self.args.head_playwright:
        return "head"
    if self.args.headless_playwright:
        return "headless"
    return None
```

- [ ] **Step 3: Pass mode into run/web paths**

```python
# run command path
await run_manifest(self.args.ten_truyen[1], playwright_mode=self._cli_playwright_mode())

# web command path
await run_web_server(
    host=self.args.host,
    port=self.args.port,
    num_workers=self.args.workers,
    playwright_mode=self._cli_playwright_mode(),
)
```

- [ ] **Step 4: Extend models/functions minimally for propagation**

```python
# vvr_scraper/job_models.py
class ScrapePayload(BaseModel):
    ...
    playwright_mode: Literal["head", "headless"] | None = None
```

```python
# vvr_scraper/job_runner.py
async def run_manifest(file_path: str, playwright_mode: str | None = None):
    ...
    # when creating/dispatching crawl payload, preserve explicit mode
```

```python
# vvr_scraper/web/__init__.py
async def run_web_server(..., playwright_mode: str | None = None):
    if playwright_mode:
        os.environ["VVR_PLAYWRIGHT_MODE"] = playwright_mode
```

- [ ] **Step 5: Run CLI parser tests**

Run: `pytest tests/test_cli_unit.py -k "playwright or web_command_dispatch" -v`
Expected: PASS.

- [ ] **Step 6: Commit CLI propagation changes**

```bash
git add vvr_scraper/cli.py vvr_scraper/job_models.py vvr_scraper/job_runner.py vvr_scraper/web/__init__.py tests/test_cli_unit.py
git commit -m "feat: add CLI playwright mode flags with propagation"
```

---

### Task 5: Add failing tests for LnHako get_content retry

**Files:**
- Modify: `tests/test_sources.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Add failing test for retry-then-success**

```python
@pytest.mark.asyncio
async def test_lnhako_get_content_retries_on_transient_failure_then_succeeds(monkeypatch):
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    calls = {"count": 0}

    async def goto_side_effect(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("transient timeout")

    mock_page.goto = AsyncMock(side_effect=goto_side_effect)
    mock_page.wait_for_selector = AsyncMock(return_value=None)
    mock_page.close = AsyncMock()

    class MockLocator:
        def __init__(self, texts=None, images=None):
            self.all_inner_texts = AsyncMock(return_value=texts or [])
            self.all = AsyncMock(return_value=images or [])

    mock_page.locator.side_effect = lambda s: MockLocator(["Recovered para"]) if s == "#chapter-content p" else MockLocator(images=[])

    monkeypatch.setattr("vvr_scraper.sources.lnhako.asyncio.sleep", AsyncMock())

    source = LnHakoSource(browser=mock_browser)
    content = await source.get_content("https://ln.hako.vn/chapter/1")

    assert calls["count"] == 2
    assert [item.data for item in content if item.type == "text"] == ["Recovered para"]
```

- [ ] **Step 2: Add failing test for retry exhaustion**

```python
@pytest.mark.asyncio
async def test_lnhako_get_content_raises_after_retry_exhausted(monkeypatch):
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_page.goto = AsyncMock(side_effect=TimeoutError("always timeout"))
    mock_page.close = AsyncMock()

    monkeypatch.setattr("vvr_scraper.sources.lnhako.asyncio.sleep", AsyncMock())

    source = LnHakoSource(browser=mock_browser)
    with pytest.raises(TimeoutError):
        await source.get_content("https://ln.hako.vn/chapter/1")

    assert mock_page.goto.await_count == 3
```

- [ ] **Step 3: Run only the new tests (expect fail)**

Run: `pytest tests/test_sources.py -k "lnhako_get_content_retries or retry_exhausted" -v`
Expected: FAIL because retry not implemented yet.

- [ ] **Step 4: Commit test-only red phase**

```bash
git add tests/test_sources.py
git commit -m "test: add failing LnHako content retry coverage"
```

---

### Task 6: Implement LnHako retry loop and pass tests

**Files:**
- Modify: `vvr_scraper/sources/lnhako.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Add minimal retry loop around current fetch/extract block**

```python
# vvr_scraper/sources/lnhako.py
import asyncio

...

MAX_RETRIES = 3
BACKOFF_SECONDS = (2, 4)

async def get_content(self, chapter_url: str) -> list[ContentItem]:
    if not self.browser:
        raise RuntimeError("Browser instance required for LnHakoSource content extraction")

    page = await self.browser.new_page()
    try:
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                await page.goto(chapter_url, wait_until="networkidle", timeout=60000)
                try:
                    await page.wait_for_selector("#chapter-content", timeout=30000)
                except TimeoutError:
                    await page.wait_for_selector("#chapter-content p, #chapter-content img", timeout=30000)

                paragraphs = await page.locator("#chapter-content p").all_inner_texts()
                extracted_content = [ContentItem(type="text", data=p.strip()) for p in paragraphs if p.strip()]

                images = await page.locator("#chapter-content img").all()
                for img in images:
                    src = await img.get_attribute("src")
                    if src:
                        extracted_content.append(ContentItem(type="image", data=src))

                return extracted_content
            except TimeoutError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BACKOFF_SECONDS[attempt])
                    continue
                raise

        if last_exc:
            raise last_exc
        return []
    finally:
        await page.close()
```

- [ ] **Step 2: Run targeted LnHako tests**

Run: `pytest tests/test_sources.py -k "lnhako_get_content" -v`
Expected: PASS.

- [ ] **Step 3: Refactor minimally (deduplicate constants/naming)**

```python
# keep constants module-local and names clear
```

- [ ] **Step 4: Re-run targeted tests**

Run: `pytest tests/test_sources.py -k "lnhako_get_content" -v`
Expected: PASS.

- [ ] **Step 5: Commit retry implementation**

```bash
git add vvr_scraper/sources/lnhako.py tests/test_sources.py
git commit -m "feat: add retry for LnHako chapter content extraction"
```

---

### Task 7: Integrate resolver at all Playwright launch sites

**Files:**
- Modify: `vvr_scraper/cli.py`
- Modify: `vvr_scraper/job_runner.py`
- Modify: `vvr_scraper/web/routes/download.py`
- Modify: `vvr_scraper/web/routes/library.py`
- Modify: `vvr_scraper/tao_so_do_cay.py`
- Modify: `vvr_scraper/video_renderer.py`
- Test: `tests/test_cli_unit.py`

- [ ] **Step 1: Replace direct launch in CLI path**

```python
# vvr_scraper/cli.py
from .utils import resolve_playwright_headless

...
headless = resolve_playwright_headless(cli_mode=self._cli_playwright_mode())
browser = await p.chromium.launch(headless=headless)
```

- [ ] **Step 2: Replace direct launch in job runner**

```python
# vvr_scraper/job_runner.py
from vvr_scraper.utils import resolve_playwright_headless

...
headless = resolve_playwright_headless(cli_mode=payload.playwright_mode)
browser = await p.chromium.launch(headless=headless)
```

- [ ] **Step 3: Replace direct launch in web routes and chapter-tree fallback**

```python
# web/routes/download.py and web/routes/library.py
from ...utils import resolve_playwright_headless
...
browser = await p.chromium.launch(headless=resolve_playwright_headless())
```

```python
# tao_so_do_cay.py
from .utils import HEADERS, resolve_playwright_headless
...
_browser = await p.chromium.launch(headless=resolve_playwright_headless())
```

- [ ] **Step 4: Replace direct launch in video renderer**

```python
# video_renderer.py
from .utils import resolve_playwright_headless
...
browser = await p.chromium.launch(headless=resolve_playwright_headless())
```

- [ ] **Step 5: Run focused integration/unit tests**

Run:
- `pytest tests/test_cli_unit.py -v`
- `pytest tests/test_sources.py -k "lnhako_get_content" -v`

Expected: PASS.

- [ ] **Step 6: Commit launch-site integration**

```bash
git add vvr_scraper/cli.py vvr_scraper/job_runner.py vvr_scraper/web/routes/download.py vvr_scraper/web/routes/library.py vvr_scraper/tao_so_do_cay.py vvr_scraper/video_renderer.py tests/test_cli_unit.py

git commit -m "feat: apply centralized playwright headless resolution across launch paths"
```

---

### Task 8: Final verification and cleanup

**Files:**
- Modify (if needed): any from prior tasks
- Test: full targeted suite

- [ ] **Step 1: Run lint on changed files**

Run: `ruff check vvr_scraper tests`
Expected: no new lint errors in touched files.

- [ ] **Step 2: Run targeted test suite for this feature**

Run:
- `pytest tests/test_utils_extended.py -k resolve_playwright_headless -v`
- `pytest tests/test_cli_unit.py -k playwright -v`
- `pytest tests/test_sources.py -k "lnhako_get_content" -v`

Expected: all PASS.

- [ ] **Step 3: Run broader regression slice**

Run: `pytest tests/test_sources.py tests/test_cli_unit.py tests/test_utils_extended.py -v`
Expected: PASS.

- [ ] **Step 4: Final commit (if verification fixes needed)**

```bash
git add -A
git commit -m "chore: finalize LnHako retry and Playwright mode controls"
```

---

## Spec Coverage Check

- Retry only on `LnHakoSource.get_content()` ✅ Tasks 5-6
- Add both CLI flags and keep them mutually exclusive ✅ Tasks 3-4
- Add env persistent config (`VVR_PLAYWRIGHT_MODE`) ✅ Tasks 1-2
- Enforce precedence CLI > ENV > default headless ✅ Tasks 1-2 + 4
- Apply consistently to all launch/fallback Playwright paths ✅ Task 7

## Placeholder Scan

- No `TODO/TBD` placeholders in actionable steps.
- All tasks include exact file paths, concrete tests, and run commands.

## Type/Interface Consistency

- Resolver signature used consistently as `resolve_playwright_headless(cli_mode: str | None = None)`.
- Mode values consistent across plan: `"head" | "headless"`.
