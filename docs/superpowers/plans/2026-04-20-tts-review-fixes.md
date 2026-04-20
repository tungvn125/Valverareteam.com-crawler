# Plan: Fix Critical & Warning Issues from TTS Code Quality Review

## Source
- Review report from `review` subagent on all TTS abstraction files
- 2 ❌ critical bugs, 36 ⚠️ warnings, 26 ✅ passing

---

## Critical Fixes (Must Fix)

### CRIT-1: `exporter.py:401` — Missing `await` inside `asyncio.to_thread`
**Problem:** `provider.synthesize()` is async but called inside `run_tts_chunked()` which is a sync function passed to `asyncio.to_thread()`. Adding bare `await` causes `SyntaxError: 'await' outside async function`.

**Root cause:** The entire TTS synthesis loop is wrapped in a sync `run_tts_chunked` function for pydub merging, but the provider call is async.

**Fix:** Remove the `asyncio.to_thread(run_tts_chunked)` wrapper. Make the whole synthesis loop async directly — pydub operations (blocking) can stay in `asyncio.to_thread` for the merge/export only. Structure:
```python
async def tao_file_mp3(...):
    ...
    # Synthesize chunks (async, directly in async context)
    audio_segments = []
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        voice_spec = VoiceSpec(...)
        result = await provider.synthesize(text=chunk, voice=voice_spec)
        segment = pydub.AudioSegment.from_file(io.BytesIO(result.audio_bytes), format="mp3")
        audio_segments.append(segment)

    # Merge + export (blocking, run in thread)
    def _merge_and_export(segments, path):
        if segments:
            merged = segments[0]
            for seg in segments[1:]:
                merged += seg
            merged.export(path, format="mp3")

    await asyncio.to_thread(_merge_and_export, audio_segments, filename)
```

**File:** `vvr_scraper/exporter.py` lines 384-412

---

### CRIT-2: `omnivoice_provider.py:35-43` — Blocking `self._model.generate()` in async context
**Problem:** `self._model.generate()` is a blocking PyTorch inference call inside `async def synthesize()`, which blocks the event loop.

**Fix:** Wrap in `asyncio.to_thread()`:
```python
async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
    import functools
    if voice.ref_audio_path:
        gen_fn = functools.partial(self._model.generate, text=text, ref_audio=voice.ref_audio_path, ref_text=voice.ref_text)
    elif voice.instruct:
        gen_fn = functools.partial(self._model.generate, text=text, instruct=voice.instruct)
    else:
        gen_fn = functools.partial(self._model.generate, text=text)

    audio_np = await asyncio.to_thread(gen_fn)
    ...
```

**File:** `vvr_scraper/tts/omnivoice_provider.py` lines 32-49

---

## Warning Fixes (Low Priority, Quick Wins)

### WARN-1: Missing class docstrings
Add docstrings to:
- `ElevenLabsProvider` — `elevenlabs_provider.py:15`
- `OmniVoiceProvider` — `omnivoice_provider.py:11`
- `OpenAITTSProvider` — `openai_tts_provider.py:12`

### WARN-2: Silent `except: pass` in `omnivoice_provider.py:68-73`
Log warning instead of silent swallow:
```python
except Exception as e:
    logger.warning(f"Failed to close OmniVoice model: {e}")
```

### WARN-3: Silent `except Exception: pass` in `openai_tts_provider.py:76-77`
Same — log warning.

### WARN-4: `_registry: dict[str, type]` → `dict[str, type[TTSProvider]]` in `tts/__init__.py:8`
Type precision improvement.

### WARN-5: Missing type hints on `VoiceManager.__init__`, `VoiceManager.synthesize`, `_synthesize_elevenlabs_legacy`
Add proper type annotations.

### WARN-6: Test global state in `test_audio_drama.py`
Add cleanup/monkeypatch for `VoiceManager._global_available_voices`.

### WARN-7: `test_tts_base.py:105` env var clearing
Only unset specific keys instead of `clear=True`.

---

## Execution Order

1. **CRIT-1** + **CRIT-2** — can be done in parallel (different files, no conflicts)
2. **WARN-1..7** — batch in one `implement` subagent (low risk, all quick edits)
3. **Final review** — run `review` subagent on all changed files

---

## Expected Outcome
- All ❌ resolved
- All ⚠️ resolved or documented as acceptable
- All tests still pass
- Final review shows ✅ across the board
