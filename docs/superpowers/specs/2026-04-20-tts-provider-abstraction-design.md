# Spec: TTS Provider Abstraction

## 1. Overview

Tách ElevenLabs coupling khỏi audio drama pipeline bằng cách introduce `TTSProvider` Protocol — một abstraction layer cho phép swap/combine TTS backends (ElevenLabs, OmniVoice, OpenAI-compatible HTTP, hoặc custom). Đồng thời thêm voice sample library cho OmniVoice voice cloning, và `--tts-provider` CLI flag cho user chọn backend.

### 1.1. Goals

- **Decouple**: Xóa hard dependency trên ElevenLabs SDK/HTTP API khỏi `VoiceManager`, `exporter.py`, `correction.py`
- **Extensible**: Developer thêm custom TTS provider bằng implement 1 Protocol + register
- **Voice library**: User tạo thư mục voice samples cho từng nhân vật → OmniVoice voice cloning
- **CLI control**: `--tts-provider` flag chọn backend tại runtime

### 1.2. Non-goals

- Timestamp generation cho OmniVoice (word_alignments là optional, chỉ cần cho MP4 manifest)
- Voice design mode của OmniVoice làm default (cloning luôn ưu tiên hơn)
- Multi-provider trong 1 session (1 provider per run)

---

## 2. Architecture

### 2.1. Module structure

```
vvr_scraper/
├── tts/
│   ├── __init__.py               # Provider registry + factory + auto-detect
│   ├── base.py                   # TTSProvider Protocol, VoiceSpec, SynthesisResult, VoiceInfo
│   ├── elevenlabs_provider.py    # ElevenLabs implementation
│   ├── omnivoice_provider.py     # OmniVoice local model implementation
│   └── openai_tts_provider.py    # OpenAI-compatible HTTP TTS implementation
├── audio_drama.py                # VoiceManager (refactored: uses TTSProvider)
├── exporter.py                   # tao_file_audiodrama / tao_file_mp3 (refactored)
├── models.py                     # CharacterProfile (extended: ref_audio_path, ref_text)
├── db.py                         # Migration: add columns
├── prompts/audio_drama_script.md # Provider-agnostic performance tags
└── cli.py                        # --tts-provider flag
```

### 2.2. Data flow

```
User input (chapter text)
       │
       ▼
  OpenAIParser.parse_chapter()
       │
       ▼
  ScriptResult (segments + mood_shifts)
       │
       ▼
  VoiceManager.get_voice(char_name, gender)
       │  ← checks DB for assigned voice (ref_audio_path or voice_id)
       │  ← falls back to narrator voice
       ▼
  VoiceSpec (provider-agnostic descriptor)
       │
       ▼
   TTSProvider.synthesize(text, voice_spec)
       │
       ├── ElevenLabsProvider    → HTTP API, returns SynthesisResult with word_alignments
       ├── OmniVoiceProvider     → local model.generate(), returns SynthesisResult without word_alignments
       └── OpenAITTSProvider     → HTTP /v1/audio/speech, returns SynthesisResult without word_alignments
       │
       ▼
  MixingEngine (unchanged)
       │
       ▼
  Final audio + optional manifest
```

### 2.3. Voice assignment flow

```
1. LLM parse chapter → discover characters
2. Check DB: character already has voice assigned? → skip
3. If not: prompt user "Gán voice cho [character]?"
   → User provides folder path (e.g., voices/nam_chinh/)
   → Auto-detect sample.wav + transcript.txt
   → Save to CharacterProfile in DB
4. Synthesize: OmniVoice uses ref_audio, ElevenLabs uses voice_id, OpenAI-compatible uses voice name
```

---

## 3. Core types (`tts/base.py`)

```python
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
    instruct: str | None = None  # "female, low pitch, british accent"

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
    # Optional — only populated by providers that support it (ElevenLabs).
    # When None, manifest generation is skipped for this segment.
    word_alignments: list[WordAlignment] | None = None


@dataclass
class VoiceInfo:
    """Metadata about a discovered/available voice."""

    voice_id: str | None = None      # ElevenLabs UUID; None for local samples
    name: str = ""
    gender: str = "unknown"
    ref_audio_path: str | None = None  # OmniVoice sample path
    labels: dict = field(default_factory=dict)  # Provider-specific metadata


@runtime_checkable
class TTSProvider(Protocol):
    """Interface that any TTS backend must implement.

    To add a custom provider:
    1. Create a class implementing these 4 methods
    2. Call tts.register("my_provider", MyProvider) before use
    3. Pass --tts-provider my_provider on CLI (or set VVR_TTS_PROVIDER env var)

    See docs/tts-providers.md for full guide.
    """

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize speech from text using the given voice specification.

        Args:
            text: The text to speak.
            voice: Voice specification (clone, voice_id, or design mode).

        Returns:
            SynthesisResult with audio_bytes always populated.
            word_alignments is optional (None if provider doesn't support it).
        """
        ...

    async def discover_voices(self) -> list[VoiceInfo]:
        """List available voices for this provider.

        ElevenLabs: queries cloud API for user's voice library.
        OmniVoice: scans local voices/ directories for sample files.
        """
        ...

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        """Generate a short audio preview for voice selection UI.

        Args:
            voice: Voice specification to preview.
            text: Short preview text (max ~150 chars).

        Returns:
            Raw audio bytes (MP3 or WAV depending on provider).
        """
        ...

    async def close(self) -> None:
        """Release resources (HTTP clients, GPU memory, etc.)."""
        ...
```

---

## 4. Provider implementations

### 4.1. ElevenLabs Provider (`tts/elevenlabs_provider.py`)

Extracted from current `VoiceManager.synthesize()`, `tao_file_mp3()`, `correction.py`.

```python
class ElevenLabsProvider:
    """TTSProvider implementation for ElevenLabs cloud API."""

    def __init__(self, api_key: str):
        from elevenlabs.client import ElevenLabs
        self._client = ElevenLabs(api_key=api_key)
        self._api_key = api_key

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        # Uses stream-with-timestamps endpoint (existing logic from VoiceManager.synthesize)
        # Returns SynthesisResult with word_alignments populated
        ...

    async def discover_voices(self) -> list[VoiceInfo]:
        # Wraps client.voices.get_all() (existing logic from VoiceManager._init_cache)
        ...

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        # Wraps client.generate() (existing logic from correction.py preview_voice)
        ...

    async def close(self) -> None:
        pass  # HTTP client cleanup if needed
```

Key: `synthesize()` preserves the existing `stream-with-timestamps` logic and word-level alignment parsing. This is the only provider that populates `word_alignments`.

### 4.2. OmniVoice Provider (`tts/omnivoice_provider.py`)

```python
class OmniVoiceProvider:
    """TTSProvider implementation for OmniVoice local model."""

    def __init__(self, model_name: str = "k2-fsa/OmniVoice", device: str = "cuda:0"):
        from omnivoice import OmniVoice
        self._model = OmniVoice.from_pretrained(
            model_name, device_map=device, dtype=torch.float16
        )
        self._model.load_asr_model()  # For auto-transcription of ref_audio

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        # Priority: ref_audio (clone) > instruct (design) > auto
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

        # Convert np.ndarray (24kHz) → WAV bytes
        import io, soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, audio_np[0], self._model.sampling_rate, format="WAV")
        audio_bytes = buf.getvalue()
        duration_ms = int(len(audio_np[0]) / self._model.sampling_rate * 1000)

        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=self._model.sampling_rate,
            duration_ms=duration_ms,
            word_alignments=None,  # OmniVoice doesn't provide timestamps
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        # Scan story's voices/ directory for sample.wav files
        ...

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        result = await self.synthesize(text, voice)
        return result.audio_bytes

    async def close(self) -> None:
        # Release GPU memory if needed
        del self._model
        torch.cuda.empty_cache()
```

### 4.3. OpenAI-Compatible HTTP Provider (`tts/openai_tts_provider.py`)

Universal HTTP client cho bất kỳ server nào implement OpenAI `/v1/audio/speech` endpoint. Bao gồm:
- OpenAI TTS chính chủ (`tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`)
- `omnivoice-server` (community project, expose OmniVoice qua OpenAI-compatible API)
- Azure OpenAI TTS
- LocalAI, Ollama TTS extensions
- Bất kỳ self-hosted server nào clone OpenAI API

```python
class OpenAITTSProvider:
    """TTSProvider implementation for OpenAI-compatible HTTP /v1/audio/speech endpoint."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "tts-1",
        default_voice: str = "alloy",
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=60.0,
        )

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        # Map VoiceSpec → OpenAI voice param
        # voice_id mode: use voice.voice_id as voice name (e.g., "alloy", "echo")
        # clone mode: not in standard API — skip ref_audio, use default_voice
        # design mode: not in standard API — skip instruct, use default_voice
        # auto mode: use default_voice
        voice_name = voice.voice_id or self._default_voice

        response = await self._client.post(
            "/audio/speech",
            json={
                "model": self._model,
                "input": text,
                "voice": voice_name,
                "response_format": "mp3",  # or "wav", "opus", "aac"
            },
        )
        response.raise_for_status()
        audio_bytes = response.content

        # Estimate duration from audio bytes (parse with pydub)
        from pydub import AudioSegment
        import io
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        duration_ms = len(seg)

        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=seg.frame_rate,
            duration_ms=duration_ms,
            word_alignments=None,  # OpenAI API doesn't provide timestamps
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        # OpenAI has fixed voice names; custom servers may have /v1/voices endpoint
        # Try GET /v1/voices first, fall back to hardcoded list
        try:
            response = await self._client.get("/voices")
            if response.status_code == 200:
                data = response.json()
                return [
                    VoiceInfo(voice_id=v["id"], name=v.get("name", v["id"]))
                    for v in data.get("voices", data if isinstance(data, list) else [])
                ]
        except httpx.HTTPError:
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
```

#### 4.3.1. Why this provider matters

| Scenario | How to use |
|----------|-----------|
| OpenAI cloud TTS | `--tts-provider openai_tts` + `OPENAI_TTS_API_KEY=sk-...` |
| OmniVoice without local GPU | Run `omnivoice-server` → `--tts-provider openai_tts` + `OPENAI_TTS_BASE_URL=http://localhost:8001/v1` |
| Azure OpenAI | `OPENAI_TTS_BASE_URL=https://YOUR_RESOURCE.openai.azure.com/openai/` + API key |
| LocalAI | `OPENAI_TTS_BASE_URL=http://localhost:8080/v1` |
| Custom server | Any server implementing `POST /v1/audio/speech` |

This provider is the **lightest-weight** option — only requires `httpx`, no GPU, no heavy SDK. It also serves as the bridge for users who want OmniVoice quality without managing a local model.

#### 4.3.2. Environment variables

```bash
OPENAI_TTS_BASE_URL=https://api.openai.com/v1   # Server base URL
OPENAI_TTS_API_KEY=sk-...                        # API key (Bearer auth)
OPENAI_TTS_MODEL=tts-1                           # Model name
OPENAI_TTS_DEFAULT_VOICE=alloy                   # Default voice name
```

---

## 5. Provider registry (`tts/__init__.py`)

```python
_registry: dict[str, type] = {}


def register(name: str, provider_cls: type) -> None:
    """Register a TTS provider class under the given name."""
    _registry[name] = provider_cls


def get_provider(name: str, **kwargs) -> TTSProvider:
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


# Auto-register built-in providers (lazy — only if deps available)
def _register_builtins():
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

    # openai_tts always available (only needs httpx, which is already a dependency)
    from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider
    register("openai_tts", OpenAITTSProvider)

_register_builtins()
```

---

## 6. CLI flag (`--tts-provider`)

### 6.1. CLI argument

In `cli.py`, add to the export/audio-drama argument group:

```python
parser.add_argument(
    "--tts-provider",
    default=None,
    help="TTS backend to use. Built-in: elevenlabs, omnivoice, openai_tts. Custom providers can also be specified. Default: auto-detect from env vars.",
)
```

Note: No `choices` constraint — allows custom provider names registered via `tts.register()`.

### 6.2. Environment variable fallback

```python
VVR_TTS_PROVIDER=omnivoice  # Override auto-detect
```

Priority: `--tts-provider` CLI arg > `VVR_TTS_PROVIDER` env var > `ELEVENLABS_API_KEY` / `OPENAI_TTS_API_KEY` auto-detect.

### 6.3. Provider instantiation in pipeline

```python
# In exporter.py or job_runner.py
from vvr_scraper import tts

provider_name = args.tts_provider or tts.auto_detect_provider()

if provider_name == "elevenlabs":
    provider = tts.get_provider("elevenlabs", api_key=os.getenv("ELEVENLABS_API_KEY"))
elif provider_name == "omnivoice":
    provider = tts.get_provider("omnivoice", device=os.getenv("VVR_OMNIVOICE_DEVICE", "cuda:0"))
elif provider_name == "openai_tts":
    provider = tts.get_provider("openai_tts",
        base_url=os.getenv("OPENAI_TTS_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("OPENAI_TTS_API_KEY"),
        model=os.getenv("OPENAI_TTS_MODEL", "tts-1"),
        default_voice=os.getenv("OPENAI_TTS_DEFAULT_VOICE", "alloy"),
    )
```

---

## 7. VoiceManager refactor (`audio_drama.py`)

### 7.1. Before (current)

`VoiceManager` manages voice assignment AND directly calls ElevenLabs API. Returns `voice_id: str` (ElevenLabs UUID). `synthesize()` hardcodes HTTP call to `api.elevenlabs.io`.

### 7.2. After

`VoiceManager` only manages voice assignment. Returns `VoiceSpec` (provider-agnostic). Delegates synthesis to injected `TTSProvider`.

```python
class VoiceManager:
    DEFAULT_NARRATOR_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # 11Labs default (kept for backward compat)

    def __init__(self, db, story_id: str, provider: TTSProvider):
        self._provider = provider
        self._db = db
        self._story_id = story_id
        self._voice_cache: dict[str, VoiceSpec] = {}  # char_name -> VoiceSpec
        self.narrator_voice = self._build_narrator_voice()

    def _build_narrator_voice(self) -> VoiceSpec:
        """Build narrator VoiceSpec from env config."""
        narrator_ref = os.getenv("VVR_NARRATOR_REF_AUDIO")
        if narrator_ref:
            return VoiceSpec(ref_audio_path=narrator_ref)
        narrator_id = os.getenv("VVR_NARRATOR_VOICE_ID", self.DEFAULT_NARRATOR_VOICE_ID)
        return VoiceSpec(voice_id=narrator_id)

    async def get_voice(self, character_name: str, gender: str = "unknown") -> VoiceSpec:
        """Resolve character → VoiceSpec."""
        # 1. Check cache
        # 2. Check DB CharacterProfile (ref_audio_path or voice_id)
        # 3. Auto-assign from provider's available voices
        # 4. Fallback to narrator voice
        ...

    async def synthesize(self, voice: VoiceSpec, text: str, **kwargs) -> SynthesisResult:
        """Delegate to provider."""
        return await self._provider.synthesize(text, voice)
```

### 7.3. Key change: `get_voice()` returns `VoiceSpec` not `str`

This is the most impactful refactor. Currently `get_voice()` returns a string voice_id, and `tao_file_audiodrama()` passes it as `voice_id=voice_name` to `VoiceManager.synthesize()`. After refactor, the full `VoiceSpec` flows through, and the provider decides how to interpret it.

---

## 8. CharacterProfile + DB migration

### 8.1. Model extension (`models.py`)

```python
@dataclass
class CharacterProfile:
    name: str
    story_id: str
    aliases: list[str] = field(default_factory=list)
    gender: str = "unknown"
    voice_id: str | None = None           # Existing: ElevenLabs UUID
    ref_audio_path: str | None = None     # NEW: path to voice sample file
    ref_text: str | None = None           # NEW: transcript of voice sample
    personality: str | None = None
    speaking_style: str | None = None
    emotion_range: str | None = None
    color: str | None = None
```

### 8.2. DB migration (`db.py`)

```sql
ALTER TABLE character_profiles ADD COLUMN ref_audio_path TEXT;
ALTER TABLE character_profiles ADD COLUMN ref_text TEXT;
```

Migration is additive — no data loss. Existing `voice_id` values continue to work.

### 8.3. Voice sample directory convention

```
<story_output_folder>/
├── voices/
│   ├── narrator/
│   │   ├── sample.wav          # 3-10s reference audio (24kHz+ recommended)
│   │   └── transcript.txt      # Optional: transcript (auto-generated if missing)
│   ├── nam_chinh/
│   │   ├── sample.wav
│   │   └── transcript.txt
│   └── nu_phu/
│       ├── sample.wav
│       └── transcript.txt
├── backgrounds/
├── bgm/
└── manifest.json
```

When user assigns a voice folder to a character:
1. Scan folder for `sample.wav` (or `.mp3`, `.flac` — auto-detect first audio file)
2. Check for `transcript.txt` — if missing, OmniVoice auto-transcribes via Whisper
3. Save `ref_audio_path` and `ref_text` to `CharacterProfile` in DB

---

## 9. Prompt template refactor (`prompts/audio_drama_script.md`)

### 9.1. Before

References "ElevenLabs v3 Audio Tags" specifically: `[whispers]`, `[pause]`, `[laughs]`.

### 9.2. After

Provider-agnostic tag set with mapping layer:

```markdown
## Performance Tags
Use these inline tags in dialogue text to add expression:
- [laughter] — laugh sound
- [sigh] — sigh sound
- [surprise] — surprise exclamation
- [whisper] — whispered speech
- [pause] — brief pause

Note: Not all TTS providers support all tags. Unsupported tags are silently ignored at synthesis time.
```

### 9.3. Tag mapping (`tts/base.py`)

```python
# Provider-agnostic tag → provider-specific tag
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
    "[whisper]": "[whisper]",  # via instruct mode, not inline
    "[pause]": "...",
}

OPENAI_TTS_TAG_MAP: dict[str, str] = {
    # OpenAI TTS doesn't support inline performance tags — strip them all
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
```

---

## 10. Web API refactor (`correction.py`)

### 10.1. Before

`/voices/list` and `/voices/preview` directly import `elevenlabs.client.ElevenLabs`.

### 10.2. After

Use injected `TTSProvider` instance:

```python
@router.get("/voices/list")
async def list_voices(provider: TTSProvider = Depends(get_tts_provider)):
    voices = await provider.discover_voices()
    return {"voices": [asdict(v) for v in voices]}


@router.get("/voices/preview")
async def preview_voice(
    voice_id: str | None = None,
    ref_audio_path: str | None = None,
    text: str = Query(default="Xin chào, tôi là người kể chuyện."),
    provider: TTSProvider = Depends(get_tts_provider),
):
    voice = VoiceSpec(voice_id=voice_id, ref_audio_path=ref_audio_path)
    audio = await provider.preview_voice(voice, text)
    return Response(content=audio, media_type="audio/mpeg")
```

---

## 11. Developer guide: Adding a custom TTS provider

### 11.1. Steps

1. Create `vvr_scraper/tts/my_provider.py`:

```python
from vvr_scraper.tts.base import TTSProvider, VoiceSpec, SynthesisResult, VoiceInfo


class MyProvider:
    """Custom TTS provider implementation."""

    def __init__(self, api_key: str | None = None, **kwargs):
        # Initialize your TTS client/model here
        self._client = ...
        pass

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        # 1. Interpret voice.mode to decide how to select voice
        # 2. Call your TTS API/model
        # 3. Return SynthesisResult (word_alignments is optional)
        audio_bytes = ...
        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=24000,
            duration_ms=...,
            word_alignments=None,  # Set if your provider supports timestamps
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        # Return available voices from your backend
        return []

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        # Quick preview — can reuse synthesize() with shorter text
        result = await self.synthesize(text, voice)
        return result.audio_bytes

    async def close(self) -> None:
        # Cleanup resources
        pass
```

2. Register it before pipeline runs:

```python
from vvr_scraper import tts
from vvr_scraper.tts.my_provider import MyProvider

tts.register("my_provider", MyProvider)
```

3. Use it:

```bash
# Via CLI
vvrt export novel-slug --tts-provider my_provider

# Via env var
VVR_TTS_PROVIDER=my_provider vvrt export novel-slug

# Programmatically
provider = tts.get_provider("my_provider", api_key="...")
```

### 11.2. VoiceSpec interpretation guide

| `voice.mode` | Meaning | Your synthesize should |
|--------------|---------|----------------------|
| `"clone"` | User provided a voice sample | Use `voice.ref_audio_path` + `voice.ref_text` for voice cloning |
| `"voice_id"` | Pre-registered voice ID | Use `voice.voice_id` to look up a voice in your system |
| `"design"` | Text description of desired voice | Use `voice.instruct` to generate a matching voice |
| `"auto"` | No voice preference | Pick a default voice |

### 11.3. Tag mapping

If your provider supports inline performance tags, add a tag map in `tts/base.py`:

```python
MY_PROVIDER_TAG_MAP: dict[str, str] = {
    "[laughter]": "<laugh>",
    "[sigh]": "<sigh>",
    "[pause]": "<break>",
    # ...
}
```

And register it in the `map_tags()` function.

If your provider does **not** support inline tags (like OpenAI TTS), map them to empty strings to strip them:

```python
MY_PROVIDER_TAG_MAP: dict[str, str] = {
    "[laughter]": "",
    "[sigh]": "",
    "[surprise]": "",
    "[whisper]": "",
    "[pause]": "...",
}
```

### 11.4. Reference: OpenAI-compatible provider as a template

The `OpenAITTSProvider` is the simplest built-in provider (~80 lines, only httpx dependency). It serves as the best template for custom providers because:

- Pure HTTP client — no SDK, no GPU, no heavy deps
- Shows how to handle `VoiceSpec.mode` mapping (only `voice_id` mode is used, others fall back to `default_voice`)
- Shows `discover_voices()` with graceful fallback (try API endpoint → fall back to hardcoded list)
- Shows tag stripping for providers that don't support inline tags

---

## 12. Impact summary

| Component | Change type | Description |
|-----------|------------|-------------|
| `tts/base.py` | **NEW** | Protocol + types + tag mapping |
| `tts/elevenlabs_provider.py` | **NEW** | Extract from VoiceManager + exporter + correction |
| `tts/omnivoice_provider.py` | **NEW** | OmniVoice local model wrapper |
| `tts/openai_tts_provider.py` | **NEW** | OpenAI-compatible HTTP TTS wrapper |
| `tts/__init__.py` | **NEW** | Registry + factory + auto-detect |
| `audio_drama.py` VoiceManager | **REFACTOR** | Accept TTSProvider, return VoiceSpec instead of str |
| `audio_drama.py` OpenAIParser | **NO CHANGE** | Unaffected |
| `audio_drama.py` ScriptResult | **NO CHANGE** | Unaffected |
| `exporter.py` tao_file_audiodrama | **REFACTOR** | Use VoiceSpec flow, optional manifest |
| `exporter.py` tao_file_mp3 | **REFACTOR** | Use ElevenLabsProvider |
| `correction.py` /voices/* | **REFACTOR** | Use provider.discover_voices() / preview_voice() |
| `models.py` CharacterProfile | **EXTEND** | Add ref_audio_path, ref_text |
| `db.py` | **MIGRATE** | Add 2 columns (additive, no data loss) |
| `prompts/audio_drama_script.md` | **REFACTOR** | Provider-agnostic tags |
| `cli.py` | **EXTEND** | --tts-provider flag |
| Tests | **UPDATE** | Mock TTSProvider instead of elevenlabs directly |

---

## 13. Provider comparison

| | ElevenLabs | OmniVoice (local) | OpenAI-compatible |
|---|---|---|---|
| Deployment | Cloud SaaS | Local GPU | HTTP anywhere |
| Timestamps | ✅ `word_alignments` | ❌ | ❌ |
| Voice cloning | ❌ (voice_id only) | ✅ (ref_audio) | ⚠️ (server-dependent, e.g., omnivoice-server) |
| Latency | ~300ms | ~2-5s (GPU) | Server-dependent |
| Cost | $/char | Free (GPU) | Server-dependent |
| Dependencies | elevenlabs SDK | torch + omnivoice | httpx only |
| Performance tags | ✅ (rich set) | ✅ (limited set) | ❌ (stripped) |
| Best for | Production cloud, MP4 manifest | Offline, voice cloning | Lightweight, self-hosted, bridge to OmniVoice |

---

## 14. Test plan

- **Unit**: Each provider's `synthesize()` with mock HTTP/local model
- **Unit**: `VoiceSpec.mode` property for all 4 modes
- **Unit**: `map_tags()` for all 3 providers (including OpenAI tag stripping)
- **Unit**: Registry `register()` / `get_provider()` / `auto_detect_provider()`
- **Unit**: `OpenAITTSProvider.discover_voices()` — fallback from /voices endpoint to hardcoded list
- **Integration**: `tao_file_audiodrama()` with `ElevenLabsProvider` mock (existing tests adapted)
- **Integration**: `tao_file_audiodrama()` with `OmniVoiceProvider` mock (new)
- **Integration**: `tao_file_audiodrama()` with `OpenAITTSProvider` mock (new)
- **Integration**: Voice assignment flow (folder → CharacterProfile → VoiceSpec)
- **Regression**: Existing test suite passes with ElevenLabsProvider (backward compat)
