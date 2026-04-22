# TTS Provider Abstraction

## Section 1: Overview

The TTS Provider Abstraction layer decouples audio synthesis from ElevenLabs. This allows the system to work with multiple text-to-speech backends without changing the core audio pipeline code.

The current implementation includes three built-in providers:

- **ElevenLabs** — cloud API with word-level timing and performance tags
- **OmniVoice** — local PyTorch model for voice cloning
- **OpenAI-compatible HTTP** — generic endpoint for any server exposing `/v1/audio/speech`

The abstraction uses provider-agnostic types that travel through the pipeline:

- `VoiceSpec` — describes how to synthesize (voice ID, clone reference, design instructions)
- `SynthesisResult` — contains audio bytes, sample rate, duration, and optional word alignments
- `WordAlignment` — word-level timestamp data for lip-sync and subtitle generation

A tag mapping system converts generic performance tags (like `[laughter]`) into provider-specific equivalents. This keeps prompts portable across different backends.

## Section 2: Provider Configuration

### Environment Variables

| Variable | Provider | Required | Description |
|----------|----------|----------|-------------|
| `ELEVENLABS_API_KEY` | elevenlabs | Yes | ElevenLabs cloud API key |
| `VVR_TTS_PROVIDER` | all | No | Explicit provider override (`elevenlabs`, `omnivoice`, `openai_tts`) |
| `OPENAI_TTS_API_KEY` | openai_tts | Yes* | API key for OpenAI-compatible server |
| `OPENAI_TTS_BASE_URL` | openai_tts | No* | Custom base URL (default: `https://api.openai.com/v1`) |
| `OMNIVOICE_MODEL_PATH` | omnivoice | Yes | Path to OmniVoice model checkpoint |

*For openai_tts: either `OPENAI_TTS_API_KEY` or `OPENAI_TTS_BASE_URL` must be set

### Auto-Detection Logic

When `VVR_TTS_PROVIDER` is not set, the system detects the provider in this order:

1. If `VVR_TTS_PROVIDER` is set explicitly, use that value
2. If `ELEVENLABS_API_KEY` exists, use `elevenlabs`
3. If `OPENAI_TTS_API_KEY` or `OPENAI_TTS_BASE_URL` exists, use `openai_tts`
4. If `VVR_OMNIVOICE_DEVICE` is set (e.g., `cuda:0`), select `omnivoice`
5. If none match, raise `ValueError` with a message indicating no provider is configured

### CLI Override

The `--tts-provider <name>` flag overrides all environment-based detection. This is useful for testing or forcing a specific backend:

```bash
vvrt <slug> -f AD-MP3 --tts-provider elevenlabs
vvrt <slug> -f MP3 --tts-provider omnivoice
```

## Section 3: Provider Details

### ElevenLabs

The ElevenLabs provider connects to the cloud API for high-quality synthesis with word-level timing.

**Requirements:**
- `ELEVENLABS_API_KEY` environment variable

**Features:**
- Uses `stream-with-timestamps` endpoint for word-level timing data
- Supports performance tags: `[laughs]`, `[sighs]`, `[gasps]`, `[whispers]`
- Default voice: `EXAVITQu4vr4xnSDxMaL` (Bella)

**VoiceSpec behavior:**
- `voice_id` mode uses the specified ElevenLabs voice
- `clone` mode uses the voice cloning API with reference audio
- `design` mode uses the voice design API with instructions

### OmniVoice (Local)

The OmniVoice provider runs a local PyTorch model. This is useful for offline operation and voice cloning without cloud dependencies.

**Requirements:**
- `omnivoice` Python package installed
- `OMNIVOICE_MODEL_PATH` pointing to model checkpoint files

**Features:**
- No API key required
- Voice cloning via `ref_audio_path` + `ref_text` (preferred method)
- Voice design via `instruct` string (limited quality, described as "lỏ")
- No word-level timestamps (`word_alignments=None` in results)

**Supported tags:**
- `[laughter]` — laughter effect
- `[sigh]` — sighing effect
- `[surprise-ah]` — surprise gasp
- `[whisper]` — whispered speech

**VoiceSpec behavior:**
- `clone` mode with `ref_audio_path` and `ref_text` produces best results
- `design` mode works but quality is lower than cloning
- `voice_id` mode is not supported (OmniVoice does not have a voice library)

### OpenAI-Compatible HTTP

The OpenAI TTS provider works with any server that exposes an OpenAI-compatible `/v1/audio/speech` endpoint.

**Requirements:**
- `OPENAI_TTS_API_KEY` or `OPENAI_TTS_BASE_URL` environment variable

**Features:**
- Default voice: `alloy`
- No word-level timestamps
- Supports custom endpoints via `OPENAI_TTS_BASE_URL` (for example, a local `omnivoice-server`)

**Limitations:**
- Performance tags are stripped from text (not supported by OpenAI TTS API)
- Voice cloning and design are not available

**VoiceSpec behavior:**
- Only `voice_id` mode is supported
- The voice ID maps directly to OpenAI voice names (`alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`)

## Section 4: Voice Assignment Flow

The `VoiceManager` resolves character voices using a cascading lookup:

1. **Story-specific cache** — checks `_voice_cache` for assignments made in the current session
2. **CharacterProfile from DB** — checks `CharacterProfile.ref_audio_path` or `voice_id` for existing assignments
3. **Community Voice Bank** — queries public voices by gender and inferred character tags, sorted by vote score
4. **Provider discovery** — calls `discover_voices()` on the configured provider for gender-aware matching
5. **Fallback** — uses the narrator voice when no specific voice is found

### Community Voice Bank Integration

When the Community Voice Bank is enabled (requires `voice_bank.db`):

- `VoiceManager` calls `find_best_voice(gender, tags)` on the voice bank
- Tags are inferred from character names via keyword matching (e.g., "loli" → `child`, "tsun" → `tsundere`)
- The highest-scoring public voice (by tag matches + community votes) is selected
- Selected voices are cached per story and their `usage_count` increments

To manually assign community voices, use `--select-voices` with `AD-MP3`:

```bash
vvrt <slug> -f AD-MP3 --tts-provider omnivoice --select-voices
```

### VoiceSpec Resolution Modes

The `VoiceSpec` type supports four modes in priority order:

1. **`clone`** — highest priority, uses reference audio for voice cloning
2. **`voice_id`** — uses a specific voice identifier from the provider
3. **`design`** — creates a voice from text instructions
4. **`auto`** — lets the provider select an appropriate voice

### OmniVoice Cloning Integration

When using OmniVoice as the provider:

- `ref_audio_path` from `CharacterProfile` enables voice cloning
- The system passes this path to OmniVoice along with reference text
- This produces character-consistent voices without cloud API calls

### Provider-Specific Settings

The `VoiceSpec.settings` dictionary passes provider-specific parameters:

- **ElevenLabs:** `stability`, `similarity_boost`, `style`, `use_speaker_boost`
- **OmniVoice:** `temperature`, `top_p`, `repetition_penalty`
- **OpenAI:** `speed` (speech speed multiplier)

Example:

```python
voice = VoiceSpec(
    mode="voice_id",
    voice_id="EXAVITQu4vr4xnSDxMaL",
    settings={"stability": 0.5, "similarity_boost": 0.75}
)
```

## Section 5: Custom Provider Guide

You can add custom TTS providers by implementing the `TTSProvider` protocol.

### Step 1: Create Provider Module

Create a new file at `vvr_scraper/tts/my_provider.py`:

```python
from vvr_scraper.tts.base import TTSProvider, VoiceSpec, SynthesisResult, VoiceInfo

class MyProvider:
    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        # Your synthesis logic here
        audio_bytes = b"..."  # PCM or WAV data
        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=24000,
            duration_ms=1000,
            word_alignments=None  # or list of WordAlignment if supported
        )
    
    async def discover_voices(self) -> list[VoiceInfo]:
        # Return available voices for this provider
        return [
            VoiceInfo(id="voice1", name="Voice One", gender="female"),
            VoiceInfo(id="voice2", name="Voice Two", gender="male"),
        ]
    
    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        # Generate a short preview for voice selection UI
        result = await self.synthesize(text, voice)
        return result.audio_bytes
    
    async def close(self) -> None:
        # Cleanup resources (HTTP sessions, model memory, etc.)
        pass
```

### Step 2: Register Provider

Add the registration to `vvr_scraper/tts/__init__.py`:

```python
from vvr_scraper.tts.base import register
from vvr_scraper.tts.my_provider import MyProvider

register("my_provider", MyProvider)
```

### Step 3: Use Provider

After registration, use your provider via CLI or environment:

```bash
# Via CLI flag
vvrt <slug> -f AD-MP3 --tts-provider my_provider

# Via environment variable
export VVR_TTS_PROVIDER=my_provider
vvrt <slug> -f AD-MP3
```

### Protocol Reference

The `TTSProvider` protocol requires four async methods:

| Method | Purpose |
|--------|---------|
| `synthesize(text, voice)` | Convert text to audio bytes |
| `discover_voices()` | List available voices for UI selection |
| `preview_voice(voice, text)` | Generate short preview audio |
| `close()` | Release resources on shutdown |

## Section 6: Tag Mapping Reference

The system uses generic performance tags in prompts. These are mapped to provider-specific equivalents at synthesis time.

### Generic Tags

Use these tags in your prompts for portable effects:

- `[laughter]` — character laughs
- `[sigh]` — character sighs
- `[surprise]` — surprise reaction
- `[whisper]` — whispered speech
- `[pause]` — brief pause

### Provider-Specific Mapping

The `map_tags()` function in `base.py` converts generic tags:

| Generic Tag | ElevenLabs | OmniVoice | OpenAI |
|-------------|------------|-----------|--------|
| `[laughter]` | `[laughs]` | `[laughter]` | stripped |
| `[sigh]` | `[sighs]` | `[sigh]` | stripped |
| `[surprise]` | `[gasps]` | `[surprise-ah]` | stripped |
| `[whisper]` | `[whispers]` | `[whisper]` | stripped |
| `[pause]` | (space) | (space) | stripped |

**Note:** OpenAI TTS does not support performance tags, so they are removed from the text before sending to the API.

## Section 7: Web API Endpoints

The Web UI exposes endpoints for voice discovery and preview.

### List Voices

```
GET /voices/list
```

Returns available voices from the configured provider:

```json
{
  "voices": [
    {"id": "voice1", "name": "Voice One", "gender": "female"},
    {"id": "voice2", "name": "Voice Two", "gender": "male"}
  ]
}
```

### Preview Voice

```
GET /voices/preview?voice_id=...&ref_audio_path=...&text=...
```

Generates a short audio preview for the specified voice. Returns audio bytes (typically WAV or MP3).

**Parameters:**

- `voice_id` — voice identifier (required for `voice_id` mode)
- `ref_audio_path` — path to reference audio (required for `clone` mode)
- `ref_text` — transcript of reference audio (recommended for `clone` mode)
- `text` — preview text to synthesize (default: short sample phrase)

**Example:**

```bash
curl "http://localhost:8000/voices/preview?voice_id=EXAVITQu4vr4xnSDxMaL" \
  --output preview.mp3
```

## Section 8: Community Voice Bank API

The Web UI exposes endpoints for managing community voice samples (OmniVoice only).

### Upload Voice

```
POST /api/voices/upload
```

**Multipart form fields:**

- `audio` — audio file (.wav, .mp3, .ogg, .m4a)
- `ref_text` — transcript text (min 10 chars)
- `name` — voice name (3–100 chars)
- `gender` — `male`, `female`, or `other`
- `age_group` — `child`, `teen`, `young_adult`, `adult`, `elder`
- `description` — optional (max 500 chars)
- `language` — default `vi`
- `mood` — optional
- `tags` — comma-separated, max 5 tags

**Validation:**
- Audio must be 3–10 seconds
- Sample rate ≥ 22050 Hz
- WAV files must be PCM 16/24-bit
- Duplicate detection via file hash

### List My Voices

```
GET /api/voices/me?limit=20&offset=0
```

Returns voices owned by the authenticated user (private + public).

### List Community Voices

```
GET /api/voices/community?limit=20&offset=0&tag=tsundere&gender=male&age_group=adult
```

Returns public voices with optional filters.

### Publish / Delist

```
PATCH /api/voices/{id}/publish    # private → public
PATCH /api/voices/{id}/delist     # public → delisted
```

### Vote

```
POST /api/voices/{id}/vote
Body: { "vote": 1 }  # or -1
```

### Preview

```
POST /api/voices/{id}/preview
Body: { "text": "Xin chào" }
Response: audio/wav bytes
```

### Character Profile Integration

Update a character's voice from the community bank:

```
PUT /api/correction/{slug}/characters/{name}
Body: { "voice_bank_id": "uuid-of-voice" }
```

The system resolves the voice from the bank and writes `ref_audio_path` + `ref_text` into the character profile.

## Troubleshooting

### Provider Not Found

If you see `ValueError: No TTS provider configured`:

1. Check that at least one provider environment variable is set
2. Or set `VVR_TTS_PROVIDER` explicitly
3. Or use `--tts-provider` CLI flag

### OmniVoice Model Not Found

If OmniVoice fails with model path errors:

1. Verify `OMNIVOICE_MODEL_PATH` points to valid checkpoint files
2. Ensure the `omnivoice` package is installed: `pip install omnivoice`
3. Check that model files are downloaded and accessible

### ElevenLabs Rate Limits

If ElevenLabs returns rate limit errors:

1. Check your API key quota at https://elevenlabs.io
2. Consider switching to `omnivoice` for local processing
3. Add delays between synthesis calls in batch operations

### OpenAI Connection Errors

If OpenAI TTS fails to connect:

1. Verify `OPENAI_TTS_API_KEY` is set correctly
2. Check `OPENAI_TTS_BASE_URL` if using a custom endpoint
3. Ensure the endpoint exposes `/v1/audio/speech` correctly
