# Voice Bank System

## Overview

The Voice Bank system provides persistent storage and community sharing of voice reference samples for text-to-speech synthesis. Users can upload, manage, and share voice samples that can be used as reference audio for TTS providers like OmniVoice.

## Database Schema

The Voice Bank uses SQLite with WAL mode enabled, managed by `VoiceBankDatabaseManager`. The database consists of three main tables:

### voice_samples

Stores metadata for each uploaded voice sample.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | UUID v4 unique identifier |
| user_id | TEXT NOT NULL | Owner's user ID |
| name | TEXT NOT NULL | Display name (3-100 chars) |
| description | TEXT | Optional description (max 500 chars) |
| ref_audio_path | TEXT NOT NULL | Relative path to audio file |
| ref_text | TEXT NOT NULL | Reference transcription text (10-5000 chars) |
| duration_ms | INTEGER NOT NULL | Audio duration in milliseconds |
| sample_rate | INTEGER NOT NULL | Audio sample rate in Hz |
| gender | TEXT NOT NULL | 'male', 'female', or 'other' |
| age_group | TEXT NOT NULL | 'child', 'teen', 'young_adult', 'adult', or 'elder' |
| language | TEXT NOT NULL DEFAULT 'vi' | Language code (default Vietnamese) |
| mood | TEXT | Optional mood descriptor |
| visibility | TEXT NOT NULL DEFAULT 'private' | 'private', 'public', or 'delisted' |
| usage_count | INTEGER NOT NULL DEFAULT 0 | Number of times used for TTS |
| file_hash | TEXT NOT NULL | BLAKE3 hash for deduplication |
| created_at | TEXT NOT NULL | ISO 8601 timestamp |
| updated_at | TEXT NOT NULL | ISO 8601 timestamp |

### voice_votes

Stores user votes on public voice samples.

| Column | Type | Description |
|--------|------|-------------|
| voice_id | TEXT NOT NULL | Foreign key to voice_samples |
| user_id | TEXT NOT NULL | Voting user ID |
| vote | INTEGER NOT NULL | 1 (upvote) or -1 (downvote) |
| created_at | TEXT NOT NULL | Vote timestamp |
| PRIMARY KEY | (voice_id, user_id) | Composite primary key |
| FOREIGN KEY | voice_id | CASCADE on delete |

### voice_tags

Stores tags associated with voice samples (max 5 per voice).

| Column | Type | Description |
|--------|------|-------------|
| voice_id | TEXT NOT NULL | Foreign key to voice_samples |
| tag | TEXT NOT NULL | Normalized tag string (lowercase, max 15 chars) |
| PRIMARY KEY | (voice_id, tag) | Composite primary key |
| FOREIGN KEY | voice_id | CASCADE on delete |

### Indexes

- `idx_voices_community` on `visibility` — For filtering public voices
- `idx_voices_user` on `user_id` — For listing user's voices
- `idx_voices_gender_age` on `(gender, age_group)` — For filtering by demographics
- `idx_tags_tag` on `tag` — For tag-based searches
- `idx_voices_user_hash` UNIQUE on `(user_id, file_hash)` — Prevents duplicate uploads

## Service Layer

The service layer (`service.py`) provides business logic functions:

### upload_voice

```python
async def upload_voice(
    db: VoiceBankDatabaseManager,
    user_id: str,
    audio_file_path: str,
    ref_text: str,
    name: str,
    description: str | None = None,
    gender: str = "other",
    age_group: str = "adult",
    language: str = "vi",
    mood: str | None = None,
    tags: list[str] | None = None,
) -> dict
```

Full upload pipeline:
1. Validates audio format using `validate_audio()`
2. Converts to canonical WAV (PCM 16-bit, mono, 22050 Hz)
3. Re-validates the converted file
4. Computes BLAKE3 file hash for deduplication
5. Checks for existing duplicate (same user + hash)
6. Saves file to voice bank directory
7. Creates database record with 'private' visibility
8. Sets tags if provided
9. Returns the complete voice sample record

Raises `ValueError` if validation fails or duplicate detected.

### publish_voice

```python
async def publish_voice(
    db: VoiceBankDatabaseManager,
    voice_id: str,
    user_id: str
) -> dict
```

Changes voice visibility from 'private' to 'public'. Only the owner can publish their voice.

### delist_voice

```python
async def delist_voice(
    db: VoiceBankDatabaseManager,
    voice_id: str,
    user_id: str,
    is_admin: bool = False
) -> dict
```

Changes voice visibility to 'delisted'. Available to owner or admin users.

### delete_voice

```python
async def delete_voice(
    db: VoiceBankDatabaseManager,
    voice_id: str,
    user_id: str,
    is_admin: bool = False
) -> None
```

Deletes a voice sample and its files:
1. Verifies ownership (or admin access)
2. Resolves absolute file path with path traversal protection
3. Deletes database record (cascades to tags and votes)
4. Removes audio file from disk
5. Cleans up empty user directory

### vote_voice

```python
async def vote_voice(
    db: VoiceBankDatabaseManager,
    voice_id: str,
    user_id: str,
    vote: int
) -> int
```

Casts a vote on a public voice sample. Returns the new vote score (sum of all votes).
Only public voices can be voted on. Uses upsert pattern (updates existing vote).

## File Storage

### Storage Location

The voice bank storage directory is determined by:

```python
def get_voice_bank_dir() -> str
```

- Environment variable `VVR_VOICE_BANK_DIR` if set
- Otherwise: `{config_dir}/voice_bank` where config_dir comes from `vvr_scraper.utils.get_config_dir()`

### File Organization

Files are organized as: `{voice_bank_dir}/{user_id}/{voice_id}.wav`

- Each user has their own subdirectory
- Files are stored as canonical WAV format
- Original filenames are not preserved

### Key Functions

#### save_voice_file

```python
def save_voice_file(source_path: str, user_id: str, voice_id: str) -> str
```

Copies a canonical WAV file to the voice bank directory. Creates user subdirectory if needed. Returns the relative path (e.g., 'user-uuid/voice-uuid.wav').

#### get_voice_file_path

```python
def get_voice_file_path(relative_path: str) -> str
```

Resolves a relative path to an absolute path within the voice bank directory.

#### delete_voice_files

```python
def delete_voice_files(user_id: str, voice_id: str) -> None
```

Removes a voice file and cleans up empty user directories.

#### scan_local_voice_dir

```python
def scan_local_voice_dir(voice_dir: str) -> list[dict]
```

Scans a local directory for voice samples organized as:
```
voice_dir/
  {name}-voice/
    ref_audio_path.{wav,mp3,ogg,m4a}
    ref_text.txt (optional)
```

Returns list of dicts with: `name`, `ref_audio_path`, `ref_text`, `duration_ms`, `sample_rate`

## Validation Rules

Audio validation is performed by `validate_audio()` in `validator.py`.

### Supported Formats

- **Extensions**: `.wav`, `.mp3`, `.ogg`, `.m4a`
- **Max file size**: 30 MB

### WAV Requirements

- **Codec**: PCM 16-bit, 24-bit, or 32-bit (`pcm_s16le`, `pcm_s24le`, `pcm_s32le`)

### Audio Constraints

| Parameter | Minimum | Maximum |
|-----------|---------|---------|
| Duration | 3000 ms (3 seconds) | 10000 ms (10 seconds) |
| Sample Rate | 22050 Hz | No maximum |
| Channels | 1 (mono) | 2 (stereo) |

### Canonical Format

All uploads are converted to canonical WAV format using `convert_to_canonical()`:
- **Sample rate**: 22050 Hz
- **Channels**: 1 (mono)
- **Codec**: PCM 16-bit (`pcm_s16le`)

### Deduplication

Files are deduplicated using BLAKE3 hash (falls back to SHA-256 if blake3 not installed). The same user cannot upload the same audio file twice.

## Pydantic Models

### Request Models

#### VoiceUploadRequest

```python
class VoiceUploadRequest(BaseModel):
    name: str                    # 3-100 characters
    description: str | None      # max 500 characters
    ref_text: str                # 10-5000 characters
    gender: Literal["male", "female", "other"]
    age_group: Literal["child", "teen", "young_adult", "adult", "elder"]
    language: str = "vi"
    mood: str | None
    tags: list[str] = []         # max 5 tags, each max 15 chars
```

Tag validation:
- Maximum 15 characters per tag
- Alphanumeric with hyphens and underscores only
- Converted to lowercase and stripped

#### VoiceUpdateRequest

```python
class VoiceUpdateRequest(BaseModel):
    name: str | None             # 3-100 characters
    description: str | None      # max 500 characters
    mood: str | None
    tags: list[str] | None       # max 5 tags
```

#### VoiceVoteRequest

```python
class VoiceVoteRequest(BaseModel):
    vote: Literal[1, -1]
```

#### VoicePreviewRequest

```python
class VoicePreviewRequest(BaseModel):
    text: str                    # 1-500 characters
```

### Response Models

#### VoiceSampleResponse

```python
class VoiceSampleResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    ref_audio_path: str
    ref_text: str
    duration_ms: int
    sample_rate: int
    gender: str
    age_group: str
    language: str
    mood: str | None
    visibility: str
    usage_count: int
    tags: list[str]
    vote_score: int
    created_at: str
    updated_at: str
```

#### VoiceListResponse

```python
class VoiceListResponse(BaseModel):
    items: list[VoiceSampleResponse]
    total: int
```
