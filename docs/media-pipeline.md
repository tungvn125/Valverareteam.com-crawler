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
- uses a narrator voice, overridable through `VVR_NARRATOR_VOICE_ID`

The default narrator voice ID is currently hard-coded in `VoiceManager.DEFAULT_NARRATOR_VOICE_ID`.

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

## Required Runtime Dependencies

Depending on which outputs you use, the current pipeline may require:

- Playwright Chromium
- `ffmpeg`
- OpenAI-compatible API credentials via `VVR_API_KEY` and `VVR_BASE_URL`
- Freesound credentials for sound-effect or music workflows

For local development, install Playwright Chromium with:

```bash
playwright install chromium
```

## Operational Notes

- Video rendering creates a temporary local HTTP server bound to `127.0.0.1` on a free ephemeral port.
- MP4 generation is effectively a browser-driven render pipeline, so headless and graphics-environment differences can matter.
- Some media paths log warnings rather than failing early when AI-related environment variables are missing, so misconfiguration may surface later in the pipeline.
