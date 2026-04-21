"""Audio validation and conversion for voice bank uploads."""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".m4a"}
MIN_DURATION_MS = 3000
MAX_DURATION_MS = 10000
MIN_SAMPLE_RATE = 22050
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB


@dataclass
class AudioValidationResult:
    valid: bool
    format: str = ""
    codec: str = ""
    sample_rate: int = 0
    channels: int = 0
    duration_ms: int = 0
    bit_depth: int | None = None
    error: str | None = None


def validate_audio(file_path: str) -> AudioValidationResult:
    """Validate an audio file against voice bank requirements.

    Checks format, codec, sample rate, channels, duration, and file size.
    Returns AudioValidationResult with details or error message.
    """
    path = Path(file_path)

    # Check file exists
    if not path.exists():
        return AudioValidationResult(valid=False, error=f"File not found: {file_path}")

    # Check file size
    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        return AudioValidationResult(valid=False, error=f"File too large (max 30MB, got {file_size})")

    # Check extension
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return AudioValidationResult(
            valid=False, error=f"Unsupported audio format. Accepted: wav, mp3, ogg, m4a"
        )

    # Run ffprobe
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_format", "-show_streams",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return AudioValidationResult(valid=False, error=f"ffprobe failed: {result.stderr.strip()}")
        probe = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        return AudioValidationResult(valid=False, error=f"Audio analysis failed: {e}")

    # Find audio stream
    streams = probe.get("streams", [])
    audio_stream = None
    for s in streams:
        if s.get("codec_type") == "audio":
            audio_stream = s
            break

    if audio_stream is None:
        return AudioValidationResult(valid=False, error="No audio stream found in file")

    codec = audio_stream.get("codec_name", "")
    sample_rate = int(audio_stream.get("sample_rate", 0))
    channels = int(audio_stream.get("channels", 0))
    bit_depth = audio_stream.get("bits_per_sample")
    if bit_depth:
        bit_depth = int(bit_depth)

    # Validate codec for WAV
    if ext == ".wav" and codec not in ("pcm_s16le", "pcm_s24le", "pcm_s32le"):
        return AudioValidationResult(
            valid=False, format="wav", codec=codec,
            error=f"WAV must be PCM 16/24-bit (got {codec})"
        )

    # Validate sample rate
    if sample_rate < MIN_SAMPLE_RATE:
        return AudioValidationResult(
            valid=False, format=ext.lstrip("."), codec=codec,
            sample_rate=sample_rate, error=f"Sample rate must be >= {MIN_SAMPLE_RATE} Hz (got {sample_rate})"
        )

    # Validate channels
    if channels > 2:
        return AudioValidationResult(
            valid=False, format=ext.lstrip("."), codec=codec,
            sample_rate=sample_rate, channels=channels,
            error=f"Only mono/stereo supported (got {channels} channels)"
        )

    # Get duration from format
    format_info = probe.get("format", {})
    duration_s = float(format_info.get("duration", 0))
    duration_ms = int(duration_s * 1000)

    # Validate duration
    if duration_ms < MIN_DURATION_MS or duration_ms > MAX_DURATION_MS:
        return AudioValidationResult(
            valid=False, format=ext.lstrip("."), codec=codec,
            sample_rate=sample_rate, channels=channels, duration_ms=duration_ms,
            error=f"Duration must be 3-10 seconds (got {duration_ms}ms)"
        )

    return AudioValidationResult(
        valid=True,
        format=ext.lstrip("."),
        codec=codec,
        sample_rate=sample_rate,
        channels=channels,
        duration_ms=duration_ms,
        bit_depth=bit_depth,
    )


def convert_to_canonical(input_path: str, output_path: str) -> None:
    """Convert an audio file to canonical WAV format: PCM 16-bit, mono, 22050 Hz."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le",
            output_path,
        ],
        capture_output=True, text=True, timeout=30,
        check=True,
    )


def compute_file_hash(file_path: str) -> str:
    """Compute BLAKE3 hash of a file for deduplication."""
    try:
        import blake3
        h = blake3.blake3()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except ImportError:
        # Fallback to SHA-256 if blake3 not installed
        import hashlib
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
