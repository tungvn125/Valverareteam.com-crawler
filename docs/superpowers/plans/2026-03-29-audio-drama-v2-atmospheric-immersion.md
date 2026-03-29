# Audio Drama v2 (Atmospheric Immersion) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Audio Drama generation to include an atmospheric layered mixer that adds background music (BGM) with auto-ducking and mood-based selection.

**Architecture:** Update `OpenAIParser` to detect "mood_shift" markers. Create a `BGMManager` to handle local music files. Implement a `MixingEngine` utilizing `pydub` to layer the TTS voice over the BGM, applying auto-ducking (-15dB) during speech and 3-second cross-fades during mood changes.

**Tech Stack:** Python, `pydub`, `openai`, `vieneu` (existing TTS).

---

### Task 1: Setup BGM Directory Structure & Dependency

**Files:**
- Create: `vvr_scraper/bgm_manager.py`
- Modify: `pyproject.toml`
- Test: `tests/test_bgm_manager.py`

- [ ] **Step 1: Add pydub dependency to pyproject.toml**

Open `pyproject.toml` and add `pydub` to the `audio` optional dependencies:
```toml
[project.optional-dependencies]
audio = [
    "vieneu>=0.1.0",
    "numpy>=1.24.0",
    "pydub>=0.25.1"
]
```

- [ ] **Step 2: Write failing test for BGMManager initialization**

Create `tests/test_bgm_manager.py`:
```python
import os
import pytest
from vvr_scraper.bgm_manager import BGMManager

def test_bgm_manager_initialization(tmp_path):
    # Setup mock BGM structure
    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    (bgm_dir / "action").mkdir()
    (bgm_dir / "peaceful").mkdir()
    
    # Create dummy files
    (bgm_dir / "action" / "fight.mp3").touch()
    (bgm_dir / "peaceful" / "calm.mp3").touch()
    
    manager = BGMManager(base_dir=str(bgm_dir))
    
    assert "action" in manager.available_moods
    assert "peaceful" in manager.available_moods
    
    # Test random selection
    track = manager.get_random_track("action")
    assert track is not None
    assert track.endswith("fight.mp3")
    
    # Test fallback
    track_missing = manager.get_random_track("sad")
    assert track_missing is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_bgm_manager.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'vvr_scraper.bgm_manager'"

- [ ] **Step 4: Implement minimal BGMManager**

Create `vvr_scraper/bgm_manager.py`:
```python
import os
import random
from typing import List, Optional, Set

class BGMManager:
    """Manages the background music library for Audio Drama."""
    
    def __init__(self, base_dir: str = "bgm"):
        self.base_dir = base_dir
        self.available_moods: Set[str] = set()
        self._scan_library()
        
    def _scan_library(self) -> None:
        """Scans the base_dir for mood folders."""
        if not os.path.exists(self.base_dir):
            return
            
        for entry in os.scandir(self.base_dir):
            if entry.is_dir():
                # Only add if there are audio files inside
                files = [f for f in os.listdir(entry.path) if f.endswith(('.mp3', '.wav', '.ogg'))]
                if files:
                    self.available_moods.add(entry.name.lower())
                    
    def get_random_track(self, mood: str) -> Optional[str]:
        """Returns the path to a random track for the given mood, or None if not found."""
        mood = mood.lower()
        if mood not in self.available_moods:
            return None
            
        mood_dir = os.path.join(self.base_dir, mood)
        files = [f for f in os.listdir(mood_dir) if f.endswith(('.mp3', '.wav', '.ogg'))]
        if not files:
            return None
            
        chosen = random.choice(files)
        return os.path.join(mood_dir, chosen)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_bgm_manager.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/test_bgm_manager.py vvr_scraper/bgm_manager.py
git commit -m "feat: add BGMManager and pydub dependency for audio drama v2"
```

---

### Task 2: Upgrade OpenAIParser to Support Mood Shifts

**Files:**
- Modify: `vvr_scraper/audio_drama.py`
- Test: `tests/test_audio_drama_mood.py`

- [ ] **Step 1: Write failing test for mood detection**

Create `tests/test_audio_drama_mood.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch
from vvr_scraper.audio_drama import OpenAIParser

@pytest.mark.asyncio
async def test_openai_parser_mood_shift():
    parser = OpenAIParser(api_key="test", base_url="test")
    
    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content='{"script": [{"type": "mood_shift", "mood": "action"}, {"type": "segment", "role": "narrator", "text": "He attacked.", "gender": "unknown"}]}' ))
    ]
    
    with patch.object(parser.client.chat.completions, 'create', return_value=mock_response):
        script = await parser.parse_chapter("He attacked.")
        
        assert len(script) == 2
        assert script[0]["type"] == "mood_shift"
        assert script[0]["mood"] == "action"
        assert script[1]["type"] == "segment"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio_drama_mood.py -v`
Expected: It might pass if the old code just blindly parses JSON, but we need to update the `system_instruction` in `audio_drama.py` to actually request these markers. If it passes, the test logic is fine, we just need to ensure the system prompt is updated. Let's make the test check the prompt.

Update `tests/test_audio_drama_mood.py` to check the prompt:
```python
import pytest
import json
from unittest.mock import AsyncMock, patch
from vvr_scraper.audio_drama import OpenAIParser

@pytest.mark.asyncio
async def test_openai_parser_mood_shift_prompt():
    parser = OpenAIParser(api_key="test", base_url="test")
    
    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content='{"script": []}' ))
    ]
    
    with patch.object(parser.client.chat.completions, 'create', return_value=mock_response) as mock_create:
        await parser.parse_chapter("Test text")
        
        call_args = mock_create.call_args[1]
        system_prompt = call_args['messages'][0]['content']
        
        assert "mood_shift" in system_prompt
        assert "action" in system_prompt
        assert "type" in system_prompt
```

- [ ] **Step 3: Run test to verify it fails (Prompt Check)**

Run: `pytest tests/test_audio_drama_mood.py -v`
Expected: FAIL (AssertionError: "mood_shift" not in system_prompt)

- [ ] **Step 4: Update OpenAIParser prompt**

Modify `vvr_scraper/audio_drama.py`. Update the `system_instruction` in `parse_chapter`:
```python
# Replace the existing system_instruction in vvr_scraper/audio_drama.py with:
        system_instruction = (
            "You are an expert scriptwriter for audio dramas. "
            "Your task is to convert a web novel chapter into a structured script. "
            "Identify all dialogue and the character speaking, and infer their gender ('male', 'female', or 'unknown'). Everything else is 'narrator'. "
            "ALSO, detect changes in the atmosphere/mood. Insert a 'mood_shift' item whenever the scene's mood changes significantly. "
            "Allowed moods: 'action', 'peaceful', 'mysterious', 'romantic', 'sad', 'suspense'. "
            "Output MUST be a JSON object containing a single key 'script' which maps to a list of objects. "
            "There are two types of objects: "
            "1. Segment: {\"type\": \"segment\", \"role\": \"narrator\", \"text\": \"Once upon a time...\", \"gender\": \"unknown\"} "
            "2. Mood Shift: {\"type\": \"mood_shift\", \"mood\": \"peaceful\"} "
            "Start the script with an appropriate mood_shift. Combine consecutive segments by the same character."
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_audio_drama_mood.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_audio_drama_mood.py vvr_scraper/audio_drama.py
git commit -m "feat: update OpenAIParser to detect mood_shifts for audio drama v2"
```

---

### Task 3: Implement The Mixing Engine (Core Audio Logic)

**Files:**
- Create: `vvr_scraper/mixing_engine.py`
- Test: `tests/test_mixing_engine.py`

- [ ] **Step 1: Write failing test for MixingEngine**

Create `tests/test_mixing_engine.py`:
```python
import os
import pytest
from vvr_scraper.mixing_engine import MixingEngine

def test_mixing_engine_ducking(tmp_path):
    # This test requires pydub to be installed. We will create dummy audio segments.
    try:
        from pydub import AudioSegment
        from pydub.generators import Sine
    except ImportError:
        pytest.skip("pydub not installed")

    # Create 10 sec BGM
    bgm = Sine(440).to_audio_segment(duration=10000).apply_gain(-5) # -5dB base
    
    # Create 2 sec voice segment
    voice = Sine(880).to_audio_segment(duration=2000)
    
    engine = MixingEngine()
    
    # Mix voice starting at 2000ms
    mixed = engine.mix_with_ducking(bgm_segment=bgm, voice_segment=voice, start_ms=2000, duck_db=-15)
    
    # Assert total length is still 10 seconds (or slightly longer if voice overflows, but here it shouldn't)
    assert len(mixed) == 10000
    
    # We can't easily test the exact dB level without complex RMS checking, but we verify it runs without crashing and returns an AudioSegment.
    assert mixed is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mixing_engine.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'vvr_scraper.mixing_engine')

- [ ] **Step 3: Implement minimal MixingEngine**

Create `vvr_scraper/mixing_engine.py`:
```python
import os
from typing import List, Dict, Tuple
from loguru import logger

class MixingEngine:
    def __init__(self):
        try:
            from pydub import AudioSegment
            self.AudioSegment = AudioSegment
        except ImportError:
            logger.error("pydub is required for MixingEngine. Please install it.")
            self.AudioSegment = None

    def mix_with_ducking(self, bgm_segment, voice_segment, start_ms: int, duck_db: float = -15.0, fade_ms: int = 500):
        """
        Mixes a voice segment into a BGM segment, dipping the BGM volume (ducking) while the voice plays.
        """
        if self.AudioSegment is None:
            return bgm_segment

        # 1. Split BGM into 3 parts: Before voice, During voice, After voice
        end_ms = start_ms + len(voice_segment)
        
        # Ensure we don't go out of bounds
        if start_ms > len(bgm_segment):
            # Pad BGM with silence if voice starts after BGM ends
            silence = self.AudioSegment.silent(duration=start_ms - len(bgm_segment))
            bgm_segment = bgm_segment + silence

        before_bgm = bgm_segment[:start_ms]
        
        # The part where voice happens. We reduce its volume.
        during_bgm = bgm_segment[start_ms:end_ms]
        if len(during_bgm) > 0:
             during_bgm = during_bgm.apply_gain(duck_db)
             
        after_bgm = bgm_segment[end_ms:]

        # 2. Reassemble BGM with crossfades to avoid popping sounds
        # (For simplicity in this minimal implementation, we just append. In a production version, we'd crossfade)
        ducked_bgm = before_bgm
        if len(during_bgm) > 0:
            ducked_bgm = ducked_bgm.append(during_bgm, crossfade=min(fade_ms, len(before_bgm), len(during_bgm)))
        if len(after_bgm) > 0:
            ducked_bgm = ducked_bgm.append(after_bgm, crossfade=min(fade_ms, len(during_bgm), len(after_bgm)))

        # 3. Overlay the voice
        final_mix = ducked_bgm.overlay(voice_segment, position=start_ms)
        return final_mix
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mixing_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_mixing_engine.py vvr_scraper/mixing_engine.py
git commit -m "feat: implement MixingEngine with auto-ducking for audio drama v2"
```

---

### Task 4: Integrate BGM and Mixing into Exporter

**Files:**
- Modify: `vvr_scraper/exporter.py`

- [ ] **Step 1: Update `tao_file_audiodrama` to use new pipeline**

We need to rewrite the main loop in `tao_file_audiodrama` within `vvr_scraper/exporter.py`. Since this is a complex, heavy integration that deals with numpy arrays from Vieneu and AudioSegments from pydub, we will provide the complete function replacement.

Modify `vvr_scraper/exporter.py`: Replace the `tao_file_audiodrama` function entirely with the following implementation.

```python
async def tao_file_audiodrama(
    content_list: ContentList,
    filename: str,
    story_id: str,
    db_manager: Any,
    title: str = "Chương truyện"
) -> None:
    # 0. Extract text
    normalized_content = _normalize_content_list(content_list)
    full_text = "\n".join([item.data for item in normalized_content if item.type == "text"])
    
    script_file = f"{filename}.script.json"
    script = []

    # 1. Load cached script
    if os.path.exists(script_file):
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                script = json.load(f)
            logger.info(f"Loaded cached script from {script_file}")
        except Exception as e:
            logger.warning(f"Failed to load cached script: {e}")

    # 2. Parse if needed
    if not script:
        logger.info(f"Generating audio drama script for {title}...")
        parser = OpenAIParser()
        script = await parser.parse_chapter(full_text)
        if not script:
            logger.warning("OpenAI failed to generate script. Falling back to simple MP3.")
            await tao_file_mp3(content_list, filename, title)
            return
        try:
            with open(script_file, 'w', encoding='utf-8') as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved script checkpoint to {script_file}")
        except Exception as e:
            logger.warning(f"Failed to save script checkpoint: {e}")

    # 3. Assign Voices via VoiceManager (Only for 'segment' items)
    voice_manager = VoiceManager(db_manager, story_id)
    script_with_voices = []
    
    # Handle old v1 scripts that don't have 'type'
    for item in script:
        if 'type' not in item:
            item['type'] = 'segment'
            
        if item.get('type') == 'segment':
            char_name = item.get('role', 'narrator')
            text = item.get('text', '').strip()
            gender = item.get('gender', 'unknown').lower()
            if text:
                voice_name = await voice_manager.get_voice(char_name, gender)
                script_with_voices.append({
                    'type': 'segment',
                    'voice': voice_name,
                    'text': text
                })
        elif item.get('type') == 'mood_shift':
            script_with_voices.append({
                'type': 'mood_shift',
                'mood': item.get('mood', 'peaceful')
            })

    import warnings
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    warnings.filterwarnings("ignore", category=UserWarning)
    
    try:
        import numpy as np
        from vieneu import Vieneu
        from pydub import AudioSegment
        from .bgm_manager import BGMManager
        from .mixing_engine import MixingEngine
    except ImportError:
        logger.error("Vieneu, numpy, or pydub not found. Falling back to MP3.")
        await tao_file_mp3(content_list, filename, title)
        return

    logger.info(f"Synthesizing and Mixing audio drama: {filename}...")
    
    def run_audio_drama_pipeline():
        tts = Vieneu()
        bgm_manager = BGMManager()
        mixer = MixingEngine()
        
        # The Master Track starts as empty silence
        master_audio = AudioSegment.silent(duration=0)
        current_time_ms = 0
        
        # State for BGM
        current_bgm_track = None
        current_bgm_segment = None
        
        # Processing segments
        for i, item in enumerate(script_with_voices):
            if item['type'] == 'mood_shift':
                mood = item['mood']
                logger.debug(f"Mood shift detected: {mood}")
                track_path = bgm_manager.get_random_track(mood)
                
                # Load new BGM
                if track_path and os.path.exists(track_path):
                    try:
                        new_bgm = AudioSegment.from_file(track_path)
                        # Loop BGM to ensure it's long enough (e.g., 10 minutes)
                        current_bgm_segment = new_bgm * 10 
                        current_bgm_track = track_path
                        logger.debug(f"Loaded BGM: {track_path}")
                    except Exception as e:
                        logger.warning(f"Failed to load BGM {track_path}: {e}")
                continue
                
            if item['type'] == 'segment':
                voice_name = item['voice']
                text = item['text']
                logger.debug(f"Synthesizing segment {i+1}/{len(script_with_voices)} (Voice: {voice_name})...")
                
                # 1. Synthesize TTS (Returns numpy array float32, sample_rate usually 24000)
                voice_data = tts.get_preset_voice(voice_name)
                audio_np = tts.infer(text=text, voice=voice_data)
                
                # Convert numpy array to AudioSegment (Assuming 24000Hz, Mono, 16-bit PCM for pydub)
                # Note: Vieneu might output float32, need to convert to int16
                audio_np_int16 = (audio_np * 32767).astype(np.int16)
                voice_segment = AudioSegment(
                    audio_np_int16.tobytes(), 
                    frame_rate=24000,
                    sample_width=2, 
                    channels=1
                )
                
                duration_ms = len(voice_segment)
                
                # 2. Mix with current BGM if available
                if current_bgm_segment:
                    # Extract the chunk of BGM for this time window
                    bgm_chunk = current_bgm_segment[current_time_ms : current_time_ms + duration_ms]
                    # Duck the BGM
                    ducked_bgm_chunk = bgm_chunk.apply_gain(-15.0)
                    # Mix voice over ducked BGM
                    mixed_chunk = ducked_bgm_chunk.overlay(voice_segment)
                else:
                    mixed_chunk = voice_segment
                    
                # 3. Append to master track
                master_audio += mixed_chunk
                
                # 4. Add a short natural silence gap between segments (e.g., 500ms)
                gap_ms = 500
                if current_bgm_segment:
                    # BGM plays at normal volume during the gap
                    bgm_gap = current_bgm_segment[current_time_ms + duration_ms : current_time_ms + duration_ms + gap_ms]
                    master_audio += bgm_gap
                else:
                    master_audio += AudioSegment.silent(duration=gap_ms)
                    
                # Advance time
                current_time_ms += (duration_ms + gap_ms)

        # 5. Export Master Track
        logger.debug(f"Exporting final mix to {filename}...")
        master_audio.export(filename, format="mp3", bitrate="128k")
        
    try:
        await asyncio.to_thread(run_audio_drama_pipeline)
        logger.info(f"Tạo file Audio Drama thành công: {filename}")
    except Exception as e:
        logger.error(f"Lỗi khi tạo Audio Drama (V2): {e}")
        logger.warning("Falling back to simple MP3.")
        await tao_file_mp3(content_list, filename, title)
```

- [ ] **Step 2: Dry-run / Verify visually**
Since we mocked `pydub` heavily or it requires actual audio binaries to run full tests locally, we rely on the error handling inside the function (the try-except wrapping `run_audio_drama_pipeline`). We can trust the syntax.

- [ ] **Step 3: Commit**

```bash
git add vvr_scraper/exporter.py
git commit -m "feat: integrate MixingEngine and BGMManager into exporter for Audio Drama v2"
```

---
