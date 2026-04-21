"""File storage manager for voice bank audio files."""

import os
import shutil
from pathlib import Path


def get_voice_bank_dir() -> str:
    """Get the voice bank storage directory from env or default."""
    from vvr_scraper.utils import get_config_dir
    return os.environ.get("VVR_VOICE_BANK_DIR", os.path.join(get_config_dir(), "voice_bank"))


def save_voice_file(source_path: str, user_id: str, voice_id: str) -> str:
    """Save a canonical WAV file to the voice bank directory.

    Returns the relative path (e.g., 'local/uuid.wav').
    """
    bank_dir = get_voice_bank_dir()
    user_dir = os.path.join(bank_dir, user_id)
    os.makedirs(user_dir, exist_ok=True)

    filename = f"{voice_id}.wav"
    dest = os.path.join(user_dir, filename)
    shutil.copy2(source_path, dest)

    return os.path.join(user_id, filename)


def get_voice_file_path(relative_path: str) -> str:
    """Resolve a relative voice path to an absolute path."""
    return os.path.join(get_voice_bank_dir(), relative_path)


def delete_voice_files(user_id: str, voice_id: str) -> None:
    """Delete a voice file from disk."""
    bank_dir = get_voice_bank_dir()
    filepath = os.path.join(bank_dir, user_id, f"{voice_id}.wav")
    if os.path.exists(filepath):
        os.remove(filepath)
    # Clean up empty user directory
    user_dir = os.path.join(bank_dir, user_id)
    if os.path.isdir(user_dir) and not os.listdir(user_dir):
        os.rmdir(user_dir)


def scan_local_voice_dir(voice_dir: str) -> list[dict]:
    """Scan a local directory for voice samples organized as:
    <voice_dir>/<name>-voice/ref_audio_path.<ext> + ref_text.txt

    Returns a list of dicts with keys: name, ref_audio_path, ref_text, duration_ms.
    """
    from vvr_scraper.voice_bank.validator import validate_audio, SUPPORTED_EXTENSIONS

    results = []
    voice_path = Path(voice_dir)

    if not voice_path.exists() or not voice_path.is_dir():
        return results

    for subdir in sorted(voice_path.iterdir()):
        if not subdir.is_dir():
            continue

        # Find ref_audio_path file (any supported extension)
        audio_file = None
        for ext in SUPPORTED_EXTENSIONS:
            candidate = subdir / f"ref_audio_path{ext}"
            if candidate.exists():
                audio_file = str(candidate)
                break

        if audio_file is None:
            continue  # Skip: no ref_audio_path file found

        # Read ref_text.txt (optional - OmniVoice can auto-transcribe)
        ref_text = None
        text_file = subdir / "ref_text.txt"
        if text_file.exists():
            ref_text = text_file.read_text(encoding="utf-8").strip()

        # Validate audio
        validation = validate_audio(audio_file)
        if not validation.valid:
            continue  # Skip invalid audio

        # Extract name from directory (strip trailing "-voice" if present)
        dir_name = subdir.name
        name = dir_name.removesuffix("-voice") if dir_name.endswith("-voice") else dir_name

        results.append({
            "name": name,
            "ref_audio_path": str(audio_file),
            "ref_text": ref_text,
            "duration_ms": validation.duration_ms,
            "sample_rate": validation.sample_rate,
        })

    return results
