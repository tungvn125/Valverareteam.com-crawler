# Community Voice Bank (CVB) — Design Spec

## Overview

Add a community voice bank system to VVR-Scraper that lets users upload voice samples with transcripts for OmniVoice cloning. Users maintain a "My Voices" private library and can publish voices to a public "Community Voices" bank. The community can vote, tag, and discover voices. When generating audio dramas, the VoiceManager resolves character voices using a priority cascade that includes community voices.

## Goals

- Let users upload voice samples + transcripts for OmniVoice voice cloning.
- Support private "My Voices" and public "Community Voices" with voting.
- Integrate with the existing `VoiceManager` in `audio_drama.py` so community voices participate in the voice assignment cascade.
- Allow users to search and select community voices for specific characters via CLI and Web UI.
- Provide a CLI command `vvrt voice upload` for uploading voice samples to the bank.
- Provide a `--select-voices` flag for interactive voice assignment during AD-MP3 generation.
- Keep the scope OmniVoice-only because OmniVoice is the only provider that supports local reference-audio cloning via `ref_audio_path` + `ref_text`.

## Non-Goals

- Support ElevenLabs or OpenAI voice cloning (those use cloud voice IDs, not local reference audio).
- Real-time voice training or fine-tuning.
- Custom emoji / GIF integration (out of scope; belongs to the social emoji feature).

## Naming Convention

All variable names are aligned with the existing codebase (`VoiceSpec`, `CharacterProfile`, `db.py`):

| Concept | Field Name | Used In |
|---|---|---|
| Path to reference audio file | `ref_audio_path` | `VoiceSpec`, `character_profiles`, `voice_samples`, CLI, local voice dirs |
| Transcript text for cloning | `ref_text` | `VoiceSpec`, `character_profiles`, `voice_samples`, CLI, local voice dirs |

The voice bank DB uses the same field names as `VoiceSpec` and `character_profiles` to avoid confusion. When a community voice is resolved for synthesis, the DB's `ref_audio_path` (relative) is joined with `VVR_VOICE_BANK_DIR` to produce the absolute path that `VoiceSpec.ref_audio_path` receives.

## Architecture

```
┌─────────────────────────────────────────────┐
│            VVR Backend (FastAPI)            │
│  ┌────────────┐  ┌───────────────────────┐  │
│  │ Social     │  │ Voice Bank Module     │  │
│  │ - Auth     │  │ - Upload/Publish      │  │
│  │ - Voting   │  │ - Vote/Tag/Search     │  │
│  │ - Moderate │  │ - My Voices           │  │
│  └─────┬──────┘  └───────────┬───────────┘  │
│        │                     │              │
│   social.db              voice_bank.db      │
│  (existing)            (new, separate)     │
└────────┼────────────────────┼──────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────┐
│        VoiceManager (audio_drama.py)        │
│  1. Story config (ref_audio/voice_id)       │
│  2. CharacterProfile from DB                │
│  3. Community Voices (public + vote rank)   │
│  4. Auto-assign fallback                    │
└─────────────────────────────────────────────┘
```

## Database

A new `voice_bank.db` SQLite file, independent from `books.db` and `social.db`. It is initialized in the app lifespan similar to `social.db`.

### `voice_samples`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID, PK | |
| `user_id` | UUID, FK → social.users.id | owner |
| `name` | TEXT | 3–100 characters |
| `description` | TEXT | optional, max 500 characters |
| `ref_audio_path` | TEXT | **relative** path from `VVR_VOICE_BANK_DIR`, e.g. `<user_id>/<voice_id>.wav` |
| `ref_text` | TEXT | transcript text for OmniVoice cloning |
| `duration_ms` | INTEGER | |
| `sample_rate` | INTEGER | |
| `gender` | TEXT | `male`, `female`, `other` |
| `age_group` | TEXT | `child`, `teen`, `young_adult`, `adult`, `elder` |
| `language` | TEXT | default `vi` |
| `mood` | TEXT | optional |
| `visibility` | TEXT | `private`, `public`, or `delisted` |
| `usage_count` | INTEGER | how many times used in audio drama generation |
| `file_hash` | TEXT | BLAKE3 hash of canonical WAV for dedup |
| `created_at` | TEXT | ISO 8601 (aligned with social.db convention) |
| `updated_at` | TEXT | ISO 8601 |

### `voice_votes`

| Column | Type | Notes |
|---|---|---|
| `voice_id` | UUID, FK | |
| `user_id` | UUID, FK | |
| `vote` | INTEGER | `+1` or `-1` |
| `created_at` | TEXT | ISO 8601 |
| **UNIQUE** (`voice_id`, `user_id`) | | one vote per user per voice |

**Vote score is computed on-demand** via `SUM(vote)`; there is no cached `vote_score` column to avoid race conditions.

### `voice_tags`

| Column | Type | Notes |
|---|---|---|
| `voice_id` | UUID, FK | |
| `tag` | TEXT | normalized, max 15 characters |
| **PK** (`voice_id`, `tag`) | | |

### Tag Rules

- Tags are user-defined (free-form), not curated.
- Each tag: 1 word, lowercase letters, numbers, hyphens, underscores; max 15 characters.
- Max 5 tags per voice sample.
- Stored normalized (lowercase, stripped).
- Examples: `tsundere`, `hanoi-accent`, `soft-spoken`, `villain-vibe`.

### Indexes

```sql
CREATE INDEX idx_voices_community ON voice_samples(visibility);
CREATE INDEX idx_voices_user ON voice_samples(user_id);
CREATE INDEX idx_voices_gender_age ON voice_samples(gender, age_group);
CREATE INDEX idx_tags_tag ON voice_tags(tag);
CREATE INDEX idx_voices_file_hash ON voice_samples(user_id, file_hash);
```

## API Endpoints

### Upload & Management

```
POST /api/voices/upload
  Content-Type: multipart/form-data
  Fields:
    - audio: File (required)
    - ref_text: string (required, min 10 chars, max 5000 chars)
    - name: string (required, 3-100 chars)
    - description: string (optional, max 500 chars)
    - gender: enum(male, female, other) (required)
    - age_group: enum(child, teen, young_adult, adult, elder) (required)
    - language: string (default "vi")
    - mood: string (optional)
    - tags: comma-separated string (optional, max 5)
  Response: { id, name, visibility, audio_url, preview_url }

GET    /api/voices/me?limit=20&offset=0                 # List My Voices
GET    /api/voices/community?limit=20&offset=0&tag=tsundere&sort=votes&gender=male&age_group=adult
GET    /api/voices/{id}                                  # Get single voice detail
PATCH  /api/voices/{id}                                  # Update metadata (name, description, mood, tags)
PATCH  /api/voices/{id}/publish                          # private → public (owner only)
PATCH  /api/voices/{id}/delist                           # public → delisted (owner or admin)
DELETE /api/voices/{id}                                  # Delete (owner or admin)
POST   /api/voices/{id}/vote                             # Body: { vote: 1 | -1 }
POST   /api/voices/{id}/preview                          # Body: { text: "..." }
                                                         # Response: audio/wav bytes
```

### List Endpoint Response Shape

```json
{
  "items": [...],
  "total": 42
}
```

### Audio Validation Rules (Server-Side)

| Check | Requirement | Error Response |
|---|---|---|
| **Format** | `.wav`, `.mp3`, `.ogg`, `.m4a` | `400: Unsupported audio format. Accepted: wav, mp3, ogg, m4a` |
| **Codec (WAV)** | PCM, 16-bit or 24-bit | `400: WAV must be PCM 16/24-bit` |
| **Codec (MP3)** | Standard MPEG Audio | `400: Invalid MP3 encoding` |
| **Sample Rate** | ≥ 22050 Hz | `400: Sample rate must be ≥ 22050 Hz (got {sr})` |
| **Channels** | Mono or Stereo | `400: Only mono/stereo supported` |
| **Duration** | 3–10 seconds (validated on **decoded audio stream post-conversion**) | `400: Duration must be 3-10 seconds (got {dur}ms)` |
| **File Size** | ≤ 30 MB | `400: File too large (max 30MB)` |
| **ref_text** | Required, min 10 chars | `400: ref_text must be at least 10 characters` |

### Post-Upload Processing

1. Save raw file to temp.
2. Validate with `ffprobe` or `soundfile`.
3. Convert to canonical format: **WAV PCM 16-bit, mono, 22050 Hz** using `ffmpeg`.
4. **Re-validate duration on the canonical file** to ensure it still meets the 3–10s requirement.
5. Compute `file_hash` (BLAKE3 of canonical file).
6. Check dedup: if same `user_id` + `file_hash` already exists → reject with `409: Duplicate voice sample`.
7. Save canonical file to `<VVR_VOICE_BANK_DIR>/<user_id>/<voice_id>.wav`.
8. Store **relative path** `<user_id>/<voice_id>.wav` in `ref_audio_path`.
9. Store transcript text in `ref_text`.
10. Store metadata in `voice_bank.db` with `visibility='private'`.
11. Return voice ID, `audio_url`, and `preview_url`.

### URL Definitions

- `audio_url` → `/api/voices/{id}/audio` (static file endpoint)
- `preview_url` → `/api/voices/{id}/preview`

### Rate Limits

| Endpoint | Limit |
|---|---|
| Upload | 5 per hour per user |
| Preview | 10 per minute per user |
| Vote | 30 per minute per user |

## Component Design

### New Module: `vvr_scraper/voice_bank/`

```
vvr_scraper/voice_bank/
├── __init__.py
├── router.py          # FastAPI routes
├── models.py          # Pydantic request/response models
├── db.py              # voice_bank.db queries + VoiceBankDatabaseManager
├── validator.py       # Audio validation (ffprobe/soundfile)
├── storage.py         # File storage manager
└── service.py         # Business logic (upload, publish, vote, cleanup)
```

### `db.py`

```python
class VoiceBankDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db = None
        self._lock = asyncio.Lock()

    async def get_db(self): ...
    async def init_db(self): ...
    async def close(self): ...
```

Initialized in app lifespan (`web/__init__.py`):
```python
app.state.voice_bank_db = VoiceBankDatabaseManager(voice_bank_db_path)
await app.state.voice_bank_db.init_db()
```

### `validator.py`

```python
class AudioValidationResult:
    valid: bool
    format: str          # "wav", "mp3", "ogg", "m4a"
    codec: str
    sample_rate: int
    channels: int
    duration_ms: int
    bit_depth: int | None
    error: str | None
```

Validation pipeline:
1. Check MIME type / extension.
2. `ffprobe -v error -show_format -show_streams` → parse JSON.
3. Cross-check rules above.
4. If pass → convert to canonical WAV with `ffmpeg -i input -ar 22050 -ac 1 -c:a pcm_s16le output.wav`.
5. Re-validate duration on decoded canonical file.

### `storage.py`

Storage layout:
```
<VVR_VOICE_BANK_DIR>/
├── <user_id>/
│   └── <voice_id>.wav          # Canonical converted file
```

- Env var: `VVR_VOICE_BANK_DIR` (default: `<config_dir>/voice_bank`).
- `ref_audio_path` stored in DB is **relative** to this directory.
- `delete_voice_files(user_id, voice_id)` removes the canonical file on DELETE.

### `service.py`

Key functions:
- `upload_voice(...)` → validate → convert → dedup check → save → create private record.
- `publish_voice(voice_id, user_id)` → private → public (owner only).
- `delist_voice(voice_id, user_id)` → public → delisted (owner or admin).
- `vote_voice(voice_id, user_id, vote)` → upsert vote (atomic transaction, compute score on-demand).
- `search_voices(query, tags, gender, age_group, sort, limit, offset)` → community search.
- `find_best_voice(gender, tags)` → algorithm defined below.
- `increment_usage(voice_id)` → increment `usage_count`.

### `find_best_voice` Algorithm

```python
async def find_best_voice(gender: str, tags: list[str]) -> dict | None:
    """Find the best matching public community voice."""
    # 1. Filter: visibility='public', gender matches (or 'unknown')
    # 2. Score each voice:
    #    - Exact tag match: +10 per matching tag
    #    - Vote score: SUM(vote) from voice_votes
    #    - Total score = tag_matches * 10 + vote_score
    # 3. Sort by total score DESC
    # 4. Break ties by usage_count DESC (prefer proven voices), then created_at DESC
    # 5. Return top 1
```

## VoiceManager Integration

### Updated Lookup Order in `VoiceManager.get_voice()`

**Cross-reference:** This sits alongside the per-story `voices/` folder mechanism from the TTS Provider Abstraction spec (2026-04-20). Local per-story samples are handled via `CharacterProfile.ref_audio_path` at step 2. Community voices are consulted only if no local sample is assigned.

```python
async def get_voice(self, character_name: str, gender: str = "unknown") -> VoiceSpec:
    char_normalized = character_name.lower()
    
    # 1. Story-specific config (highest priority)
    if char_normalized in self._voice_cache:
        return self._voice_cache[char_normalized]
    
    # 2. CharacterProfile from DB (includes per-story voices/ folder refs)
    profile = await self._get_character_profile(char_normalized)
    if profile:
        if profile.ref_audio_path:
            return VoiceSpec(ref_audio_path=profile.ref_audio_path, ref_text=profile.ref_text)
        if profile.voice_id:
            return VoiceSpec(voice_id=profile.voice_id)
    
    # 3. Community Voice Bank lookup
    voice_bank = get_voice_bank_db()
    community_voice = await voice_bank.find_best_voice(
        gender=gender,
        tags=_infer_tags_from_character(character_name),
    )
    if community_voice:
        canonical_path = os.path.join(
            VVR_VOICE_BANK_DIR, community_voice["ref_audio_path"]
        )
        spec = VoiceSpec(
            ref_audio_path=canonical_path,
            ref_text=community_voice["ref_text"]
        )
        self._voice_cache[char_normalized] = spec
        await voice_bank.increment_usage(community_voice["id"])
        return spec
    
    # 4. Auto-assign fallback (ElevenLabs / OpenAI)
    ...
```

### Character → Tag Inference

```python
def _infer_tags_from_character(character_name: str) -> list[str]:
    """Infer community voice tags from a character name. MVP keyword matching."""
    name = character_name.lower()
    tags = []
    if any(k in name for k in ("loli", "nhóc", "bé", "con nít", "trẻ con")):
        tags.append("child")
    if any(k in name for k in ("ông", "bà", "lão", "già", "cụ")):
        tags.append("elder")
    if "tsun" in name:
        tags.append("tsundere")
    if any(k in name for k in ("yandere", "điên", "psycho")):
        tags.append("yandere")
    if any(k in name for k in ("chúa", "vua", "hoàng đế", "lord")):
        tags.append("noble")
    return tags
```

Can be overridden in story config if needed.

## CLI Commands

### `vvrt voice upload`

A new CLI subcommand for uploading voice samples to the voice bank. This command works in **offline mode** (no web server required) — it validates, converts, and stores the voice sample directly into `voice_bank.db`.

```bash
vvrt voice upload
```

Interactive prompts:

1. **Audio file path** — prompt for `ref_audio_path` (path to `.wav`, `.mp3`, `.ogg`, or `.m4a` file).
   - Validates: file exists, format supported, duration 3–10s, codec correct.
   - If invalid, shows error and re-prompts.

2. **Transcript text** — prompt for `ref_text` (the text spoken in the audio).
   - Validates: min 10 chars, max 5000 chars.
   - If invalid, shows error and re-prompts.

3. **Name** — prompt for voice name (3–100 chars).

4. **Metadata** (optional, press Enter to skip):
   - `gender`: select from `male` / `female` / `other`
   - `age_group`: select from `child` / `teen` / `young_adult` / `adult` / `elder`
   - `language`: default `vi`
   - `mood`: free text or Enter to skip
   - `tags`: comma-separated, max 5

5. **Confirm** — show summary table, ask y/n.

6. **Process** — validate audio, convert to canonical WAV, compute hash, store in `voice_bank.db` with `visibility='private'`.

Output on success:
```
✓ Voice sample uploaded successfully!
  ID: <uuid>
  Name: "Hà Nội trầm"
  Duration: 5.2s
  Visibility: private
  Path: <VVR_VOICE_BANK_DIR>/<user_id>/<voice_id>.wav

Publish to community? [y/N]:
```

If user confirms publish → `visibility` set to `'public'`.

**Note:** In offline mode (no web auth), `user_id` defaults to `'local'`. When the web server is running, `vvrt voice upload` uses the authenticated user's ID.

### `--select-voices` Flag

Add a new CLI argument for the AD-MP3 pipeline:

```bash
vvrt <slug> -f AD-MP3 --tts-provider omnivoice --select-voices
```

When `--select-voices` is used, the CLI enters an interactive voice assignment flow **after the LLM has parsed the script** (so all characters are known). The flow has two modes:

#### Mode A: Local Voice Directory

The user provides a local directory path containing voice samples organized as:

```
<voice_dir>/
├── linh-voice/
│   ├── ref_audio_path.wav      # Audio file (any supported format)
│   └── ref_text.txt            # Transcript text
├── ong-thay-voice/
│   ├── ref_audio_path.wav
│   └── ref_text.txt
└── narrator-voice/
    ├── ref_audio_path.wav
    └── ref_text.txt
```

**Directory structure rules:**
- Each subdirectory name becomes the voice name (the part before `-voice` is extracted as a hint for character matching).
- `ref_audio_path.wav` — the audio file. Must be a supported format (`.wav`, `.mp3`, `.ogg`, `.m4a`). The filename must be exactly `ref_audio_path` with any supported extension.
- `ref_text.txt` — plain text file containing the transcript. Must be ≥ 10 chars.

**Flow:**
1. CLI scans `<voice_dir>/` for subdirectories matching the pattern.
2. For each subdirectory, reads `ref_text.txt` and validates `ref_audio_path.*`.
3. Displays a Rich table of discovered voices:
   ```
   ┌────────────────────┬──────────┬────────────┐
   │ Voice Name         │ Duration │ Transcript │
   ├────────────────────┼──────────┼────────────┤
   │ linh-voice         │ 5.2s     │ "Xin chào… │
   │ ong-thay-voice     │ 8.1s     │ "Các em h… │
   │ narrator-voice     │ 6.0s     │ "Trong mộ… │
   └────────────────────┴──────────┴────────────┘
   ```
4. For each detected character in the script, prompt:
   ```
   Character: Linh
   [1] Auto-assign (default)
   [2] Choose from local voices
   [3] Choose from community voice bank
   [4] Skip
   > 2
   
   Available local voices:
   [1] linh-voice (5.2s, female-young_adult)
   [2] ong-thay-voice (8.1s, male-adult)
   [3] narrator-voice (6.0s, male-adult)
   Select voice: 1
   ```
5. Selected voice's absolute `ref_audio_path` and `ref_text` are saved to `character_profiles` for the story.

#### Mode B: Community Voice Bank

The user chooses to search the community voice bank:

1. For each character, prompt for search keywords/tags:
   ```
   Character: Ông Thầy
   Search tags (e.g., "male adult serious"): male adult
   ```
2. Query `voice_bank.db` via `search_voices()` (works offline, direct DB query).
3. Display top results:
   ```
   ┌──────────────────┬────────┬──────────┬──────────┬───────┐
   │ Name             │ Gender │ Age      │ Tags     │ Votes │
   ├──────────────────┼────────┼──────────┼──────────┼───────┤
   │ Giọng trầm nam   │ male   │ adult    │ serious  │ +12   │
   │ Thầy giáo giọng  │ male   │ adult    │ teacher  │ +5    │
   └──────────────────┴────────┴──────────┴──────────┴───────┘
   [1] Select "Giọng trầm nam"
   [2] Select "Thầy giáo giọng"
   [3] Search again
   [4] Skip
   ```
4. User selects by number → the voice's `ref_audio_path` (resolved to absolute) and `ref_text` are saved to `character_profiles`.

#### Persisting Selections

All voice assignments are saved to `character_profiles` in `books.db`:

```python
profile = CharacterProfile(
    name=character_name,
    story_id=story_slug,
    ref_audio_path=selected_voice_ref_audio_path,  # absolute path
    ref_text=selected_voice_ref_text,
)
await db.save_character_profile(profile)
```

Future runs of the same story will use these saved assignments (highest priority in `VoiceManager`).

## Web UI Integration

The existing `PUT /api/correction/{slug}/characters/{character_name}` endpoint in `correction.py` updates character profiles including `voice_id`. Extend it to support:

- `voice_bank_id`: UUID of a community/personal voice sample
- When `voice_bank_id` is provided, fetch the voice from `voice_bank.db` and write `ref_audio_path` + `ref_text` into `character_profiles`
- Also add `ref_audio_path` and `ref_text` fields directly to `CharacterUpdateRequest` for manual entry
- The Web UI character editor gets a "Search Community Voice" button that queries `GET /api/voices/community`

## Error Handling

| Scenario | Response |
|---|---|
| Invalid audio format | `400: Unsupported audio format. Accepted: wav, mp3, ogg, m4a` |
| Wrong codec | `400: Invalid codec. WAV must be PCM 16/24-bit` |
| Sample rate < 22050 Hz | `400: Sample rate must be ≥ 22050 Hz (got {sr})` |
| Duration < 3s or > 10s | `400: Duration must be 3-10 seconds (got {dur}ms)` |
| File > 30MB | `400: File too large (max 30MB)` |
| Missing ref_text | `400: ref_text is required` |
| ref_text < 10 chars | `400: ref_text must be at least 10 characters` |
| Invalid tags | `400: Each tag must be 1 word, max 15 characters` |
| > 5 tags | `400: Maximum 5 tags allowed` |
| Duplicate file hash | `409: Duplicate voice sample` |
| Not owner on modify | `403: You do not own this voice sample` |
| Not admin on delist/delete others | `403: Admin access required` |
| Voice not found | `404: Voice sample not found` |
| Already voted | `200: Vote updated` (upsert, not error) |
| Preview text missing | `400: Preview text is required` |
| Rate limit exceeded | `429: Rate limit exceeded` |
| Local voice dir not found | CLI: `Error: Directory not found: <path>` |
| `ref_text.txt` missing in voice subdir | CLI: `Warning: Skipping <name>-voice: missing ref_text.txt` |
| `ref_audio_path.*` missing in voice subdir | CLI: `Warning: Skipping <name>-voice: missing ref_audio_path file` |

## Testing Strategy

### Backend Unit Tests

1. Audio validation pass/fail for each format (WAV, MP3, OGG, M4A).
2. FFmpeg conversion produces correct canonical spec (22050 Hz, mono, PCM 16-bit).
3. Duration re-validation on canonical file catches edge cases.
4. DB CRUD operations for voice samples, votes, tags.
5. Vote upsert and `SUM(vote)` score calculation (no race conditions).
6. Duplicate detection via `file_hash`.
7. `find_best_voice` ranking algorithm correctness.
8. VoiceManager lookup order (story config → community → fallback).
9. File cleanup on delete.

### Integration Tests

1. Full upload → validate → convert → dedup → save flow.
2. Preview generation via OmniVoice with uploaded sample (requires provider dependency).
3. Publish / delist / private toggle.
4. Community search with filters (gender, age_group, tags, sort).
5. Voice selection in audio drama pipeline.
6. CLI `vvrt voice upload` interactive flow.
7. CLI `--select-voices` local directory scanning.
8. CLI `--select-voices` community voice bank search.

### End-to-End Verification

1. Upload a valid 5-second WAV → private draft created.
2. Preview with test text → audio generated.
3. Publish → visible in community list.
4. Another user upvotes → `SUM(vote)` increases.
5. Create audio drama with character matching tags → community voice selected.
6. CLI `--select-voices` → scan local voice dir → assign → regenerate → uses assigned voice.
7. CLI `--select-voices` → search community → assign → regenerate → uses assigned voice.
8. `vvrt voice upload` → validate → store → publish → appears in community search.

## Future Extensions (Out of Scope)

1. **Auto-transcribe** using OmniVoice ASR (currently user provides `ref_text`).
2. **Voice quality scoring** — ML model evaluates clarity/noise.
3. **Collections / Playlists** — users curate voice sets for stories.
4. **Character archetype presets** — pre-filled tags for common tropes.
5. **Moderation queue** — reported voices reviewed before delisting.
6. **Freesound-style preview waveform** — visual waveform in UI.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Provider | OmniVoice only | Only provider with local `ref_audio_path` + `ref_text` cloning |
| Duration | 3–10 seconds | Per OmniVoice docs |
| Storage | Separate `voice_bank.db` | Independent backup/migrate from library data |
| Visibility | `private` / `public` / `delisted` | Simpler than separate status+visibility fields |
| Vote score | `SUM(vote)` on-demand | Avoids race conditions from cached column |
| Tags | Free-form, user-defined | Flexible, no maintenance burden |
| Required metadata | gender + age_group | Essential for voice search/filtering |
| Canonical format | WAV PCM 16-bit mono 22050 Hz | OmniVoice optimal input |
| Field naming | `ref_audio_path` + `ref_text` | Consistent with `VoiceSpec` and `character_profiles` |
| Audio path storage | Relative to `VVR_VOICE_BANK_DIR` | Portable if data directory moves |
| Lookup priority | Story config → Community → Fallback | Existing behavior preserved; community layered on top |
| File dedup | BLAKE3 hash per user | Prevents spam uploads of identical audio |
| Timestamps | ISO 8601 TEXT | Aligned with existing `social.db` convention |
| CLI voice upload | `vvrt voice upload` subcommand | Dedicated command for uploading voice samples offline |
| CLI voice selection | `--select-voices` flag | Interactive prompt after LLM script parsing |
| Local voice dir structure | `<name>-voice/ref_audio_path.wav` + `ref_text.txt` | Matches `VoiceSpec` field names for consistency |

## Deployment

### Environment Variables

```
VVR_VOICE_BANK_DIR=<path>          # default: <config_dir>/voice_bank
```

### Lifespan Initialization

In `vvr_scraper/web/__init__.py`:
```python
from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager

# Inside lifespan startup:
voice_bank_db_path = os.path.join(get_config_path(), "voice_bank.db")
app.state.voice_bank_db = VoiceBankDatabaseManager(voice_bank_db_path)
await app.state.voice_bank_db.init_db()

# Inside lifespan shutdown:
await app.state.voice_bank_db.close()
```

### Router Registration

In `vvr_scraper/web/__init__.py`:
```python
from vvr_scraper.voice_bank.router import router as voice_bank_router

app.include_router(voice_bank_router, prefix="/api/voices")
```

### Docker Compose

No new services. The voice bank module runs within the existing VVR FastAPI container. Ensure `ffmpeg` is available (already required for audio/video workflows).

## Files to Create

```
vvr_scraper/
├── voice_bank/
│   ├── __init__.py
│   ├── router.py
│   ├── models.py
│   ├── db.py
│   ├── validator.py
│   ├── storage.py
│   └── service.py
```

## Files to Modify

```
vvr_scraper/
├── audio_drama.py             # VoiceManager.get_voice() community lookup + _infer_tags_from_character
├── cli.py                     # Add --select-voices argument + vvrt voice upload subcommand
├── web/__init__.py            # Lifespan init + router registration
├── web/routes/correction.py   # Extend character update to accept voice_bank_id + ref_audio_path + ref_text
├── db.py                      # Ensure character_profiles supports ref_audio_path + ref_text
└── models.py                  # CharacterUpdateRequest: add ref_audio_path, ref_text, voice_bank_id
```