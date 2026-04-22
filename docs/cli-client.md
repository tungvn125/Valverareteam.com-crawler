# vvrt-client CLI Documentation

## Overview

`vvrt-client` is a standalone CLI client for the VVR Voice Bank API. It provides a command-line interface for managing voice samples, browsing the community gallery, and interacting with the voice bank server.

Unlike the main `vvrt` CLI (which is used for web scraping operations), `vvrt-client` is specifically designed as a remote client for voice bank operations, allowing users to:

- Upload and manage voice samples
- Browse public voice galleries
- Download voice audio files
- Generate TTS previews
- Vote on community voices

## Installation

The CLI client is distributed as part of the `vvr-scraper` package. Install it via pip:

```bash
pip install vvr-scraper
```

After installation, the `vvrt-client` command will be available in your PATH.

## Authentication

### Login

Authenticate with the voice bank server to obtain a JWT token:

```bash
vvrt-client login
```

Options:
- `--username, -u`: Username (will prompt if omitted)
- `--password, -p`: Password (will prompt if omitted)

You can also provide credentials directly:

```bash
vvrt-client login --username myuser --password mypass
```

On successful login, the token is saved to `~/.config/vvr-scraper/token.json` along with user information (username, user_id, role, created_at).

### Logout

Remove the stored authentication token:

```bash
vvrt-client logout
```

This deletes the token file at `~/.config/vvr-scraper/token.json`.

### Token Storage

Tokens are stored in JSON format at:

```
~/.config/vvr-scraper/token.json
```

Token resolution priority (highest to lowest):

1. **Command-line token**: Use `--token` flag to override
2. **Environment variable**: Set `VVR_TOKEN` environment variable
3. **Token file**: The default location at `~/.config/vvr-scraper/token.json`

## Global Flags

These flags apply to all subcommands:

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Server host address |
| `--port` | `8000` | Server port |
| `--token` | None | JWT token for authentication (overrides token file) |

Example:

```bash
vvrt-client --host 192.168.1.100 --port 8080 list
```

## Commands

### upload

Upload a new voice sample to your voice bank.

```bash
vvrt-client upload [options]
```

**Options:**

| Option | Short | Required | Description |
|--------|-------|----------|-------------|
| `--audio` | `-a` | Yes* | Path to audio file |
| `--name` | `-n` | Yes* | Voice name (3-100 characters) |
| `--ref-text` | `-t` | Yes* | Reference text (minimum 10 characters) |
| `--gender` | `-g` | Yes* | Speaker gender: `male`, `female`, `other` |
| `--age-group` | | Yes* | Age group: `child`, `teen`, `young_adult`, `adult`, `elder` |
| `--description` | | No | Voice description |
| `--language` | | No | Language code (default: `vi`) |
| `--mood` | `-m` | No | Voice mood/tag |
| `--tags` | | No | Comma-separated tags |

*Required fields will prompt interactively if omitted.

**Example:**

```bash
vvrt-client upload --audio sample.wav --name "My Voice" --ref-text "Hello world" --gender male --age-group adult
```

### list

List all voices in your personal voice bank.

```bash
vvrt-client list [options]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | `20` | Maximum number of items to return |
| `--offset` | `0` | Pagination offset |

**Example:**

```bash
vvrt-client list --limit 50 --offset 20
```

### community

Browse the public voice gallery.

```bash
vvrt-client community [options]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--tag` | None | Filter by tag |
| `--gender` | None | Filter by gender: `male`, `female`, `other` |
| `--age-group` | None | Filter by age group: `child`, `teen`, `young_adult`, `adult`, `elder` |
| `--sort` | `votes` | Sort order: `votes` or `newest` |
| `--limit` | `20` | Maximum number of items |
| `--offset` | `0` | Pagination offset |

**Example:**

```bash
vvrt-client community --gender female --sort newest --limit 10
```

### show

Display detailed information about a specific voice.

```bash
vvrt-client show <voice_id>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to display |

**Example:**

```bash
vvrt-client show abc123def456
```

### update

Update voice metadata.

```bash
vvrt-client update <voice_id> [options]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to update |

**Options:**

| Option | Description |
|--------|-------------|
| `--name` | New name |
| `--description` | New description |
| `--mood` | New mood |
| `--tags` | New comma-separated tags |

**Example:**

```bash
vvrt-client update abc123 --name "New Name" --tags "tag1,tag2,tag3"
```

### delete

Delete a voice sample from your voice bank.

```bash
vvrt-client delete <voice_id>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to delete |

This command prompts for confirmation before deletion.

**Example:**

```bash
vvrt-client delete abc123def456
```

### publish

Make a voice public (visible in the community gallery).

```bash
vvrt-client publish <voice_id>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to publish |

**Example:**

```bash
vvrt-client publish abc123def456
```

### delist

Make a voice private (remove from community gallery).

```bash
vvrt-client delist <voice_id>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to delist |

**Example:**

```bash
vvrt-client delist abc123def456
```

### vote

Upvote or downvote a voice in the community gallery.

```bash
vvrt-client vote <voice_id> (--up | --down)
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to vote on |

**Options (mutually exclusive, one required):**

| Option | Description |
|--------|-------------|
| `--up` | Upvote the voice |
| `--down` | Downvote the voice |

**Example:**

```bash
vvrt-client vote abc123def456 --up
vvrt-client vote abc123def456 --down
```

### download

Download the audio file for a voice.

```bash
vvrt-client download <voice_id> --output <path>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to download |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output file path (required) |

**Example:**

```bash
vvrt-client download abc123def456 --output ./my-voice.wav
```

### preview

Generate a TTS preview using a voice and play it.

```bash
vvrt-client preview <voice_id> [options]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `voice_id` | The voice ID to use for TTS |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--text` | `-t` | Text to synthesize (will prompt if omitted) |

**Example:**

```bash
vvrt-client preview abc123def456 --text "Hello, this is a test"
```

The preview is saved to a temporary file and automatically played using one of the following audio players (in order of preference):

1. `aplay` (ALSA)
2. `ffplay` (FFmpeg)
3. `mpv`

If no player is found, the file path is displayed for manual playback.

## Configuration

### Configuration File Location

The CLI client stores its authentication token at:

```
~/.config/vvr-scraper/token.json
```

This path is automatically created on first use if it doesn't exist.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `VVR_TOKEN` | JWT token for authentication (overrides token file) |

### Token File Format

The token file stores the following JSON structure:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "myuser",
  "user_id": "uuid-here",
  "role": "user",
  "created_at": "2024-01-15T10:30:00"
}
```

## API Client

The `APIClient` class in `client.py` handles all HTTP communication with the voice bank server.

### Base URL

The base URL is constructed from the host and port:

```
http://{host}:{port}
```

Default: `http://127.0.0.1:8000`

### Timeouts

| Operation | Timeout |
|-----------|---------|
| Standard requests | 30 seconds |
| File uploads | 60 seconds |
| File downloads | 60 seconds |
| Preview generation | 60 seconds |

### Error Handling

The client translates HTTP status codes to user-friendly error messages:

| Status Code | Error Message |
|-------------|---------------|
| 401 | "Chưa đăng nhập. Chạy `vvrt-client login`" |
| 403 | "Không có quyền thực hiện" |
| 404 | "Không tìm thấy voice sample" |
| 413 | "File quá lớn (tối đa 30MB)" |
| 429 | "Quá nhiều request, thử lại sau" |
| 500 | "Lỗi server" |

Connection errors produce: "Không thể kết nối đến server tại {base_url}. Vui lòng kiểm tra server đã chạy chưa."

### Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | General error (CLIError) |
| 130 | Operation cancelled by user (Ctrl+C) |

## Display Formatting

The CLI uses the Rich library for formatted terminal output:

- **Tables**: Voice lists are displayed in formatted tables with columns for ID, Name, Gender, Age, Duration, Tags, Votes, and Visibility
- **Panels**: Voice details are shown in bordered panels with all metadata
- **Colors**: 
  - Public voices: Green
  - Private voices: Yellow
  - Delisted voices: Red
  - Errors: Red
  - Success messages: Green
  - Warnings: Yellow

## Supported Audio Formats

The following audio formats are supported for upload:

| Extension | MIME Type |
|-----------|-----------|
| `.mp3` | `audio/mpeg` |
| `.wav` | `audio/wav` |
| `.ogg` | `audio/ogg` |
| `.m4a` | `audio/mp4` |
| `.flac` | `audio/flac` |
