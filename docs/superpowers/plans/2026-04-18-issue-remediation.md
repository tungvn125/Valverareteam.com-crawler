# Issue Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the currently measurable quality issues and the highest-value technical weaknesses in orchestration and API error handling without expanding into a full architectural rewrite.

**Architecture:** The implementation proceeds in two phases. First, stabilize the codebase by fixing current lint failures, standardizing API error behavior, and eliminating or isolating visible runtime warnings. Second, add regression coverage and apply only the smallest refactors needed to improve testability and reduce orchestration friction in `job_runner.py`, `web/routes/api.py`, and `web/routes/correction.py`.

**Tech Stack:** Python 3.12+, FastAPI, pytest, pytest-asyncio, Ruff, httpx, Playwright, aiosqlite

---

## File Map

### Existing files expected to change

- `demo/vvr_config_pydantic.py`
  Purpose: demo-only config example currently failing Ruff.
- `vvr_scraper/web/routes/api.py`
  Purpose: API route handlers; currently contains inconsistent error response patterns.
- `vvr_scraper/job_runner.py`
  Purpose: orchestration for crawl/render/server jobs; candidate for small helper extraction and more direct tests.
- `vvr_scraper/web/routes/correction.py`
  Purpose: correction endpoints; needs stronger tests and possibly small helper extraction.
- `tests/test_web_api.py`
  Purpose: FastAPI API behavior tests; expand with API error-handling assertions.
- `tests/test_job_runner_unit.py`
  Purpose: unit tests for orchestration behavior; expand for helper-driven and error-path behavior.
- `tests/test_correction.py`
  Purpose: correction route and helper coverage; expand for file/path/data error branches.
- Potentially `tests/test_video_renderer.py` or another existing test file if warning reduction requires test fixture cleanup rather than product-code changes.

### Existing files that may be read during implementation

- `docs/superpowers/specs/2026-04-18-issue-remediation-design.md`
- `vvr_scraper/web/state.py`
- `vvr_scraper/web/__init__.py`
- `vvr_scraper/web/routes/download.py`

### Files not to broaden in this plan

- `vvr_scraper/cli.py`
- `vvr_scraper/exporter.py`

These large files remain outside the scoped remediation except for indirect compatibility checks.

## Task 1: Baseline And Scope Lock

**Files:**
- Read: `docs/superpowers/specs/2026-04-18-issue-remediation-design.md`
- Read: `demo/vvr_config_pydantic.py`
- Read: `vvr_scraper/web/routes/api.py`
- Read: `vvr_scraper/job_runner.py`
- Read: `vvr_scraper/web/routes/correction.py`
- Test: full suite and targeted commands

- [ ] **Step 1: Capture current failing/fragile baseline**

Run:

```bash
ruff check .
pytest
pytest tests/test_web_api.py tests/test_job_runner_unit.py tests/test_correction.py -v
```

Expected:

- Ruff reports the known current failures.
- Pytest passes or exposes the currently known warning set.
- Targeted tests establish the current behavior around API, job runner, and correction flows.

- [ ] **Step 2: Record the exact in-scope failures before changing code**

Create a short working note locally while implementing with this checklist:

```text
- Ruff failures still present in demo/vvr_config_pydantic.py?
- API routes still returning mixed error styles?
- Which warnings are product-code issues vs test-harness/dependency issues?
- Which uncovered branches in api/job_runner/correction are the highest risk?
```

Expected:

- The worker can point to concrete failures being addressed and avoid scope creep.

- [ ] **Step 3: Do not change architecture outside the scoped modules**

Guardrail for the rest of the plan:

```text
Allowed: local helper extraction, route-level cleanup, narrow state access wrappers, targeted tests.
Not allowed: full web DI rewrite, full job-system redesign, exporter/CLI decomposition.
```

Expected:

- Later tasks stay aligned with the approved spec.

## Task 2: Make Ruff Pass

**Files:**
- Modify: `demo/vvr_config_pydantic.py`
- Test: Ruff only

- [ ] **Step 1: Write the failing quality-gate check**

Run:

```bash
ruff check demo/vvr_config_pydantic.py
```

Expected: FAIL with import ordering, unused imports, deprecated typing syntax, and whitespace issues.

- [ ] **Step 2: Apply the minimal cleanup required for Ruff**

Update the file to use sorted imports, remove unused imports, modernize typing, and remove trailing whitespace. The resulting import/header shape should look like this:

```python
"""
Example Pydantic settings module.
This provides type validation and fail-fast environment variable loading.
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(None, alias="VVR_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="VVR_BASE_URL")
    elevenlabs_api_key: str | None = Field(None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("ywBZEqUhld86Jeajq94o", alias="VVR_NARRATOR_VOICE_ID")
    web_host: str = Field("127.0.0.1", alias="WEB_HOST")
    web_port: int = Field(8000, alias="WEB_PORT")
    opds_password: str = Field("password", alias="OPDS_PASSWORD")
    freesound_client_id: str | None = Field(None, alias="FREESOUND_CLIENT_ID")
    freesound_client_secret: str | None = Field(None, alias="FREESOUND_CLIENT_SECRET")
    debug: bool = Field(False, alias="VVR_DEBUG")
```

If the file contains additional fields, keep them and apply the same cleanup style consistently.

- [ ] **Step 3: Re-run Ruff on the file**

Run:

```bash
ruff check demo/vvr_config_pydantic.py
```

Expected: PASS.

- [ ] **Step 4: Re-run Ruff on the full repo**

Run:

```bash
ruff check .
```

Expected: PASS, or expose only new in-scope failures discovered after the first file is cleaned.

- [ ] **Step 5: Commit**

```bash
git add demo/vvr_config_pydantic.py
git commit -m "chore(lint): fix demo config ruff issues"
```

## Task 3: Standardize API Error Handling

**Files:**
- Modify: `vvr_scraper/web/routes/api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Add failing tests for inconsistent error behavior**

Add tests covering these cases in `tests/test_web_api.py`:

```python
def test_freesound_callback_returns_http_500_on_exchange_failure(client):
    with patch("vvr_scraper.web.routes.api.FreesoundManager") as MockManager:
        instance = MockManager.return_value
        instance.exchange_code = AsyncMock(side_effect=RuntimeError("boom"))

        response = client.post("/api/freesound/callback", json={"code": "bad-code"})

    assert response.status_code == 500
    assert response.json()["detail"] == "boom"


def test_story_info_returns_http_500_on_internal_error(client):
    with patch("vvr_scraper.web.routes.api.lay_thong_tin_truyen", new_callable=AsyncMock) as mock_info:
        mock_info.side_effect = RuntimeError("story failed")

        response = client.get("/api/story_info", params={"slug": "test-story"})

    assert response.status_code == 500
    assert response.json()["detail"] == "story failed"
```

If direct patch points differ after inspection, adapt the import targets but keep the assertions and intent the same.

- [ ] **Step 2: Run the targeted tests to verify failure**

Run:

```bash
pytest tests/test_web_api.py -k "freesound_callback or story_info_returns_http_500" -v
```

Expected: FAIL because the current routes return inconsistent payloads or non-HTTPException error behavior.

- [ ] **Step 3: Implement consistent error reporting in `api.py`**

Update route handlers so internal exceptions are logged and converted to `HTTPException(status_code=500, detail=str(e))` where appropriate. The Freesound callback path should move from tuple-style returns to FastAPI-native exceptions.

The pattern should look like this:

```python
from fastapi import HTTPException


@router.post("/api/freesound/callback", summary="Freesound OAuth Callback")
async def freesound_callback(req: FreesoundCallbackRequest):
    try:
        from ...freesound_manager import FreesoundManager

        fs_manager = FreesoundManager()
        await fs_manager.exchange_code(req.code)
        return {"status": "success", "message": "Freesound authentication successful."}
    except Exception as e:
        logger.error(f"Error exchanging Freesound code: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
```

Apply the same style to other internal-error cases in this module where the current behavior is inconsistent.

- [ ] **Step 4: Run the targeted tests again**

Run:

```bash
pytest tests/test_web_api.py -k "freesound_callback or story_info_returns_http_500" -v
```

Expected: PASS.

- [ ] **Step 5: Run the broader API test file**

Run:

```bash
pytest tests/test_web_api.py -v
```

Expected: PASS with no regressions in existing endpoint tests.

- [ ] **Step 6: Commit**

```bash
git add vvr_scraper/web/routes/api.py tests/test_web_api.py
git commit -m "fix(api): standardize internal error handling"
```

## Task 4: Reduce Visible Runtime Warnings

**Files:**
- Modify: the smallest necessary product or test files identified by the baseline run
- Test: targeted warning-producing tests, then full `pytest`

- [ ] **Step 1: Isolate the warning-producing tests**

Run:

```bash
pytest tests/test_properties.py::test_sanitize_filename_properties tests/test_video_renderer.py::TestVideoRenderer::test_render_logic_flow -v
```

Expected: reproduce the currently visible warning cases or confirm they have shifted.

- [ ] **Step 2: Decide whether each warning is product-code, test-harness, or dependency-driven**

Use this decision matrix:

```text
- Product-code issue: fix in product code.
- Test fixture or mock issue: fix in the test.
- Dependency deprecation with no safe local fix: isolate and document, do not broaden scope.
```

Expected:

- Each warning has a clear owner before any code is changed.

- [ ] **Step 3: Apply the smallest fix for the reproduced warnings**

Examples of acceptable fixes:

```python
# If a mocked coroutine is created but not awaited in a test, replace it with an awaited AsyncMock path.
mock_sleep = AsyncMock()
with patch("module.asyncio.sleep", mock_sleep):
    ...

# If a background server thread in a test triggers avoidable noise, make the test own startup/shutdown explicitly.
thread.join(timeout=...)  # or ensure server object is stopped before test exit
```

Do not change dependency versions or widen the scope into infrastructure cleanup.

- [ ] **Step 4: Re-run the isolated warning tests**

Run:

```bash
pytest tests/test_properties.py::test_sanitize_filename_properties tests/test_video_renderer.py::TestVideoRenderer::test_render_logic_flow -v
```

Expected: warnings are gone or reduced to an explicitly understood dependency-driven residual set.

- [ ] **Step 5: Re-run the full test suite**

Run:

```bash
pytest
```

Expected: PASS, with the warning set improved and understood.

- [ ] **Step 6: Commit**

```bash
git add tests test_video_renderer.py vvr_scraper
git commit -m "fix(testing): reduce visible runtime warnings"
```

Note: adjust the final `git add` paths to the exact files changed. Do not add unrelated workspace files.

## Task 5: Strengthen `job_runner.py` Regression Coverage

**Files:**
- Modify: `tests/test_job_runner_unit.py`
- Modify: `vvr_scraper/job_runner.py`

- [ ] **Step 1: Add a failing test for crawl orchestration progress/update behavior**

Add a test like this to `tests/test_job_runner_unit.py`:

```python
@pytest.mark.asyncio
async def test_execute_crawl_job_updates_progress_and_metadata(tmp_path):
    mock_db = AsyncMock()
    payload = ScrapePayload(slug="story-slug", formats=["EPUB"], output_folder=str(tmp_path / "out"))

    with patch("vvr_scraper.job_runner.resolve_story_url", new=AsyncMock(return_value="https://valvrareteam.net/truyen/story-slug")), \
         patch("vvr_scraper.job_runner.load_session", return_value=None), \
         patch("vvr_scraper.job_runner.lay_thong_tin_truyen", new=AsyncMock(return_value=SimpleNamespace(
             title="Story",
             author="Author",
             description="Desc",
             slug="story-slug",
             cover_url=None,
             cover_path=None,
             genres=["Action"],
         ))), \
         patch("vvr_scraper.job_runner.get_chapter_tree_list", new=AsyncMock(return_value=[
             {"volume": "Volume 1", "chapters": [{"title": "Ch 1", "url": "/c1"}]}
         ])), \
         patch("vvr_scraper.job_runner.scrape_chapters", new=AsyncMock(return_value={
             "https://valvrareteam.net/c1": [{"type": "text", "data": "Hello"}]
         })), \
         patch("vvr_scraper.job_runner.tao_file_epub", new=AsyncMock()):
        await execute_crawl_job(payload, "job-1", mock_db)

    assert mock_db.update_job_status.await_count >= 2
    mock_db.upsert_novel.assert_awaited()
    mock_db.update_library_metadata.assert_awaited()
```

- [ ] **Step 2: Run the new test to verify failure or insufficient behavior**

Run:

```bash
pytest tests/test_job_runner_unit.py::test_execute_crawl_job_updates_progress_and_metadata -v
```

Expected: FAIL initially, or expose awkward patch/setup points that justify helper extraction.

- [ ] **Step 3: Extract the smallest helpers needed in `job_runner.py`**

Refactor only enough to make orchestration boundaries clear. The helper shapes should be simple and local, for example:

```python
def _chapter_full_url(chapter_url: str) -> str:
    return chapter_url if chapter_url.startswith("http") else f"{BASE_URL}{chapter_url}"


def _build_export_structures(chapter_tree, scraped):
    full_flat = []
    full_structure = []
    for volume in chapter_tree:
        volume_chapters = []
        for chapter in volume["chapters"]:
            full_url = _chapter_full_url(chapter["url"])
            if full_url in scraped:
                volume_chapters.append({"title": chapter["title"], "content": scraped[full_url]})
                full_flat.extend(scraped[full_url])
        if volume_chapters:
            full_structure.append({"volume": volume["volume"], "chapters": volume_chapters})
    return full_flat, full_structure
```

Keep the existing top-level behavior intact.

- [ ] **Step 4: Re-run the new test**

Run:

```bash
pytest tests/test_job_runner_unit.py::test_execute_crawl_job_updates_progress_and_metadata -v
```

Expected: PASS.

- [ ] **Step 5: Add one more focused error-path test**

Add a test for unresolved story URLs:

```python
@pytest.mark.asyncio
async def test_execute_crawl_job_raises_when_story_url_cannot_be_resolved(tmp_path):
    payload = ScrapePayload(slug="missing-story", formats=["EPUB"], output_folder=str(tmp_path / "out"))

    with patch("vvr_scraper.job_runner.resolve_story_url", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="Could not resolve story URL"):
            await execute_crawl_job(payload, "job-2", AsyncMock())
```

- [ ] **Step 6: Run the focused job-runner test file**

Run:

```bash
pytest tests/test_job_runner_unit.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add vvr_scraper/job_runner.py tests/test_job_runner_unit.py
git commit -m "test(job-runner): cover crawl orchestration paths"
```

## Task 6: Strengthen `correction.py` Regression Coverage

**Files:**
- Modify: `tests/test_correction.py`
- Modify: `vvr_scraper/web/routes/correction.py` only if small extraction is needed for testability

- [ ] **Step 1: Add a failing test for correction save error handling**

Add a test like this:

```python
@pytest.mark.asyncio
async def test_save_corrections_returns_404_when_script_missing(tmp_path):
    from fastapi import HTTPException

    with patch("vvr_scraper.web.routes.correction._async_get_output_dir", new=AsyncMock(return_value=tmp_path)):
        with pytest.raises(HTTPException, match="Script file not found"):
            await save_corrections("story-slug", 99, CorrectionRequest(segments=[]))
```

Adapt the payload shape to the actual request model if `segments=[]` is insufficient.

- [ ] **Step 2: Run the new test to verify failure or reveal the current edge behavior**

Run:

```bash
pytest tests/test_correction.py -k "save_corrections_returns_404_when_script_missing" -v
```

Expected: FAIL initially or expose untested branch behavior.

- [ ] **Step 3: Add a failing test for character update validation or missing character path**

Add a second targeted test such as:

```python
@pytest.mark.asyncio
async def test_update_character_returns_404_when_character_missing():
    from fastapi import HTTPException

    mock_db = AsyncMock()
    mock_db.get_character_profile = AsyncMock(return_value=None)

    with patch("vvr_scraper.web.routes.correction.get_db_manager", return_value=mock_db):
        with pytest.raises(HTTPException, match="Character not found"):
            await update_character("story-slug", "Unknown", CharacterUpdateRequest(voice_id="v1"))
```

If the route obtains the DB differently, patch the actual dependency point after inspection.

- [ ] **Step 4: Run the two new correction tests**

Run:

```bash
pytest tests/test_correction.py -k "save_corrections_returns_404_when_script_missing or update_character_returns_404_when_character_missing" -v
```

Expected: FAIL initially or reveal missing assertions.

- [ ] **Step 5: Implement the minimal route or helper cleanup needed**

If needed, extract small local helpers in `vvr_scraper/web/routes/correction.py` to isolate file lookup or missing-resource behavior. The goal is to make branches explicit, for example:

```python
def _find_script_path(files: list[dict], chapter_idx: int) -> Path | None:
    for item in files:
        if item.get("chapter_idx") == chapter_idx:
            return Path(item["path"])
    return None
```

Keep the module in one file and avoid broad decomposition.

- [ ] **Step 6: Re-run the targeted correction tests**

Run:

```bash
pytest tests/test_correction.py -k "save_corrections_returns_404_when_script_missing or update_character_returns_404_when_character_missing" -v
```

Expected: PASS.

- [ ] **Step 7: Run the full correction test file**

Run:

```bash
pytest tests/test_correction.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add vvr_scraper/web/routes/correction.py tests/test_correction.py
git commit -m "test(correction): cover missing-resource branches"
```

## Task 7: Narrow The Most Fragile Global-State Access

**Files:**
- Modify: `vvr_scraper/web/state.py`
- Modify: one or more direct state consumers such as `vvr_scraper/web/routes/api.py` or `vvr_scraper/web/routes/jobs.py`
- Test: relevant web tests

- [ ] **Step 1: Identify one direct-access pattern to narrow**

Target only a small, high-friction pattern such as direct mutation of task globals or repeated direct access to broadcaster state.

The chosen pattern should satisfy all of these:

```text
- Touched by routes or runtime logic in current scope.
- Easy to wrap without changing public behavior.
- Improves testability or reduces branching ambiguity.
```

- [ ] **Step 2: Add a failing test that locks the desired behavior**

Example shape, adapted to the actual access point chosen:

```python
@pytest.mark.asyncio
async def test_download_manager_add_task_broadcasts_queue_status():
    dm = DownloadManager()
    req = DownloadRequest(slug="test-novel")

    with patch("vvr_scraper.web.state.manager") as mock_manager:
        mock_manager.broadcast = AsyncMock()
        await dm.add_task(req, "task-123")

    mock_manager.broadcast.assert_awaited_once_with(
        {"type": "status", "task_id": "task-123", "status": "In Queue..."}
    )
```

If this behavior is already covered, choose a neighboring fragile access pattern that is not.

- [ ] **Step 3: Run the focused test to verify the current seam is weak or implicit**

Run:

```bash
pytest tests/test_web_api.py -k "download_manager_add_task_broadcasts_queue_status" -v
```

Expected: FAIL if the seam is not explicit enough, or PASS but still justify introducing a narrower helper only if it removes duplicated global touching in in-scope modules.

- [ ] **Step 4: Add the smallest wrapper/helper in `web/state.py` or the consuming route**

Example shape:

```python
async def broadcast_task_status(task_id: str, status: str) -> None:
    await manager.broadcast({"type": "status", "task_id": task_id, "status": status})


async def add_task(self, req, task_id: str):
    await broadcast_task_status(task_id, "In Queue...")
    await self.queue.put((req, task_id))
```

Do this only if it simplifies one or more in-scope consumers. Do not widen the abstraction beyond what is needed.

- [ ] **Step 5: Re-run the focused test and related web tests**

Run:

```bash
pytest tests/test_web_api.py -k "DownloadManager or ConnectionManager or APIEndpoints" -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add vvr_scraper/web/state.py vvr_scraper/web/routes/api.py tests/test_web_api.py
git commit -m "refactor(web): narrow fragile state access"
```

Adjust the staged files to the actual changed set.

## Task 8: Full Verification And Final Audit

**Files:**
- Verify all modified files from prior tasks

- [ ] **Step 1: Run Ruff on the full repo**

Run:

```bash
ruff check .
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
pytest
```

Expected: PASS.

- [ ] **Step 3: Re-run the highest-risk focused tests for confidence**

Run:

```bash
pytest tests/test_web_api.py tests/test_job_runner_unit.py tests/test_correction.py -v
```

Expected: PASS.

- [ ] **Step 4: Compare the result to the spec completion criteria**

Use this checklist:

```text
- Ruff passes.
- Pytest passes.
- Visible runtime warnings are fixed or explicitly understood.
- API error handling is more consistent.
- job_runner/api/correction have stronger regression safety.
- Structural changes stayed targeted and did not become a redesign.
```

Expected:

- Any remaining gap is visible before the work is claimed complete.

- [ ] **Step 5: Commit final reconciliation changes if any remain**

```bash
git add <exact modified files>
git commit -m "chore: finish issue remediation pass"
```

Only create this final commit if there are remaining unstaged or uncommitted remediation changes after the task-level commits.

## Self-Review

Spec coverage check:

- Quality gate: covered by Task 2 and Task 8.
- Runtime correctness and API consistency: covered by Task 3 and Task 4.
- Regression safety in `job_runner.py`, `api.py`, and `correction.py`: covered by Tasks 5, 6, and 8.
- Targeted architecture fixes without redesign: covered by Tasks 5 and 7 with explicit non-goals.
- Repo-level cleanup exclusion: preserved by scope and not assigned to any task.

Placeholder scan:

- No `TODO`, `TBD`, or deferred placeholders remain.
- Any adaptive wording is limited to necessary patch targets discovered during implementation and does not remove the concrete expected behavior.

Type consistency check:

- The plan consistently refers to `ScrapePayload`, `HTTPException`, and the existing test files.
- Helper examples use local names and are not depended on by later tasks as hard requirements unless the implementing worker chooses that exact shape.
