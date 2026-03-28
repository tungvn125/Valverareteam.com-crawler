# Audio-Drama Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an AI-powered multi-character audio-drama generator that parses chapters using Google Gemini and generates multi-voice audio using the local VieNeu TTS engine.

**Architecture:** A Hybrid Cloud Pipeline. Google Gemini identifies characters and dialogue from raw text, returning a structured JSON script. This script is then processed by a local worker that assigns unique VieNeu voices to characters, persists these mappings in SQLite for consistency, and generates a concatenated multi-track audiobook.

**Tech Stack:** Python 3.10+, google-generativeai, vieneu, aiosqlite, numpy, loguru.

---

### Task 1: Environment & Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add missing dependencies**

Update `pyproject.toml`:
```toml
dependencies = [
    # ... existing ...
    "aiosqlite>=0.19.0",
    "google-generativeai>=0.4.0",
]
```

- [ ] **Step 2: Sync environment**

Run: `uv sync` or `pip install aiosqlite google-generativeai`

- [ ] **Step 3: Verify installation**

Run: `python -c "import aiosqlite, google.generativeai; print('Success')"`
Expected: Success

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add aiosqlite and google-generativeai dependencies"
```

### Task 2: Database Schema & Persistence

**Files:**
- Modify: `vvr_scraper/db.py`
- Create: `tests/test_db_audio.py`

- [ ] **Step 1: Write failing test for character voices**

Create `tests/test_db_audio.py`:
```python
import pytest
from vvr_scraper.db import DatabaseManager

@pytest.mark.asyncio
async def test_character_voice_persistence(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    await db.init_db()
    
    await db.save_character_voice("story1", "Character A", "Hung")
    voice = await db.get_character_voice("story1", "Character A")
    assert voice == "Hung"
    
    assert await db.get_character_voice("story1", "Unknown") is None
```

- [ ] **Step 2: Implement `character_voices` table and methods**

Modify `vvr_scraper/db.py`:
- Update `init_db()` with `CREATE TABLE IF NOT EXISTS character_voices (story_id TEXT, character_name TEXT, voice_name TEXT, PRIMARY KEY (story_id, character_name))`.
- Add `get_character_voice(story_id, character_name)` and `save_character_voice(story_id, character_name, voice_name)`.

- [ ] **Step 3: Run test and verify it passes**

Run: `pytest tests/test_db_audio.py`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/db.py tests/test_db_audio.py
git commit -m "feat: implement character_voices table and DB methods"
```

### Task 3: Gemini Parsing & Voice Management

**Files:**
- Create: `vvr_scraper/audio_drama.py`
- Create: `tests/test_audio_drama.py`

- [ ] **Step 1: Implement `GeminiParser`**

In `vvr_scraper/audio_drama.py`:
- Configure `genai`.
- Implement `parse_chapter(text)` returning `List[Dict[str, str]]`.
- Use `gemini-1.5-flash` with a system prompt for JSON output.

- [ ] **Step 2: Implement `VoiceManager`**

In `vvr_scraper/audio_drama.py`:
- `VoiceManager(db, story_id)`
- `get_voice(character_name)`: Uses DB, or assigns a random voice from pool if not found.
- Ensure "narrator" is always "Tuyen".

- [ ] **Step 3: Write tests for Parser and VoiceManager**

Create `tests/test_audio_drama.py`:
- Mock `genai` to test `GeminiParser`.
- Mock `DatabaseManager` to test `VoiceManager` (persistence and narrator isolation).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_audio_drama.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/audio_drama.py tests/test_audio_drama.py
git commit -m "feat: implement GeminiParser and VoiceManager"
```

### Task 4: Audio Drama Orchestration

**Files:**
- Modify: `vvr_scraper/exporter.py`

- [ ] **Step 1: Implement `tao_file_audiodrama`**

Modify `vvr_scraper/exporter.py`:
```python
async def tao_file_audiodrama(content_list, filename, story_id, db_manager, title="Chương truyện"):
    # 0. Extract text from content_list (List[ContentItem])
    full_text = "\n".join([item.data for item in content_list if item.type == "text"])
    
    # 1. Parse or load cached JSON script from <filename>.script.json
    # 2. Iterate through script, get voice via VoiceManager
    # 3. Call Vieneu.infer() for each segment (via asyncio.to_thread)
    # 4. Concatenate segments with numpy
    # 5. Save output, fallback to tao_file_mp3 on error
```

- [ ] **Step 2: Add JSON script checkpointing**

Save the parsed script to `<filename>.script.json` before starting TTS.

- [ ] **Step 3: Test orchestration with Mocks**

Verify the flow in `tests/test_exporter_audio.py` using mocks for Gemini and Vieneu.

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/exporter.py
git commit -m "feat: implement tao_file_audiodrama with checkpointing"
```

### Task 5: Integration & UI Support

**Files:**
- Modify: `vvr_scraper/cli.py`
- Modify: `vvr_scraper/web.py`

- [ ] **Step 1: Update CLI to support `AD-MP3` format**

In `cli.py`:
- Add `AD-MP3` to available formats.
- Update `_write_to_formats` to call `tao_file_audiodrama`.

- [ ] **Step 2: Update Web UI DownloadManager**

In `web.py`:
- Support the `AD-MP3` type in the download loop.
- Ensure `GEMINI_API_KEY` is loaded from environment.

- [ ] **Step 3: Commit**

```bash
git add vvr_scraper/cli.py vvr_scraper/web.py
git commit -m "feat: integrate Audio-Drama (AD-MP3) into CLI and Web UI"
```
