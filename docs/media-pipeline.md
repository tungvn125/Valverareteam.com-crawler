# Media Pipeline Guide

## Supported Export Types

The current export layer supports these output types:

- `EPUB`
- `PDF`
- `HTML`
- `MD`
- `TXT`
- `MP3`
- `AD-MP3`
- `MP4`

Those formats are available through the CLI export flow and, where applicable, through job payloads and the Web UI download paths.

## Text And Ebook Exports

### EPUB

The EPUB exporter:

- builds an `ebooklib` EPUB package
- preserves chapter and volume structure
- pre-downloads illustration images in bulk before assembly
- embeds the cover image when `cover_path` exists
- writes metadata such as title, author, description, and genres

The current implementation sets the book language to `vi`.

### PDF

The PDF exporter uses ReportLab.

Current characteristics:

- supports `DejaVuSans` and `NotoSerif`
- downloads the requested font file on demand if it is not already available locally
- fetches and embeds illustration images when present

### HTML, Markdown, And Text

These exports are generated directly from normalized content items.

They are the simplest output paths and do not require the AI or cinematic pipeline.

## Standard MP3 Export

The plain `MP3` path is the audiobook-style export.

The exporter intentionally lazy-loads heavier AI-related dependencies so CLI and Web UI startup stay lighter when you are only using text-based outputs.

## Audio Drama (`AD-MP3`)

The audio drama path builds a scripted, voice-assigned audio output from chapter content.

The current pipeline uses components such as:

- `OpenAIParser`
- `VoiceManager`
- `BGMManager`
- `FreesoundManager`
- `MixingEngine`
- `AudioTimeline`

At runtime, the parser reads `VVR_API_KEY` and `VVR_BASE_URL`, and optionally `VVR_MODEL`.

If `VVR_API_KEY` or `VVR_BASE_URL` is missing, the code logs warnings and the audio drama path may fail or fall back depending on the specific call path.

### Script Parsing Behavior

`OpenAIParser`:

- sends chapter chunks to an OpenAI-compatible chat-completions endpoint
- requests structured JSON output
- retries chunk parsing up to three attempts
- normalizes `mood_shift` objects so downstream rendering has predictable fields

Large chapters are split into chunks of about 30,000 characters before parsing.

### Voice Assignment Behavior

`VoiceManager`:

- stores and reuses character voice assignments per story
- loads existing voice mappings from the database
- discovers voices from the configured TTS provider for gender-aware matching
- uses a narrator voice, overridable through `VVR_NARRATOR_VOICE_ID`
- injects the TTS provider instance for synthesis operations

The TTS provider is configured via environment variables or the `--tts-provider` CLI flag. See [TTS Providers](tts-providers.md) for provider-specific configuration.

### Community Voice Bank

The Community Voice Bank (CVB) lets users upload voice samples for OmniVoice cloning. The system integrates these voices into the audio drama pipeline.

**Uploading voices:**

```bash
vvrt voice upload --audio ./sample.wav --ref-text "Transcript text" --name "My Voice"
```

**Voice Lookup Priority:**

`VoiceManager.get_voice()` resolves voices in this order:

1. **Story-specific assignments** — manually assigned via `--select-voices` or Web UI
2. **CharacterProfile from DB** — per-story `ref_audio_path` and `ref_text`
3. **Community Voice Bank** — best matching public voice by gender + tags + vote score
4. **Auto-assign fallback** — random provider voice or narrator voice

**Interactive Selection:**

Use `--select-voices` during AD-MP3 export to manually assign voices:

```bash
vvrt <slug> -f AD-MP3 --tts-provider omnivoice --select-voices
```

Options per character:
- **Keep auto-assigned** — use the default lookup result
- **Local directory** — scan a folder with `ref_audio_path.*` + `ref_text.txt`
- **Community bank** — search public voices by tags/gender
- **Skip** — leave unassigned

Selections are persisted to `character_profiles` in the database.

### TTS Provider Integration

The audio drama pipeline supports multiple TTS backends through the provider abstraction:

- **ElevenLabs** — cloud API with word-level timing and performance tags
- **OmniVoice** — local PyTorch model for voice cloning without cloud dependencies
- **OpenAI-compatible HTTP** — generic endpoint for custom TTS servers

Use `--tts-provider <name>` to select a specific backend, or let the system auto-detect from environment variables. The `tao_file_mp3` export also supports TTS provider selection for audiobook generation.

## Video Rendering (`MP4`)

The MP4 path uses `VideoRenderer`.

Current renderer inputs:

- `manifest_path`
- `output_path`
- `fps`
- `render_format`
- `vfx_scale`

### Rendering Model

The renderer currently:

1. loads the cinematic manifest JSON
2. computes total duration from the manifest events
3. starts an `ffmpeg` process that accepts PNG frames through stdin
4. launches Playwright Chromium
5. starts a temporary local FastAPI server to serve `/static` and `/novels`
6. opens `static/cinema.html`
7. seeks the browser player frame by frame
8. captures each frame as a screenshot
9. streams the screenshots into `ffmpeg`

This means video rendering depends on both Playwright and `ffmpeg` being available.

### Render Formats And Resolution

Current output resolutions are fixed by `render_format`:

- `landscape`: `1920x1080`
- `portrait`: `1080x1920`

Current supported FPS values in the user-facing CLI are `30` and `60`.

### Audio Muxing

After video rendering, the job runner checks the referenced cinematic manifest for `audio_path` or `audio`.

If audio is available, it renames the silent MP4 temporarily and calls `VideoRenderer.mux_audio()` to combine:

- the rendered video stream
- the audio drama output

The mux step uses `ffmpeg` with copied video, AAC audio, and `-shortest`.

## BGMManager

`BGMManager` provides mood-based background music selection from a local audio library.

### Directory Structure

The manager expects a base directory (default: `bgm/`) containing subdirectories named by mood. Each mood directory holds audio files:

```
bgm/
├── calm/
│   ├── track1.mp3
│   └── track2.wav
├── tense/
│   ├── dramatic.ogg
│   └── suspense.flac
└── happy/
    └── upbeat.m4a
```

Mood directories are scanned at initialization and can be refreshed at runtime.

### Supported Audio Formats

The following extensions are recognized: `.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`.

### Mood Mapping

Mood names are normalized to lowercase. The `available_moods` property returns all moods with at least one valid track. Tracks are retrieved via `get_random_track(mood)` which returns a random file path from the specified mood directory.

### Key Methods

| Method | Description |
|--------|-------------|
| `__init__(base_dir="bgm")` | Initialize with library path |
| `refresh()` | Re-scan the library for updates |
| `get_random_track(mood)` | Return random track path for mood |
| `available_moods` | List of moods with tracks (property) |

---

## FreesoundManager

`FreesoundManager` integrates with Freesound.org for OAuth2-authenticated background music discovery and download.

### Authentication Flow

Authentication uses OAuth2 with the Freesound API:

1. **Authorization URL** — Generated via `get_auth_url()`. Users visit this URL to authorize the application.
2. **Code Exchange** — After authorization, the callback code is exchanged for an access token via `exchange_code()`.
3. **Token Persistence** — Tokens are saved to `.vvr_freesound_auth.json` in the config directory and automatically loaded on startup.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FREESOUND_CLIENT_ID` | Yes | OAuth2 client ID from Freesound |
| `FREESOUND_CLIENT_SECRET` | Yes | OAuth2 client secret from Freesound |

### Search Behavior

The `search_bgm(tags, limit=10)` method searches Freesound with the following filters:

- **Query**: Joined tags (space-separated)
- **Format filter**: `type:(wav OR flac)` — prioritizes lossless originals
- **Fields returned**: `id,name,tags,type,previews,url`

### Download and Conversion

`download_and_convert(sound_id, output_path)` retrieves the original audio file and converts it to a standard WAV format:

- Downloads the original file (WAV or FLAC) to a temporary directory
- Loads with `pydub` and exports to 44.1kHz mono/stereo WAV
- Returns the path to the converted file

---

## ImageGenerator

`ImageGenerator` handles AI-powered image generation via DALL-E 3 with built-in caching and deduplication.

### DALL-E 3 Integration

Images are generated through the OpenAI API using the `dall-e-3` model:

- **Resolution**: `1024x1024` (default) or `1792x1024` for wide formats
- **Quality**: `standard`
- **Concurrency**: Limited to 2 simultaneous requests via semaphore

### Prompt Handling and Caching

The generator uses SHA-256 hashing for deduplication:

1. The prompt is hashed to produce a unique identifier
2. Cached images are stored as `{hash}.webp`
3. If a cached image exists for the same prompt, it is returned immediately without API call

### Output Format and Directory

- **Default cache directory**: `backgrounds/`
- **Output format**: WebP (converted from PNG/JPG)
- **Quality**: 80 (WebP compression)
- **Color space**: RGB (converted for compatibility)

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for DALL-E 3 access |

### Key Methods

| Method | Description |
|--------|-------------|
| `__init__(cache_dir="backgrounds", api_key=None)` | Initialize with cache path and optional API key |
| `generate(prompt, output_path=None)` | Generate or retrieve cached image |
| `close()` | Close the shared HTTP client |

---

## Required Runtime Dependencies

Depending on which outputs you use, the current pipeline may require:

- Playwright Chromium
- `ffmpeg`
- OpenAI-compatible API credentials via `VVR_API_KEY` and `VVR_BASE_URL`
- Freesound credentials for sound-effect or music workflows
- TTS provider credentials (one of the following):
  - `ELEVENLABS_API_KEY` for ElevenLabs cloud TTS
  - `OPENAI_TTS_API_KEY` or `OPENAI_TTS_BASE_URL` for OpenAI-compatible TTS
  - `OMNIVOICE_MODEL_PATH` and `omnivoice` package for local TTS

For local development, install Playwright Chromium with:

```bash
playwright install chromium
```

For OmniVoice local TTS, install the package and download model weights:

```bash
pip install omnivoice
# Set OMNIVOICE_MODEL_PATH to your checkpoint directory
export OMNIVOICE_MODEL_PATH=/path/to/omnivoice/checkpoints
```

## Operational Notes

- Video rendering creates a temporary local HTTP server bound to `127.0.0.1` on a free ephemeral port.
- MP4 generation is effectively a browser-driven render pipeline, so headless and graphics-environment differences can matter.
- Some media paths log warnings rather than failing early when AI-related environment variables are missing, so misconfiguration may surface later in the pipeline.
