"""Business logic for voice bank operations."""

import os
import tempfile
import uuid
from datetime import UTC, datetime

from loguru import logger

from .db import VoiceBankDatabaseManager
from .storage import get_voice_file_path, save_voice_file
from .validator import AudioValidationResult, compute_file_hash, convert_to_canonical, validate_audio


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
) -> dict:
    """Full upload pipeline: validate -> convert -> dedup -> save -> create record."""
    # 1. Validate audio
    validation = validate_audio(audio_file_path)
    if not validation.valid:
        raise ValueError(validation.error)

    # 2. Convert to canonical WAV
    voice_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory() as tmpdir:
        canonical_path = os.path.join(tmpdir, f"{voice_id}.wav")
        convert_to_canonical(audio_file_path, canonical_path)

        # 3. Re-validate duration on canonical file
        canonical_validation = validate_audio(canonical_path)
        if not canonical_validation.valid:
            raise ValueError(f"Canonical file invalid: {canonical_validation.error}")

        # 4. Compute file hash for dedup
        file_hash = compute_file_hash(canonical_path)

        # 5. Check dedup
        existing = await db.get_voice_by_hash(user_id, file_hash)
        if existing:
            raise ValueError("Duplicate voice sample")

        # 6. Save to voice bank directory
        relative_path = save_voice_file(canonical_path, user_id, voice_id)

    # 7. Create DB record
    voice_id = await db.create_voice_sample(
        user_id=user_id,
        name=name,
        description=description or "",
        ref_audio_path=relative_path,
        ref_text=ref_text,
        duration_ms=canonical_validation.duration_ms,
        sample_rate=canonical_validation.sample_rate,
        gender=gender,
        age_group=age_group,
        language=language,
        mood=mood,
        visibility="private",
        file_hash=file_hash,
    )

    # 8. Set tags
    if tags:
        await db.set_tags(voice_id, tags)

    # 9. Return full record
    return await db.get_voice_sample(voice_id)


async def publish_voice(db: VoiceBankDatabaseManager, voice_id: str, user_id: str) -> dict:
    """Publish a voice from private to public."""
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise ValueError("Voice sample not found")
    if voice["user_id"] != user_id:
        raise ValueError("You do not own this voice sample")
    await db.publish_voice(voice_id, user_id)
    return await db.get_voice_sample(voice_id)


async def delist_voice(db: VoiceBankDatabaseManager, voice_id: str, user_id: str, is_admin: bool = False) -> dict:
    """Delist a voice (owner or admin)."""
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise ValueError("Voice sample not found")
    if voice["user_id"] != user_id and not is_admin:
        raise ValueError("Admin access required")
    await db.delist_voice(voice_id, user_id)
    return await db.get_voice_sample(voice_id)


async def delete_voice(db: VoiceBankDatabaseManager, voice_id: str, user_id: str, is_admin: bool = False) -> None:
    """Delete a voice sample and its files."""
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise ValueError("Voice sample not found")
    if voice["user_id"] != user_id and not is_admin:
        raise ValueError("You do not own this voice sample")

    # Store file path before deleting DB record
    from .storage import get_voice_bank_dir
    abs_path = os.path.realpath(os.path.join(get_voice_bank_dir(), voice["ref_audio_path"]))
    user_dir = os.path.realpath(os.path.join(get_voice_bank_dir(), voice["user_id"]))
    bank_dir = os.path.realpath(get_voice_bank_dir())

    # Path traversal protection: ensure resolved path is inside voice bank directory
    if not abs_path.startswith(bank_dir + os.sep):
        raise ValueError("Invalid path")

    # Delete DB record first (cascades tags and votes)
    await db.delete_voice_sample(voice_id, user_id)

    # Delete files from disk (resolve relative path to absolute)
    if os.path.exists(abs_path):
        os.remove(abs_path)
    # Clean up empty user directory
    if os.path.isdir(user_dir) and not os.listdir(user_dir):
        os.rmdir(user_dir)


async def vote_voice(db: VoiceBankDatabaseManager, voice_id: str, user_id: str, vote: int) -> int:
    """Vote on a voice sample. Returns the new score."""
    voice = await db.get_voice_sample(voice_id)
    if not voice:
        raise ValueError("Voice sample not found")
    if voice["visibility"] != "public":
        raise ValueError("Voice is not available for voting")
    await db.vote_voice(voice_id, user_id, vote)
    return await db.get_vote_score(voice_id)