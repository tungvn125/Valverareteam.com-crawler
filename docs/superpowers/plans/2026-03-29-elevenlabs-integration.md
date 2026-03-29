# ElevenLabs Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heavy local `vieneu` TTS engine with the `elevenlabs` cloud API for audiobook and audio drama generation.

**Architecture:** Use the `elevenlabs` official Python SDK. `VoiceManager` will dynamically fetch voices from the API. The exporter functions will call the ElevenLabs API for each chunk of text and concatenate the returned MP3 streams using `pydub.AudioSegment`.

**Tech Stack:** Python 3.10+, `elevenlabs`, `pydub`, `pytest`.

---

### Task 1: Update Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `vvr_scraper.egg-info/requires.txt` (via uv sync)

- [ ] **Step 1: Update pyproject.toml**

```toml
# Update audio extra in pyproject.toml
# Remove 'vieneu', 'numpy'. Add 'elevenlabs'. Keep 'pydub>=0.25.1'.
# Edit pyproject.toml (around line 36)
[project.optional-dependencies]
audio = ["elevenlabs>=1.0.0", "pydub>=0.25.1"]
```

- [ ] **Step 2: Sync lockfile and reinstall dependencies**

Run: `uv pip install -e ".[audio]"`
Expected: Installs elevenlabs and removes/ignores vieneu.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: replace vieneu with elevenlabs dependency"
```

---

### Task 2: Update VoiceManager

**Files:**
- Modify: `vvr_scraper/audio_drama.py`
- Modify: `tests/test_audio_drama.py`

- [ ] **Step 1: Update VoiceManager Implementation**

```python
# Replace VoiceManager class in vvr_scraper/audio_drama.py
class VoiceManager:
    NARRATOR_VOICE_ID = "EXAVITQu4vr4xnSDxMaL" # Rachel or any default

    def __init__(self, db, story_id: str):
        self.db = db
        self.story_id = story_id
        self._voice_cache = {}
        self._initialized = False
        self._lock = __import__('asyncio').Lock()
        self._available_voices = []

    async def _init_cache(self):
        if not self._initialized:
            if hasattr(self.db, 'get_all_story_voices'):
                db_voices = await self.db.get_all_story_voices(self.story_id)
                self._voice_cache.update(db_voices)
            
            # Fetch ElevenLabs voices
            import os
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                from loguru import logger
                logger.warning("ELEVENLABS_API_KEY missing, using fallback empty voice list")
                self._available_voices = []
            else:
                from elevenlabs.client import ElevenLabs
                import asyncio
                client = ElevenLabs(api_key=api_key)
                # Fetch voices blockingly inside thread to avoid async loop issues
                def fetch_voices():
                    return client.voices.get_all().voices
                voices = await asyncio.to_thread(fetch_voices)
                self._available_voices = [v.voice_id for v in voices]

            self._initialized = True

    async def get_voice(self, character_name: str, gender: str = "unknown") -> str:
        if not character_name:
            return self.NARRATOR_VOICE_ID
            
        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.NARRATOR_VOICE_ID

        async with self._lock:
            await self._init_cache()
            
            if char_normalized in self._voice_cache:
                return self._voice_cache[char_normalized]
            
            import random
            assigned_voice = self.NARRATOR_VOICE_ID
            if self._available_voices:
                assigned_voice = random.choice(self._available_voices)

            self._voice_cache[char_normalized] = assigned_voice
            if hasattr(self.db, 'save_story_voice'):
                await self.db.save_story_voice(self.story_id, char_normalized, assigned_voice)
                
            return assigned_voice
```

- [ ] **Step 2: Update VoiceManager Tests**

```python
# Update tests/test_audio_drama.py (tests for VoiceManager)
# Replace existing test_voice_manager_*
@pytest.mark.asyncio
async def test_voice_manager_narrator():
    from vvr_scraper.audio_drama import VoiceManager
    mock_db = MagicMock()
    vm = VoiceManager(mock_db, "story_1")
    assert await vm.get_voice("narrator") == VoiceManager.NARRATOR_VOICE_ID
    assert await vm.get_voice("") == VoiceManager.NARRATOR_VOICE_ID
    assert await vm.get_voice("Narrator") == VoiceManager.NARRATOR_VOICE_ID

@pytest.mark.asyncio
async def test_voice_manager_fallback():
    from vvr_scraper.audio_drama import VoiceManager
    import os
    if "ELEVENLABS_API_KEY" in os.environ:
        del os.environ["ELEVENLABS_API_KEY"]
    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    mock_db.save_story_voice = AsyncMock()
    vm = VoiceManager(mock_db, "story_1")
    
    voice = await vm.get_voice("Vinh", "male")
    assert voice == VoiceManager.NARRATOR_VOICE_ID # Fallback if no API key/voices
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_audio_drama.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/audio_drama.py tests/test_audio_drama.py
git commit -m "feat: update VoiceManager to use ElevenLabs"
```

---

### Task 3: Update Exporter Functions

**Files:**
- Modify: `vvr_scraper/exporter.py`
- Modify: `tests/test_exporter_audio.py`

- [ ] **Step 1: Update tao_file_mp3 in exporter.py**

```python
# In vvr_scraper/exporter.py, rewrite `tao_file_mp3`:
async def tao_file_mp3(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """AI-Powered Audiobook generation using ElevenLabs with chunked processing."""
    import os
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        logger.error("ELEVENLABS_API_KEY not found. Cannot generate MP3.")
        return

    try:
        from elevenlabs.client import ElevenLabs
        import pydub
        import io
    except ImportError:
        logger.error("elevenlabs or pydub not found. Please run 'uv pip install vvr-scraper[audio]'.")
        return

    logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng ElevenLabs AI)")
    
    chunks = [title]
    for item in _normalize_content_list(content_list):
        if item.type == 'text':
            text = item.data.strip()
            if text:
                if len(text) > 2000:
                    subchunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
                    chunks.extend(subchunks)
                else:
                    chunks.append(text)

    try:
        def run_tts_chunked():
            client = ElevenLabs(api_key=api_key)
            audio_segments = []
            
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                logger.debug(f"Synthesizing chunk {i+1}/{total_chunks}...")
                audio_stream = client.generate(text=chunk, voice="EXAVITQu4vr4xnSDxMaL", model="eleven_multilingual_v2")
                # Consume generator into bytes
                audio_bytes = b"".join(list(audio_stream))
                segment = pydub.AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                audio_segments.append(segment)
            
            if audio_segments:
                logger.debug("Merging audio segments...")
                merged_audio = audio_segments[0]
                for seg in audio_segments[1:]:
                    merged_audio += seg
                merged_audio.export(filename, format="mp3")
            
        await asyncio.to_thread(run_tts_chunked)
        logger.info(f"Tạo file Audiobook thành công: {filename}")
    except Exception as e:
        logger.error(f"Lỗi khi tạo Audiobook: {e}")
        raise e
```

- [ ] **Step 2: Update tao_file_audiodrama in exporter.py**

```python
# In vvr_scraper/exporter.py, modify `run_audio_drama_v2` logic inside `tao_file_audiodrama`:
# Remove Vieneu imports, add ElevenLabs.
    try:
        from elevenlabs.client import ElevenLabs
        from pydub import AudioSegment
        from .bgm_manager import BGMManager
        from .mixing_engine import MixingEngine
        import io
        import soundfile as sf
    except ImportError as e:
        logger.error(f"Required libraries for Audio Drama v2 not found: {e}")
        return

    logger.info(f"Synthesizing audio drama v2: {filename}...")
    
    try:
        def run_audio_drama_v2():
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                raise ValueError("ELEVENLABS_API_KEY environment variable is required")
                
            client = ElevenLabs(api_key=api_key)
            bgm_manager = BGMManager()
            mixing_engine = MixingEngine()
            
            master_audio = AudioSegment.silent(duration=0)
            current_bgm = None
            current_time_ms = 0
            
            total_items = len(enriched_script)
            for i, item in enumerate(enriched_script):
                if item.get('type') == 'mood_shift':
                    mood = item.get('mood')
                    logger.debug(f"Mood shift detected: {mood}")
                    bgm_track = bgm_manager.get_random_track(mood)
                    if bgm_track:
                        current_bgm = AudioSegment.from_file(bgm_track)
                        logger.debug(f"Loaded BGM: {bgm_track}")
                elif item.get('type') == 'segment':
                    text = item.get('text', '')
                    voice_id = item.get('voice')
                    if not text: continue
                    
                    logger.debug(f"Synthesizing [{voice_id}]: {text[:30]}...")
                    # Generate speech
                    audio_stream = client.generate(text=text, voice=voice_id, model="eleven_multilingual_v2")
                    audio_bytes = b"".join(list(audio_stream))
                    voice_seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                    
                    # Mix with BGM
                    mixed_seg = mixing_engine.mix_segment(voice_seg, current_bgm)
                    
                    # Append
                    master_audio += mixed_seg
            
            master_audio.export(filename, format="mp3")
            
        await asyncio.to_thread(run_audio_drama_v2)
        logger.info(f"Tạo file Audio Drama thành công: {filename}")
```

- [ ] **Step 3: Update Exporter Tests**

```python
# Update tests/test_exporter_audio.py
# Mock `elevenlabs.client.ElevenLabs` instead of `vieneu.Vieneu`
# Replace the old `patch("vieneu.Vieneu")` with `patch("vvr_scraper.exporter.ElevenLabs")`
```

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/exporter.py tests/test_exporter_audio.py
git commit -m "feat: use ElevenLabs for audio generation in exporter"
```
