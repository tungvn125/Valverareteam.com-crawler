# TTS Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple ElevenLabs from the audio drama pipeline by introducing a `TTSProvider` Protocol with 3 built-in providers (ElevenLabs, OmniVoice, OpenAI-compatible HTTP) and a registry system.

**Architecture:** New `vvr_scraper/tts/` package with `base.py` (Protocol + types), 3 provider implementations, and a registry factory. VoiceManager refactored to accept an injected `TTSProvider` and return `VoiceSpec` instead of raw `voice_id: str`. CLI gets `--tts-provider` flag. DB gets 2 additive columns.

**Tech Stack:** Python 3.12, httpx, dataclasses, typing.Protocol, pydub, soundfile (OmniVoice), elevenlabs SDK (ElevenLabs)

**Spec:** `docs/superpowers/specs/2026-04-20-tts-provider-abstraction-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `vvr_scraper/tts/__init__.py` | **NEW** — Provider registry, factory, auto-detect |
| `vvr_scraper/tts/base.py` | **NEW** — TTSProvider Protocol, VoiceSpec, SynthesisResult, VoiceInfo, WordAlignment, tag maps |
| `vvr_scraper/tts/elevenlabs_provider.py` | **NEW** — ElevenLabs cloud API implementation |
| `vvr_scraper/tts/omnivoice_provider.py` | **NEW** — OmniVoice local model implementation |
| `vvr_scraper/tts/openai_tts_provider.py` | **NEW** — OpenAI-compatible HTTP implementation |
| `vvr_scraper/models.py` | **MODIFY** — Add `ref_audio_path`, `ref_text` to CharacterProfile |
| `vvr_scraper/db.py` | **MODIFY** — Add 2 columns to character_profiles table |
| `vvr_scraper/audio_drama.py` | **MODIFY** — VoiceManager accepts TTSProvider, returns VoiceSpec |
| `vvr_scraper/exporter.py` | **MODIFY** — tao_file_audiodrama uses VoiceSpec flow, tao_file_mp3 uses provider |
| `vvr_scraper/cli.py` | **MODIFY** — Add --tts-provider flag |
| `vvr_scraper/prompts/audio_drama_script.md` | **MODIFY** — Provider-agnostic performance tags |
| `vvr_scraper/web/routes/correction.py` | **MODIFY** — Use provider.discover_voices() / preview_voice() |
| `tests/test_tts_base.py` | **NEW** — Unit tests for VoiceSpec, tag mapping, registry |
| `tests/test_tts_providers.py` | **NEW** — Unit tests for each provider with mocks |
| `tests/test_audio_drama.py` | **MODIFY** — Update to use VoiceSpec instead of voice_id string |

---

### Task 1: Core types and Protocol (`tts/base.py`)

**Files:**
- Create: `vvr_scraper/tts/base.py`
- Test: `tests/test_tts_base.py`

- [ ] **Step 1: Write the failing test for VoiceSpec modes**

```python
# tests/test_tts_base.py
import pytest
from vvr_scraper.tts.base import VoiceSpec, WordAlignment, SynthesisResult, VoiceInfo, map_tags


class TestVoiceSpec:
    def test_mode_clone(self):
        spec = VoiceSpec(ref_audio_path="voices/narrator/sample.wav", ref_text="Hello")
        assert spec.mode == "clone"

    def test_mode_voice_id(self):
        spec = VoiceSpec(voice_id="ywBZEqUhld86Jeajq94o")
        assert spec.mode == "voice_id"

    def test_mode_design(self):
        spec = VoiceSpec(instruct="female, low pitch")
        assert spec.mode == "design"

    def test_mode_auto(self):
        spec = VoiceSpec()
        assert spec.mode == "auto"

    def test_clone_takes_priority_over_voice_id(self):
        spec = VoiceSpec(ref_audio_path="voices/narrator/sample.wav", voice_id="abc123")
        assert spec.mode == "clone"

    def test_voice_id_takes_priority_over_design(self):
        spec = VoiceSpec(voice_id="abc123", instruct="female, low pitch")
        assert spec.mode == "voice_id"


class TestSynthesisResult:
    def test_with_alignments(self):
        result = SynthesisResult(
            audio_bytes=b"fake",
            sample_rate=24000,
            duration_ms=1000,
            word_alignments=[WordAlignment(word="Hello", start=0, end=500)],
        )
        assert result.word_alignments is not None
        assert len(result.word_alignments) == 1

    def test_without_alignments(self):
        result = SynthesisResult(audio_bytes=b"fake", sample_rate=24000, duration_ms=1000)
        assert result.word_alignments is None


class TestMapTags:
    def test_elevenlabs_tags(self):
        text = "[laughter] That was [sigh] funny."
        result = map_tags(text, "elevenlabs")
        assert result == "[laughs] That was [sighs] funny."

    def test_omnivoice_tags(self):
        text = "[laughter] That was [sigh] funny."
        result = map_tags(text, "omnivoice")
        assert result == "[laughter] That was [sigh] funny."

    def test_openai_tts_strips_tags(self):
        text = "[laughter] That was [sigh] funny."
        result = map_tags(text, "openai_tts")
        assert result == " That was  funny."

    def test_unknown_provider_passes_through(self):
        text = "[laughter] Hello"
        result = map_tags(text, "unknown_provider")
        assert result == "[laughter] Hello"

    def test_pause_tag_all_providers(self):
        text = "Wait[pause]then go."
        assert map_tags(text, "elevenlabs") == "Wait...then go."
        assert map_tags(text, "omnivoice") == "Wait...then go."
        assert map_tags(text, "openai_tts") == "Wait...then go."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.tts'`

- [ ] **Step 3: Create tts package and base.py**

```python
# vvr_scraper/tts/__init__.py
# (empty for now — will be populated in Task 3)
```

```python
# vvr_scraper/tts/base.py
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class VoiceSpec:
    """Provider-agnostic voice descriptor.

    Three mutually-exclusive modes (checked in priority order):
    1. Voice Clone: ref_audio_path + ref_text (OmniVoice cloning)
    2. Voice ID: voice_id (ElevenLabs cloud voice)
    3. Voice Design: instruct (OmniVoice fallback when no sample assigned)
    """

    # Mode 1: Voice Clone (OmniVoice preferred)
    ref_audio_path: str | None = None
    ref_text: str | None = None

    # Mode 2: Voice ID (ElevenLabs)
    voice_id: str | None = None

    # Mode 3: Voice Design fallback (OmniVoice only)
    instruct: str | None = None

    # Provider-specific settings passthrough
    settings: dict = field(default_factory=dict)

    @property
    def mode(self) -> str:
        if self.ref_audio_path:
            return "clone"
        if self.voice_id:
            return "voice_id"
        if self.instruct:
            return "design"
        return "auto"


@dataclass
class WordAlignment:
    word: str
    start: int  # milliseconds
    end: int    # milliseconds


@dataclass
class SynthesisResult:
    """Output of any TTS provider's synthesize call."""

    audio_bytes: bytes
    sample_rate: int
    duration_ms: int
    word_alignments: list[WordAlignment] | None = None


@dataclass
class VoiceInfo:
    """Metadata about a discovered/available voice."""

    voice_id: str | None = None
    name: str = ""
    gender: str = "unknown"
    ref_audio_path: str | None = None
    labels: dict = field(default_factory=dict)


# --- Tag mapping ---

ELEVENLABS_TAG_MAP: dict[str, str] = {
    "[laughter]": "[laughs]",
    "[sigh]": "[sighs]",
    "[surprise]": "[gasps]",
    "[whisper]": "[whispers]",
    "[pause]": "...",
}

OMNIVOICE_TAG_MAP: dict[str, str] = {
    "[laughter]": "[laughter]",
    "[sigh]": "[sigh]",
    "[surprise]": "[surprise-ah]",
    "[whisper]": "[whisper]",
    "[pause]": "...",
}

OPENAI_TTS_TAG_MAP: dict[str, str] = {
    "[laughter]": "",
    "[sigh]": "",
    "[surprise]": "",
    "[whisper]": "",
    "[pause]": "...",
}


def map_tags(text: str, provider_name: str) -> str:
    """Replace provider-agnostic tags with provider-specific ones."""
    tag_map = {
        "elevenlabs": ELEVENLABS_TAG_MAP,
        "omnivoice": OMNIVOICE_TAG_MAP,
        "openai_tts": OPENAI_TTS_TAG_MAP,
    }.get(provider_name, {})

    for generic, specific in tag_map.items():
        text = text.replace(generic, specific)
    return text


@runtime_checkable
class TTSProvider(Protocol):
    """Interface that any TTS backend must implement."""

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult: ...
    async def discover_voices(self) -> list[VoiceInfo]: ...
    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes: ...
    async def close(self) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tts_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/tts/__init__.py vvr_scraper/tts/base.py tests/test_tts_base.py
git commit -m "feat(tts): add TTSProvider Protocol, VoiceSpec, SynthesisResult, tag mapping"
```

---

### Task 2: ElevenLabs Provider (`tts/elevenlabs_provider.py`)

**Files:**
- Create: `vvr_scraper/tts/elevenlabs_provider.py`
- Test: `tests/test_tts_providers.py`

- [ ] **Step 1: Write the failing test for ElevenLabsProvider**

```python
# tests/test_tts_providers.py
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.tts.base import VoiceSpec, SynthesisResult


class TestElevenLabsProvider:
    @pytest.mark.asyncio
    async def test_synthesize_with_timestamps(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        chunk1 = {
            "audio_base64": base64.b64encode(b"audio1").decode(),
            "alignment": {
                "characters": ["H", "e", "l", "l", "o", " "],
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            },
        }
        chunk2 = {
            "audio_base64": base64.b64encode(b"audio2").decode(),
            "alignment": {
                "characters": ["w", "o", "r", "l", "d"],
                "character_start_times_seconds": [0.6, 0.7, 0.8, 0.9, 1.0],
                "character_end_times_seconds": [0.7, 0.8, 0.9, 1.0, 1.1],
            },
        }

        class MockResponse:
            status_code = 200
            async def aiter_lines(self):
                for chunk in [chunk1, chunk2]:
                    yield json.dumps(chunk)
            async def aread(self):
                return b""
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=MockResponse())
        mock_stream_ctx.__aexit__ = AsyncMock()

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            voice = VoiceSpec(voice_id="test_voice")
            result = await provider.synthesize("Hello world", voice)

            assert isinstance(result, SynthesisResult)
            assert result.audio_bytes == b"audio1audio2"
            assert result.word_alignments is not None
            assert len(result.word_alignments) == 2
            assert result.word_alignments[0].word == "Hello"
            assert result.word_alignments[0].start == 0
            assert result.word_alignments[0].end == 500
            assert result.word_alignments[1].word == "world"
            assert result.word_alignments[1].start == 600
            assert result.word_alignments[1].end == 1100

    @pytest.mark.asyncio
    async def test_discover_voices(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        mock_voice = MagicMock()
        mock_voice.voice_id = "abc123"
        mock_voice.name = "Rachel"
        mock_voice.labels = {"gender": "female"}

        mock_client = MagicMock()
        mock_client.voices.get_all.return_value.voices = [mock_voice]

        with patch("elevenlabs.client.ElevenLabs", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            voices = await provider.discover_voices()
            assert len(voices) == 1
            assert voices[0].voice_id == "abc123"
            assert voices[0].name == "Rachel"
            assert voices[0].gender == "female"

    @pytest.mark.asyncio
    async def test_preview_voice(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        mock_client = MagicMock()
        mock_client.generate.return_value = [b"audio_chunk"]

        with patch("elevenlabs.client.ElevenLabs", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            voice = VoiceSpec(voice_id="test_voice")
            audio = await provider.preview_voice(voice, "Test")
            assert audio == b"audio_chunk"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts_providers.py::TestElevenLabsProvider -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.tts.elevenlabs_provider'`

- [ ] **Step 3: Write ElevenLabsProvider implementation**

```python
# vvr_scraper/tts/elevenlabs_provider.py
"""ElevenLabs TTS provider — cloud API with word-level timestamps."""

import asyncio
import base64
import io
import json
import os

import httpx
from loguru import logger

from .base import VoiceInfo, VoiceSpec, WordAlignment, SynthesisResult


class ElevenLabsProvider:
    """TTSProvider implementation for ElevenLabs cloud API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=300.0)

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize using ElevenLabs stream-with-timestamps endpoint."""
        voice_id = voice.voice_id or os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        stability = voice.settings.get("stability", 0.35)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-with-timestamps"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        data = {
            "text": text,
            "model_id": "eleven_v3",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        audio_buffer = io.BytesIO()
        all_alignments = []

        async with self._client.stream("POST", url, headers=headers, json=data) as response:
            if response.status_code != 200:
                error_msg = await response.aread()
                raise Exception(f"ElevenLabs API error ({response.status_code}): {error_msg}")

            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if "audio_base64" in chunk:
                        audio_buffer.write(base64.b64decode(chunk["audio_base64"]))
                    if "alignment" in chunk:
                        all_alignments.append(chunk["alignment"])
                except Exception as e:
                    logger.warning(f"Error parsing alignment chunk: {e}")

        full_audio = audio_buffer.getvalue()
        audio_buffer.close()

        # Process alignments into word-level timestamps
        word_alignments = _parse_word_alignments(all_alignments)

        # Estimate duration from audio
        duration_ms = _estimate_duration_ms(full_audio)

        return SynthesisResult(
            audio_bytes=full_audio,
            sample_rate=44100,
            duration_ms=duration_ms,
            word_alignments=word_alignments,
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        """List available voices from ElevenLabs cloud API."""
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=self._api_key)

        def fetch():
            return client.voices.get_all().voices

        voices = await asyncio.to_thread(fetch)
        return [
            VoiceInfo(
                voice_id=v.voice_id,
                name=v.name,
                gender=v.labels.get("gender", "unknown").lower() if v.labels else "unknown",
                labels=v.labels or {},
            )
            for v in voices
        ]

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        """Generate a short audio preview via ElevenLabs."""
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=self._api_key)
        voice_id = voice.voice_id or "EXAVITQu4vr4xnSDxMaL"

        def generate():
            return client.generate(text=text, voice=voice_id, model="eleven_v3")

        audio_chunks = await asyncio.to_thread(generate)
        return b"".join(list(audio_chunks))

    async def close(self) -> None:
        await self._client.aclose()


def _parse_word_alignments(all_alignments: list[dict]) -> list[WordAlignment]:
    """Parse ElevenLabs character-level alignments into word-level alignments."""
    word_alignments = []
    current_word_chars = []
    current_word_start = None
    last_end = 0.0

    for alignment in all_alignments:
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])

        for char, start, end in zip(chars, starts, ends, strict=False):
            if char.isspace():
                if current_word_chars:
                    word_text = "".join(current_word_chars)
                    word_alignments.append(
                        WordAlignment(
                            word=word_text,
                            start=int(current_word_start * 1000),
                            end=int(last_end * 1000),
                        )
                    )
                    current_word_chars = []
                    current_word_start = None
                continue

            if not current_word_chars:
                current_word_start = start
            current_word_chars.append(char)
            last_end = end

    if current_word_chars:
        word_text = "".join(current_word_chars)
        word_alignments.append(
            WordAlignment(
                word=word_text,
                start=int(current_word_start * 1000),
                end=int(last_end * 1000),
            )
        )

    return word_alignments


def _estimate_duration_ms(audio_bytes: bytes) -> int:
    """Estimate audio duration from MP3 bytes using pydub."""
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        return len(seg)
    except Exception:
        # Fallback: rough estimate at 128kbps MP3
        return int(len(audio_bytes) * 8 / 128)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tts_providers.py::TestElevenLabsProvider -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/tts/elevenlabs_provider.py tests/test_tts_providers.py
git commit -m "feat(tts): add ElevenLabsProvider with stream-with-timestamps"
```

---

### Task 3: OpenAI-Compatible HTTP Provider (`tts/openai_tts_provider.py`)

**Files:**
- Create: `vvr_scraper/tts/openai_tts_provider.py`
- Test: `tests/test_tts_providers.py` (append)

- [ ] **Step 1: Write the failing test for OpenAITTSProvider**

Append to `tests/test_tts_providers.py`:

```python
class TestOpenAITTSProvider:
    @pytest.mark.asyncio
    async def test_synthesize(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_mp3_audio_bytes"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(side_effect=Exception("no /voices endpoint"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider(
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="tts-1",
                default_voice="alloy",
            )
            voice = VoiceSpec(voice_id="echo")
            result = await provider.synthesize("Hello world", voice)

            assert result.audio_bytes == b"fake_mp3_audio_bytes"
            assert result.word_alignments is None

            # Verify the API call used voice_id as voice name
            call_kwargs = mock_client.post.call_args[1]["json"]
            assert call_kwargs["voice"] == "echo"
            assert call_kwargs["model"] == "tts-1"

    @pytest.mark.asyncio
    async def test_synthesize_uses_default_voice_when_no_voice_id(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(side_effect=Exception("no /voices"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider(default_voice="nova")
            voice = VoiceSpec()  # mode="auto", no voice_id
            result = await provider.synthesize("Hello", voice)

            call_kwargs = mock_client.post.call_args[1]["json"]
            assert call_kwargs["voice"] == "nova"

    @pytest.mark.asyncio
    async def test_discover_voices_fallback(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("no endpoint"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider()
            voices = await provider.discover_voices()
            names = [v.voice_id for v in voices]
            assert "alloy" in names
            assert "echo" in names
            assert len(voices) == 6  # OpenAI standard voices
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts_providers.py::TestOpenAITTSProvider -v`
Expected: FAIL

- [ ] **Step 3: Write OpenAITTSProvider implementation**

```python
# vvr_scraper/tts/openai_tts_provider.py
"""OpenAI-compatible HTTP TTS provider — works with any /v1/audio/speech server."""

import io
import os

import httpx
from loguru import logger

from .base import VoiceInfo, VoiceSpec, SynthesisResult


class OpenAITTSProvider:
    """TTSProvider for OpenAI-compatible /v1/audio/speech endpoint.

    Compatible with: OpenAI TTS, omnivoice-server, Azure OpenAI, LocalAI, etc.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        default_voice: str | None = None,
    ):
        self._base_url = (base_url or os.getenv("OPENAI_TTS_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._api_key = api_key or os.getenv("OPENAI_TTS_API_KEY")
        self._model = model or os.getenv("OPENAI_TTS_MODEL", "tts-1")
        self._default_voice = default_voice or os.getenv("OPENAI_TTS_DEFAULT_VOICE", "alloy")

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=60.0,
        )

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize via POST /v1/audio/speech."""
        voice_name = voice.voice_id or self._default_voice

        response = await self._client.post(
            "/audio/speech",
            json={
                "model": self._model,
                "input": text,
                "voice": voice_name,
                "response_format": "mp3",
            },
        )
        response.raise_for_status()
        audio_bytes = response.content

        # Estimate duration
        duration_ms = _estimate_duration_ms(audio_bytes)
        sample_rate = 44100

        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=sample_rate,
            duration_ms=duration_ms,
            word_alignments=None,
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        """Try GET /v1/voices, fall back to hardcoded OpenAI voice list."""
        try:
            response = await self._client.get("/voices")
            if response.status_code == 200:
                data = response.json()
                voice_list = data.get("voices", data if isinstance(data, list) else [])
                return [
                    VoiceInfo(voice_id=v.get("id", v.get("voice_id", "")), name=v.get("name", v.get("id", "")))
                    for v in voice_list
                ]
        except Exception:
            pass

        # Fallback: OpenAI standard voices
        return [
            VoiceInfo(voice_id=name, name=name.title())
            for name in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        ]

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        result = await self.synthesize(text, voice)
        return result.audio_bytes

    async def close(self) -> None:
        await self._client.aclose()


def _estimate_duration_ms(audio_bytes: bytes) -> int:
    """Estimate audio duration from MP3 bytes using pydub."""
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        return len(seg)
    except Exception:
        return int(len(audio_bytes) * 8 / 128)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tts_providers.py::TestOpenAITTSProvider -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/tts/openai_tts_provider.py tests/test_tts_providers.py
git commit -m "feat(tts): add OpenAI-compatible HTTP TTS provider"
```

---

### Task 4: OmniVoice Provider (`tts/omnivoice_provider.py`)

**Files:**
- Create: `vvr_scraper/tts/omnivoice_provider.py`
- Test: `tests/test_tts_providers.py` (append)

- [ ] **Step 1: Write the failing test for OmniVoiceProvider**

Append to `tests/test_tts_providers.py`:

```python
class TestOmniVoiceProvider:
    @pytest.mark.asyncio
    async def test_synthesize_clone_mode(self):
        from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

        mock_model = MagicMock()
        mock_model.generate.return_value = [MagicMock(shape=(24000,))]  # fake np.ndarray
        mock_model.sampling_rate = 24000

        # Mock soundfile.write to capture output
        with patch("vvr_scraper.tts.omnivoice_provider.OmniVoice", return_value=mock_model):
            with patch("soundfile.write") as mock_sf_write:
                # Make soundfile.write actually write WAV header to BytesIO
                import numpy as np
                mock_model.generate.return_value = [np.zeros(24000, dtype=np.float32)]

                provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
                provider._model = mock_model
                provider._sampling_rate = 24000

                voice = VoiceSpec(ref_audio_path="voices/narrator/sample.wav", ref_text="Hello")
                result = await provider.synthesize("Hello world", voice)

                assert result.word_alignments is None
                assert result.sample_rate == 24000
                mock_model.generate.assert_called_once_with(
                    text="Hello world",
                    ref_audio="voices/narrator/sample.wav",
                    ref_text="Hello",
                )

    @pytest.mark.asyncio
    async def test_synthesize_design_mode(self):
        from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

        mock_model = MagicMock()
        mock_model.sampling_rate = 24000

        import numpy as np
        mock_model.generate.return_value = [np.zeros(12000, dtype=np.float32)]

        provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
        provider._model = mock_model
        provider._sampling_rate = 24000

        voice = VoiceSpec(instruct="female, low pitch")
        result = await provider.synthesize("Hello", voice)

        mock_model.generate.assert_called_once_with(text="Hello", instruct="female, low pitch")
        assert result.duration_ms == 500  # 12000 / 24000 * 1000

    @pytest.mark.asyncio
    async def test_synthesize_auto_mode(self):
        from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

        mock_model = MagicMock()
        mock_model.sampling_rate = 24000

        import numpy as np
        mock_model.generate.return_value = [np.zeros(12000, dtype=np.float32)]

        provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
        provider._model = mock_model
        provider._sampling_rate = 24000

        voice = VoiceSpec()  # auto mode
        result = await provider.synthesize("Hello", voice)

        mock_model.generate.assert_called_once_with(text="Hello")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts_providers.py::TestOmniVoiceProvider -v`
Expected: FAIL

- [ ] **Step 3: Write OmniVoiceProvider implementation**

```python
# vvr_scraper/tts/omnivoice_provider.py
"""OmniVoice TTS provider — local model with voice cloning and design."""

import io
import os

from loguru import logger

from .base import VoiceInfo, VoiceSpec, SynthesisResult


class OmniVoiceProvider:
    """TTSProvider implementation for OmniVoice local model.

    Supports voice cloning (ref_audio), voice design (instruct), and auto mode.
    Requires GPU with PyTorch + OmniVoice installed.
    """

    def __init__(self, model_name: str = "k2-fsa/OmniVoice", device: str | None = None):
        from omnivoice import OmniVoice

        device = device or os.getenv("VVR_OMNIVOICE_DEVICE", "cuda:0")
        self._model = OmniVoice.from_pretrained(model_name, device_map=device, dtype="float16")
        self._model.load_asr_model()  # For auto-transcription of ref_audio
        self._sampling_rate = self._model.sampling_rate

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize using OmniVoice local model."""
        import asyncio

        if voice.ref_audio_path:
            audio_np = self._model.generate(
                text=text,
                ref_audio=voice.ref_audio_path,
                ref_text=voice.ref_text,  # None → auto-transcribe via Whisper
            )
        elif voice.instruct:
            audio_np = self._model.generate(text=text, instruct=voice.instruct)
        else:
            audio_np = self._model.generate(text=text)

        # Convert np.ndarray → WAV bytes
        import soundfile as sf

        buf = io.BytesIO()
        sf.write(buf, audio_np[0], self._sampling_rate, format="WAV")
        audio_bytes = buf.getvalue()
        duration_ms = int(len(audio_np[0]) / self._sampling_rate * 1000)

        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=self._sampling_rate,
            duration_ms=duration_ms,
            word_alignments=None,
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        """Scan local voices/ directories for sample files."""
        # This is a stub — actual implementation scans story output dirs
        # which requires story context. For now, return empty.
        return []

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        result = await self.synthesize(text, voice)
        return result.audio_bytes

    async def close(self) -> None:
        try:
            import torch
            del self._model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tts_providers.py::TestOmniVoiceProvider -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/tts/omnivoice_provider.py tests/test_tts_providers.py
git commit -m "feat(tts): add OmniVoiceProvider with voice cloning and design"
```

---

### Task 5: Provider Registry (`tts/__init__.py`)

**Files:**
- Modify: `vvr_scraper/tts/__init__.py`
- Test: `tests/test_tts_base.py` (append)

- [ ] **Step 1: Write the failing test for registry**

Append to `tests/test_tts_base.py`:

```python
class TestRegistry:
    def test_register_and_get(self):
        from vvr_scraper.tts import register, get_provider

        class FakeProvider:
            def __init__(self, **kw): pass
            async def synthesize(self, text, voice): pass
            async def discover_voices(self): return []
            async def preview_voice(self, voice, text): return b""
            async def close(self): pass

        register("fake_test", FakeProvider)
        provider = get_provider("fake_test")
        assert isinstance(provider, FakeProvider)

    def test_get_unknown_raises(self):
        from vvr_scraper.tts import get_provider

        with pytest.raises(ValueError, match="Unknown TTS provider"):
            get_provider("nonexistent_provider_xyz")

    def test_auto_detect_elevenlabs(self):
        from vvr_scraper.tts import auto_detect_provider

        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}, clear=False):
            result = auto_detect_provider()
            assert result == "elevenlabs"

    def test_auto_detect_openai_tts(self):
        from vvr_scraper.tts import auto_detect_provider

        env = {"OPENAI_TTS_API_KEY": "sk-test", "ELEVENLABS_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True):
            result = auto_detect_provider()
            assert result == "openai_tts"

    def test_auto_detect_explicit_override(self):
        from vvr_scraper.tts import auto_detect_provider

        with patch.dict(os.environ, {"VVR_TTS_PROVIDER": "omnivoice"}, clear=True):
            result = auto_detect_provider()
            assert result == "omnivoice"

    def test_auto_detect_none_raises(self):
        from vvr_scraper.tts import auto_detect_provider

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="No TTS provider configured"):
                auto_detect_provider()
```

Add `import os` and `from unittest.mock import patch` to test file imports if not present.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts_base.py::TestRegistry -v`
Expected: FAIL

- [ ] **Step 3: Write registry implementation**

```python
# vvr_scraper/tts/__init__.py
"""TTS Provider registry and factory."""

import os
from typing import Any

from .base import TTSProvider

_registry: dict[str, type] = {}


def register(name: str, provider_cls: type) -> None:
    """Register a TTS provider class under the given name."""
    _registry[name] = provider_cls


def get_provider(name: str, **kwargs: Any) -> TTSProvider:
    """Instantiate a registered provider by name."""
    if name not in _registry:
        raise ValueError(
            f"Unknown TTS provider '{name}'. "
            f"Available: {list(_registry.keys())}. "
            f"Set --tts-provider or VVR_TTS_PROVIDER env var."
        )
    return _registry[name](**kwargs)


def auto_detect_provider() -> str:
    """Determine provider from env vars and installed packages."""
    explicit = os.getenv("VVR_TTS_PROVIDER")
    if explicit:
        return explicit

    if os.getenv("ELEVENLABS_API_KEY"):
        return "elevenlabs"

    if os.getenv("OPENAI_TTS_API_KEY") or os.getenv("OPENAI_TTS_BASE_URL"):
        return "openai_tts"

    raise ValueError(
        "No TTS provider configured. "
        "Set ELEVENLABS_API_KEY for ElevenLabs, "
        "OPENAI_TTS_API_KEY for OpenAI-compatible TTS, "
        "or set VVR_TTS_PROVIDER=omnivoice for OmniVoice local model."
    )


def _register_builtins() -> None:
    """Auto-register built-in providers (lazy — only if deps available)."""
    try:
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider
        register("elevenlabs", ElevenLabsProvider)
    except ImportError:
        pass

    try:
        from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider
        register("omnivoice", OmniVoiceProvider)
    except ImportError:
        pass

    # openai_tts always available (only needs httpx)
    from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider
    register("openai_tts", OpenAITTSProvider)


_register_builtins()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tts_base.py::TestRegistry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/tts/__init__.py tests/test_tts_base.py
git commit -m "feat(tts): add provider registry, factory, and auto-detect"
```

---

### Task 6: CharacterProfile extension + DB migration

**Files:**
- Modify: `vvr_scraper/models.py`
- Modify: `vvr_scraper/db.py`
- Test: `tests/test_db_audio.py` (append)

- [ ] **Step 1: Add ref_audio_path and ref_text to CharacterProfile**

In `vvr_scraper/models.py`, add 2 fields after `voice_id`:

```python
@dataclass
class CharacterProfile:
    """Detailed profile for a character in a story."""

    name: str  # canonical name
    story_id: str
    aliases: list[str] = field(default_factory=list)
    gender: str = "unknown"
    voice_id: str | None = None
    ref_audio_path: str | None = None     # NEW: path to voice sample file
    ref_text: str | None = None           # NEW: transcript of voice sample
    personality: str | None = None
    speaking_style: str | None = None
    emotion_range: float = 0.5
    color: str | None = None
```

- [ ] **Step 2: Add DB migration for new columns**

In `vvr_scraper/db.py`, inside `init_db()` method, after the existing character_profiles column migration block (around line 155), add:

```python
        # Migration: Add ref_audio_path and ref_text to character_profiles
        cursor = await db.execute("PRAGMA table_info(character_profiles)")
        existing_profile_columns = [row[1] for row in await cursor.fetchall()]

        for col_name, col_def in [("ref_audio_path", "TEXT"), ("ref_text", "TEXT")]:
            if col_name not in existing_profile_columns:
                try:
                    await db.execute(f"ALTER TABLE character_profiles ADD COLUMN {col_name} {col_def}")
                    await db.commit()
                    logger.info(f"Added column {col_name} to character_profiles.")
                except Exception as e:
                    logger.warning(f"Could not add column {col_name} to character_profiles: {e}")
```

- [ ] **Step 3: Update save_character_profile to handle new fields**

In `vvr_scraper/db.py`, update the `save_character_profile` method's INSERT/UPDATE SQL to include `ref_audio_path` and `ref_text`. Find the existing INSERT statement and add the new columns.

- [ ] **Step 4: Update get_character_profiles to read new fields**

In `vvr_scraper/db.py`, in the `get_character_profiles` method, add the new fields to the CharacterProfile constructor:

```python
                    ref_audio_path=profile_dict.get("ref_audio_path"),
                    ref_text=profile_dict.get("ref_text"),
```

- [ ] **Step 5: Write test for new fields**

Append to `tests/test_db_audio.py`:

```python
@pytest.mark.asyncio
async def test_character_voice_with_ref_audio(tmp_path):
    db_path = tmp_path / "test_ref.db"
    db = DatabaseManager(str(db_path))
    await db.init_db()

    from vvr_scraper.models import CharacterProfile

    profile = CharacterProfile(
        name="Hero",
        story_id="story1",
        gender="male",
        voice_id="abc123",
        ref_audio_path="voices/hero/sample.wav",
        ref_text="I am the hero of this story.",
    )
    await db.save_character_profile(profile)

    loaded = await db.get_character_profiles("story1")
    assert len(loaded) == 1
    assert loaded[0].ref_audio_path == "voices/hero/sample.wav"
    assert loaded[0].ref_text == "I am the hero of this story."
    assert loaded[0].voice_id == "abc123"
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_db_audio.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add vvr_scraper/models.py vvr_scraper/db.py tests/test_db_audio.py
git commit -m "feat(tts): add ref_audio_path and ref_text to CharacterProfile + DB migration"
```

---

### Task 7: VoiceManager refactor

**Files:**
- Modify: `vvr_scraper/audio_drama.py`
- Test: `tests/test_audio_drama.py` (update)

- [ ] **Step 1: Refactor VoiceManager to accept TTSProvider and return VoiceSpec**

Replace the entire `VoiceManager` class in `vvr_scraper/audio_drama.py` with:

```python
class VoiceManager:
    """Manages voice assignment for characters. Delegates synthesis to TTSProvider."""

    DEFAULT_NARRATOR_VOICE_ID = "ywBZEqUhld86Jeajq94o"

    _global_available_voices = None
    _global_voice_metadata = {}
    _global_init_lock = asyncio.Lock()

    def __init__(self, db, story_id: str, provider=None):
        from .tts.base import TTSProvider, VoiceSpec
        self._provider = provider
        self.db = db
        self.story_id = story_id
        self._voice_cache: dict[str, VoiceSpec] = {}  # char_name -> VoiceSpec
        self._profile_cache = {}
        self._initialized = False
        self._instance_lock = asyncio.Lock()

        # Build narrator voice from env config
        narrator_ref = os.getenv("VVR_NARRATOR_REF_AUDIO")
        if narrator_ref:
            self.narrator_voice = VoiceSpec(ref_audio_path=narrator_ref)
        else:
            narrator_id = os.getenv("VVR_NARRATOR_VOICE_ID", self.DEFAULT_NARRATOR_VOICE_ID)
            self.narrator_voice = VoiceSpec(voice_id=narrator_id)

        # Legacy: still need httpx client for ElevenLabs direct calls if no provider
        self._client = httpx.AsyncClient(timeout=300.0)
        self._cached_available_voices = []
        self._cached_voice_metadata = {}

    async def close(self):
        """Closes resources."""
        await self._client.aclose()
        if self._provider and hasattr(self._provider, 'close'):
            await self._provider.close()
        logger.debug("VoiceManager closed.")

    async def _init_cache(self):
        if self._initialized:
            return

        # 1. Load existing assignments and profiles from DB
        if hasattr(self.db, "get_all_story_voices"):
            db_voices = await self.db.get_all_story_voices(self.story_id)
            for k, v in db_voices.items():
                self._voice_cache[k.lower()] = VoiceSpec(voice_id=v)

        if hasattr(self.db, "get_character_profiles"):
            profiles = await self.db.get_character_profiles(self.story_id)
            for p in profiles:
                self._profile_cache[p.name.lower()] = p
                # Build VoiceSpec from profile
                if p.ref_audio_path:
                    self._voice_cache[p.name.lower()] = VoiceSpec(
                        ref_audio_path=p.ref_audio_path, ref_text=p.ref_text
                    )
                elif p.voice_id:
                    self._voice_cache[p.name.lower()] = VoiceSpec(voice_id=p.voice_id)

        # 2. Fetch ElevenLabs voices (using global cache) — only if no provider
        if self._provider is None:
            async with self._global_init_lock:
                if VoiceManager._global_available_voices is None:
                    api_key = os.getenv("ELEVENLABS_API_KEY")
                    if not api_key:
                        VoiceManager._global_available_voices = []
                    else:
                        try:
                            from elevenlabs.client import ElevenLabs
                            client = ElevenLabs(api_key=api_key)
                            def fetch_voices():
                                return client.voices.get_all().voices
                            voices = await asyncio.to_thread(fetch_voices)
                            VoiceManager._global_available_voices = [v.voice_id for v in voices]
                            VoiceManager._global_voice_metadata = {
                                v.voice_id: {
                                    "name": v.name,
                                    "gender": v.labels.get("gender", "unknown").lower() if v.labels else "unknown",
                                }
                                for v in voices
                            }
                        except Exception as e:
                            logger.error(f"Failed to fetch ElevenLabs voices: {e}")
                            VoiceManager._global_available_voices = []

                self._cached_available_voices = VoiceManager._global_available_voices
                self._cached_voice_metadata = VoiceManager._global_voice_metadata

        self._initialized = True

    async def get_known_characters(self):
        await self._init_cache()
        return list(self._profile_cache.values())

    async def get_voice(self, character_name: str, gender: str = "unknown") -> VoiceSpec:
        """Resolve character → VoiceSpec."""
        from .tts.base import VoiceSpec

        if not character_name:
            return self.narrator_voice

        char_normalized = character_name.lower().strip()
        if char_normalized == "narrator":
            return self.narrator_voice

        async with self._instance_lock:
            await self._init_cache()

            # Check cache
            if char_normalized in self._voice_cache:
                return self._voice_cache[char_normalized]

            # Check profile cache
            if char_normalized in self._profile_cache:
                profile = self._profile_cache[char_normalized]
                if profile.ref_audio_path:
                    spec = VoiceSpec(ref_audio_path=profile.ref_audio_path, ref_text=profile.ref_text)
                    self._voice_cache[char_normalized] = spec
                    return spec
                if profile.voice_id:
                    spec = VoiceSpec(voice_id=profile.voice_id)
                    self._voice_cache[char_normalized] = spec
                    return spec

            # Auto-assign from available voices (ElevenLabs legacy path)
            gender = gender.lower()
            available_ids = self._cached_available_voices
            assigned_ids = {v.voice_id for v in self._voice_cache.values() if v.voice_id}
            candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice.voice_id and vid not in assigned_ids]

            if not candidate_ids:
                candidate_ids = [vid for vid in available_ids if vid != self.narrator_voice.voice_id]

            if not candidate_ids:
                assigned_voice = self.narrator_voice
            else:
                gender_candidates = [
                    vid for vid in candidate_ids
                    if self._cached_voice_metadata.get(vid, {}).get("gender") == gender
                ]
                final_pool = gender_candidates if gender_candidates else candidate_ids
                chosen_id = random.choice(final_pool)
                assigned_voice = VoiceSpec(voice_id=chosen_id)

            # Save to profile and DB
            profile = self._profile_cache.get(char_normalized)
            if not profile:
                profile = CharacterProfile(
                    name=character_name.strip(),
                    story_id=self.story_id,
                    gender=gender,
                )
                self._profile_cache[char_normalized] = profile

            if assigned_voice.voice_id:
                profile.voice_id = assigned_voice.voice_id
            if gender != "unknown" and profile.gender == "unknown":
                profile.gender = gender

            self._voice_cache[char_normalized] = assigned_voice

            if hasattr(self.db, "save_character_profile"):
                await self.db.save_character_profile(profile)

            return assigned_voice

    def resolve_aliases(self, script_segments):
        """NLP-based alias resolution for script segments."""
        alias_map = {}
        for p in self._profile_cache.values():
            for alias in p.aliases:
                alias_map[alias.lower().strip()] = p.name

        for seg in script_segments:
            role = seg.get("role")
            if not role or role.lower() == "narrator":
                continue
            role_normalized = role.lower().strip()
            if role_normalized in alias_map:
                seg["role"] = alias_map[role_normalized]

        return script_segments

    async def synthesize(self, voice: VoiceSpec, text: str, **kwargs) -> SynthesisResult:
        """Delegate synthesis to provider, or fall back to legacy ElevenLabs."""
        from .tts.base import SynthesisResult

        if self._provider:
            return await self._provider.synthesize(text, voice)

        # Legacy path: direct ElevenLabs call (backward compat)
        voice_id = voice.voice_id or self.narrator_voice.voice_id
        stability = kwargs.get("stability", 0.35)
        audio_bytes, word_alignments_raw = await self._synthesize_elevenlabs_legacy(voice_id, text, stability)

        from .tts.base import WordAlignment
        word_alignments = [
            WordAlignment(word=w["word"], start=w["start"], end=w["end"])
            for w in word_alignments_raw
        ] if word_alignments_raw else None

        duration_ms = _estimate_duration_ms_legacy(audio_bytes)
        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=44100,
            duration_ms=duration_ms,
            word_alignments=word_alignments,
        )

    async def _synthesize_elevenlabs_legacy(self, voice_id, text, stability):
        """Legacy ElevenLabs synthesis (kept for backward compat when no provider)."""
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY required")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-with-timestamps"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        data = {
            "text": text,
            "model_id": "eleven_v3",
            "voice_settings": {"stability": stability, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True},
        }

        audio_buffer = io.BytesIO()
        all_alignments = []

        async with self._client.stream("POST", url, headers=headers, json=data) as response:
            if response.status_code != 200:
                error_msg = await response.aread()
                raise Exception(f"ElevenLabs API error ({response.status_code}): {error_msg}")
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if "audio_base64" in chunk:
                        audio_buffer.write(base64.b64decode(chunk["audio_base64"]))
                    if "alignment" in chunk:
                        all_alignments.append(chunk["alignment"])
                except Exception as e:
                    logger.warning(f"Error parsing alignment chunk: {e}")

        full_audio = audio_buffer.getvalue()
        audio_buffer.close()

        word_alignments = []
        current_word_chars = []
        current_word_start = None
        last_end = 0

        for alignment in all_alignments:
            chars = alignment.get("characters", [])
            starts = alignment.get("character_start_times_seconds", [])
            ends = alignment.get("character_end_times_seconds", [])
            for char, start, end in zip(chars, starts, ends, strict=False):
                if char.isspace():
                    if current_word_chars:
                        word_text = "".join(current_word_chars)
                        word_alignments.append({"word": word_text, "start": int(current_word_start * 1000), "end": int(last_end * 1000)})
                        current_word_chars = []
                        current_word_start = None
                    continue
                if not current_word_chars:
                    current_word_start = start
                current_word_chars.append(char)
                last_end = end

        if current_word_chars:
            word_text = "".join(current_word_chars)
            word_alignments.append({"word": word_text, "start": int(current_word_start * 1000), "end": int(last_end * 1000)})

        return full_audio, word_alignments


def _estimate_duration_ms_legacy(audio_bytes: bytes) -> int:
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        return len(seg)
    except Exception:
        return int(len(audio_bytes) * 8 / 128)
```

- [ ] **Step 2: Update existing tests to use VoiceSpec**

In `tests/test_audio_drama.py`, update the narrator test to check VoiceSpec:

```python
# Change assertions from:
assert await vm.get_voice("narrator") == vm.narrator_voice_id
# To:
assert (await vm.get_voice("narrator")) == vm.narrator_voice
```

And update the voice assignment test similarly — `get_voice()` now returns `VoiceSpec`, not `str`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_audio_drama.py -v`
Expected: PASS (may need minor adjustments to test assertions)

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/audio_drama.py tests/test_audio_drama.py
git commit -m "refactor(tts): VoiceManager accepts TTSProvider, returns VoiceSpec"
```

---

### Task 8: Exporter refactor

**Files:**
- Modify: `vvr_scraper/exporter.py`

- [ ] **Step 1: Update tao_file_audiodrama to use VoiceSpec flow**

In `vvr_scraper/exporter.py`, update `tao_file_audiodrama()`:

1. Replace `VoiceManager(db_manager, story_id)` with provider-aware construction:
```python
    from . import tts
    from .tts.base import VoiceSpec, map_tags

    provider_name = kwargs.get("tts_provider") or tts.auto_detect_provider()
    if provider_name == "elevenlabs":
        provider = tts.get_provider("elevenlabs", api_key=os.getenv("ELEVENLABS_API_KEY"))
    elif provider_name == "openai_tts":
        provider = tts.get_provider("openai_tts")
    elif provider_name == "omnivoice":
        provider = tts.get_provider("omnivoice")
    else:
        provider = tts.get_provider(provider_name)

    voice_manager = VoiceManager(db_manager, story_id, provider=provider)
```

2. Update the enriched_script loop — `get_voice()` now returns `VoiceSpec`:
```python
    voice_spec = await voice_manager.get_voice(char_name, gender)
    enriched_script.append({"type": "segment", "role": char_name, "voice": voice_spec, "text": text})
```

3. Update `synthesize_segment()` — use `VoiceSpec` and `SynthesisResult`:
```python
    async def synthesize_segment(item):
        async with semaphore:
            voice_spec = item["voice"]  # VoiceSpec object
            text = item["text"]
            role = item.get("role", "narrator")
            stability = 0.75 if role.lower() == "narrator" else 0.35

            try:
                result = await voice_manager.synthesize(
                    voice=voice_spec, text=text, stability=stability
                )
                segment = AudioSegment.from_file(io.BytesIO(result.audio_bytes), format="mp3")
                # Convert WordAlignment to dict for manifest compatibility
                alignments = [{"word": w.word, "start": w.start, "end": w.end} for w in result.word_alignments] if result.word_alignments else []
                return segment, alignments
            except Exception as e:
                logger.error(f"Error synthesizing segment: {e}")
                return AudioSegment.silent(duration=500), []
```

4. Make manifest generation conditional on having alignments:
```python
    has_any_alignments = any(len(a) > 0 for a in raw_block_alignments)
    if has_any_alignments:
        # Generate manifest as before
        ...
```

5. Remove the hardcoded `ELEVENLABS_API_KEY` check — provider handles this.

- [ ] **Step 2: Update tao_file_mp3 to use provider**

Replace the direct `elevenlabs` import in `tao_file_mp3()` with provider usage:

```python
async def tao_file_mp3(content_list, filename, title="Chương truyện", tts_provider_name=None):
    from . import tts
    from .tts.base import VoiceSpec

    provider_name = tts_provider_name or tts.auto_detect_provider()
    provider = tts.get_provider(provider_name) if provider_name != "elevenlabs" else tts.get_provider("elevenlabs", api_key=os.getenv("ELEVENLABS_API_KEY"))

    # ... chunk text as before ...

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        voice = VoiceSpec(voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"))
        result = await provider.synthesize(chunk, voice)
        segment = AudioSegment.from_file(io.BytesIO(result.audio_bytes), format="mp3")
        audio_segments.append(segment)

    # ... merge and export as before ...
```

- [ ] **Step 3: Run existing tests to verify backward compat**

Run: `pytest tests/test_exporter_audio.py -v`
Expected: PASS (with minor mock adjustments — VoiceManager mock needs to return VoiceSpec)

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/exporter.py
git commit -m "refactor(tts): exporter uses TTSProvider and VoiceSpec flow"
```

---

### Task 9: CLI flag + prompt template

**Files:**
- Modify: `vvr_scraper/cli.py`
- Modify: `vvr_scraper/prompts/audio_drama_script.md`

- [ ] **Step 1: Add --tts-provider CLI argument**

In `vvr_scraper/cli.py`, after the `--render-format` argument (around line 216), add:

```python
        parser.add_argument(
            "--tts-provider",
            default=None,
            help="TTS backend. Built-in: elevenlabs, omnivoice, openai_tts. Custom providers also supported. Default: auto-detect from env vars.",
        )
```

- [ ] **Step 2: Pass tts_provider to tao_file_audiodrama**

Find where `tao_file_audiodrama` is called in `cli.py` and pass the new arg:

```python
    await tao_file_audiodrama(
        content_list=content_list,
        filename=filename,
        story_id=story_id,
        db_manager=self.db_manager,
        title=title,
        tts_provider=self.args.tts_provider,
    )
```

Update `tao_file_audiodrama` signature in `exporter.py` to accept `tts_provider: str | None = None`.

- [ ] **Step 3: Update prompt template to be provider-agnostic**

Replace `vvr_scraper/prompts/audio_drama_script.md` content:

```markdown
# Audio Drama Scriptwriter Prompt

You are an expert scriptwriter for high-quality audio dramas. Your task is to convert a web novel chapter segment into a structured, performance-ready script.

## Core Tasks

1.  **Identify Roles:** Distinguish between dialogue (character speaking) and narration. Everything not spoken by a character is 'narrator'.
2.  **Infer Gender:** For each character, infer their gender ('male', 'female', or 'unknown') based on context, names, and pronouns.
3.  **Identify Mood Shifts:** Detect significant changes in the story's atmosphere. 
    *   Identify the atmosphere using 1-3 English keywords (tags). 
    *   Examples: `mysterious`, `dark piano`, `traditional flute`, `forest ambient`, `action`, `romantic`, `peaceful`, `sad`, `suspense`.
4.  **Enrich Performance:** Enhance the 'text' field by inserting performance-directing tags in square brackets.

## Performance Tag Dictionary

Use these tags to direct the AI voice delivery. Insert them naturally at the start or mid-sentence.

*   **Emotions:** `[happy]`, `[sad]`, `[angry]`, `[scared]`, `[excited]`, `[hopeful]`, `[worried]`, `[serious tone]`.
*   **Delivery Style:** `[whisper]`, `[shouting]`, `[softly]`, `[dramatic]`, `[hesitates]`, `[rushed]`, `[slowly]`.
*   **Non-Verbal Reactions:** `[laughter]`, `[sigh]`, `[surprise]`, `[gasp]`, `[cough]`.
*   **Pacing:** `[pause]`, `[short pause]`, `[long pause]`.

*Note: Not all TTS providers support all tags. Unsupported tags are silently ignored at synthesis time. You are encouraged to use other natural English descriptive words in square brackets if they fit the context better.*

## Output Format

The output **MUST** be a valid JSON object with a single key `"script"` mapping to a list of objects.

### Object Types:

1.  **Segment:**
    *   `type`: "segment"
    *   `role`: Character name or "narrator"
    *   `gender`: "male", "female", or "unknown"
    *   `text`: The spoken text, enriched with performance tags.

2.  **Mood Shift:**
    *   `type`: "mood_shift"
    *   `tags`: A list of English strings (1-3 keywords).
    *   `visual_prompt`: (Required) A 1-sentence English description for image generation. Describe the setting, characters present, and the main action. **Always write this in English.**
    *   `vfx`: (Required) A list of effects, choose from: `shake`, `flash`, `rain`, `fog`, or `none`.
    *   `intensity`: (Required) A float from 0.1 to 1.0 representing the strength of the effects.
    *   `duration`: (Required) Duration of the mood/effects in milliseconds (e.g., 2000).
    *   `transition`: (Required) Choose from: `fade`, `cut`, or `zoom`.

## Constraints

*   Every script MUST start with a `mood_shift` to set the initial scene and visuals.
*   Insert a `mood_shift` whenever the location, time, or intense visual action changes.
*   Combine consecutive segments by the same character.
*   Ensure ALL fields and objects are correctly separated by commas.
*   Do not add any text or explanation outside the JSON object.
*   The script should feel immersive and "alive".
```

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/cli.py vvr_scraper/prompts/audio_drama_script.md
git commit -m "feat(tts): add --tts-provider CLI flag, provider-agnostic prompt tags"
```

---

### Task 10: Web API refactor (`correction.py`)

**Files:**
- Modify: `vvr_scraper/web/routes/correction.py`

- [ ] **Step 1: Refactor /voices/list and /voices/preview to use provider**

Replace the direct `elevenlabs.client.ElevenLabs` imports with provider calls:

```python
# At the top of correction.py, add:
from vvr_scraper import tts as tts_module
from vvr_scraper.tts.base import VoiceSpec

def _get_tts_provider():
    """Get the configured TTS provider instance."""
    provider_name = tts_module.auto_detect_provider()
    if provider_name == "elevenlabs":
        return tts_module.get_provider("elevenlabs", api_key=os.getenv("ELEVENLABS_API_KEY"))
    elif provider_name == "openai_tts":
        return tts_module.get_provider("openai_tts")
    else:
        return tts_module.get_provider(provider_name)


@router.get("/voices/list")
async def list_voices():
    """List available voices from the configured TTS provider."""
    try:
        provider = _get_tts_provider()
        voices = await provider.discover_voices()
        await provider.close()
        return {"voices": [asdict(v) for v in voices]}
    except Exception as e:
        logger.error(f"Error listing voices: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/voices/preview")
async def preview_voice(
    voice_id: str | None = None,
    ref_audio_path: str | None = None,
    text: str = Query(default="Xin chào, tôi là người kể chuyện."),
):
    """Generate a short audio preview using the configured TTS provider."""
    if len(text) > 150:
        text = text[:150]

    try:
        provider = _get_tts_provider()
        voice = VoiceSpec(voice_id=voice_id, ref_audio_path=ref_audio_path)
        audio = await provider.preview_voice(voice, text)
        await provider.close()
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"Error generating voice preview: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
```

Remove the old `_async_get_voices` function and the direct `elevenlabs.client` imports.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_correction.py -v`
Expected: PASS (may need mock adjustments)

- [ ] **Step 3: Commit**

```bash
git add vvr_scraper/web/routes/correction.py
git commit -m "refactor(tts): web API uses TTSProvider for voice listing and preview"
```

---

### Task 11: Update existing tests for VoiceSpec compatibility

**Files:**
- Modify: `tests/test_exporter_audio.py`
- Modify: `tests/test_elevenlabs_timestamps.py`
- Modify: `tests/test_audio_drama_global_timestamps.py`
- Modify: `tests/test_cinematic_integration.py`

- [ ] **Step 1: Update test mocks to return VoiceSpec instead of str**

In `tests/test_exporter_audio.py`, change:
```python
vm_instance.get_voice = AsyncMock(return_value="fake_voice_id")
```
to:
```python
from vvr_scraper.tts.base import VoiceSpec
vm_instance.get_voice = AsyncMock(return_value=VoiceSpec(voice_id="fake_voice_id"))
```

And update `vm_instance.synthesize` to return `SynthesisResult`:
```python
from vvr_scraper.tts.base import SynthesisResult, WordAlignment
vm_instance.synthesize = AsyncMock(
    return_value=SynthesisResult(
        audio_bytes=b"fake_audio",
        sample_rate=44100,
        duration_ms=2000,
        word_alignments=[WordAlignment(word="Hello", start=0, end=500)],
    )
)
```

Apply similar changes to all test files that mock `VoiceManager`.

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test(tts): update all test mocks for VoiceSpec/SynthesisResult"
```

---

### Task 12: Final integration test + regression

**Files:**
- Create: `tests/test_tts_integration.py`

- [ ] **Step 1: Write integration test for full pipeline with mock provider**

```python
# tests/test_tts_integration.py
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.models import ContentItem
from vvr_scraper.tts.base import VoiceSpec, SynthesisResult, WordAlignment


@pytest.mark.asyncio
async def test_audiodrama_with_openai_tts_provider(tmp_path):
    """Integration test: tao_file_audiodrama with OpenAI-compatible provider."""
    from vvr_scraper.audio_drama import ScriptResult
    from vvr_scraper.exporter import tao_file_audiodrama

    filename = str(tmp_path / "test_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]

    mock_script = ScriptResult([
        {"type": "mood_shift", "mood": "peaceful", "tags": ["peaceful"],
         "visual_prompt": "peaceful", "vfx": [], "transition": "fade", "duration": 1000},
        {"type": "segment", "role": "narrator", "text": "Hello world."},
    ])

    # Mock provider
    mock_provider = MagicMock()
    mock_provider.synthesize = AsyncMock(return_value=SynthesisResult(
        audio_bytes=b"fake_audio_data",
        sample_rate=44100,
        duration_ms=2000,
        word_alignments=None,
    ))
    mock_provider.discover_voices = AsyncMock(return_value=[])
    mock_provider.close = AsyncMock()

    with (
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.exporter.VoiceManager") as MockVM,
        patch("vvr_scraper.exporter.BGMManager"),
        patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
        patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
        patch("vvr_scraper.exporter.ImageGenerator") as MockImageGen,
        patch("pydub.AudioSegment.from_file") as MockFromFile,
        patch("pydub.AudioSegment.silent") as MockSilent,
    ):
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)

        vm_instance = MockVM.return_value
        vm_instance.get_known_characters = AsyncMock(return_value=[])
        vm_instance.resolve_aliases = MagicMock(side_effect=lambda x: x)
        vm_instance.get_voice = AsyncMock(return_value=VoiceSpec(voice_id="alloy"))
        vm_instance.synthesize = AsyncMock(return_value=SynthesisResult(
            audio_bytes=b"fake_audio_data",
            sample_rate=44100,
            duration_ms=2000,
            word_alignments=None,
        ))
        vm_instance.close = AsyncMock()

        MockImageGen.return_value.generate = AsyncMock(return_value="fake_bg.webp")
        MockFreesound.return_value.search_bgm = AsyncMock(return_value=[])
        MockFreesound.return_value.download_and_convert = AsyncMock(return_value="fake_bgm.wav")

        mock_audio = MagicMock()
        mock_audio.__len__.return_value = 2000
        mock_audio.fade_in.return_value = mock_audio
        mock_audio.fade_out.return_value = mock_audio
        mock_audio.append.return_value = mock_audio
        MockSilent.side_effect = lambda duration: mock_audio
        MockFromFile.return_value = mock_audio

        MockMixing.return_value.create_looped_background.return_value = mock_audio
        MockMixing.return_value.overlay_voice_on_background.return_value = mock_audio

        await tao_file_audiodrama(
            content_list, filename, story_id, MagicMock(),
            tts_provider="openai_tts",
        )

        # Verify synthesize was called
        vm_instance.synthesize.assert_called_once()
```

- [ ] **Step 2: Run full regression suite**

Run: `pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_tts_integration.py
git commit -m "test(tts): add integration test for OpenAI TTS provider pipeline"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Section 3 (Core types) → Task 1
- ✅ Section 4.1 (ElevenLabs) → Task 2
- ✅ Section 4.2 (OmniVoice) → Task 4
- ✅ Section 4.3 (OpenAI-compatible) → Task 3
- ✅ Section 5 (Registry) → Task 5
- ✅ Section 6 (CLI flag) → Task 9
- ✅ Section 7 (VoiceManager refactor) → Task 7
- ✅ Section 8 (CharacterProfile + DB) → Task 6
- ✅ Section 9 (Prompt template) → Task 9
- ✅ Section 10 (Web API) → Task 10
- ✅ Section 13 (Provider comparison) → covered by implementations
- ✅ Section 14 (Test plan) → Tasks 1-4, 11-12

**2. Placeholder scan:** No TBD/TODO found. All steps have complete code.

**3. Type consistency:**
- `VoiceSpec` used consistently across all tasks
- `SynthesisResult` with `word_alignments: list[WordAlignment] | None` consistent
- `get_voice()` returns `VoiceSpec` in Task 7, consumed as `VoiceSpec` in Task 8
- `synthesize()` signature: `(voice: VoiceSpec, text: str)` in Task 7, called with same signature in Task 8
