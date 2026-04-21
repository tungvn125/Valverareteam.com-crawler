"""
Tests for voice bank service layer — upload, publish, delist, delete, vote.
"""

import os
import struct
import tempfile
import wave
from unittest.mock import patch

import pytest

from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager
from vvr_scraper.voice_bank.service import (
    delete_voice,
    delist_voice,
    publish_voice,
    upload_voice,
    vote_voice,
)


def _create_wav(path, duration_s=5, sample_rate=22050, channels=1, bit_depth=16):
    """Helper to create a valid WAV file for testing."""
    n_samples = int(duration_s * sample_rate)
    data = struct.pack(f"<{n_samples * channels}h", *([0] * n_samples * channels))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bit_depth // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(data)


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "voice_bank.db")
        manager = VoiceBankDatabaseManager(db_path)
        await manager.init_db()
        yield manager
        await manager.close()


@pytest.fixture
def voice_bank_dir():
    """Temporary voice bank directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _make_valid_wav(temp_dir, duration_s=5):
    """Create a valid 5-second WAV file and return its path."""
    path = os.path.join(temp_dir, "voice.wav")
    _create_wav(path, duration_s=duration_s, sample_rate=22050)
    return path


# =============================================================================
# Upload Tests
# =============================================================================


@pytest.mark.asyncio
async def test_upload_voice_success(voice_bank_dir, db):
    """Upload valid WAV -> creates record in DB + file on disk."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        result = await upload_voice(
            db=db,
            user_id="test-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Test Voice",
            description="A test voice sample",
            gender="male",
            age_group="adult",
            language="vi",
            mood=None,
            tags=["test"],
        )

    assert result is not None
    assert result["name"] == "Test Voice"
    assert result["user_id"] == "test-user"
    assert result["visibility"] == "private"
    assert result["ref_text"] == "Xin chào, đây là giọng nói của tôi"

    # File should exist on disk
    abs_path = os.path.join(voice_bank_dir, result["ref_audio_path"])
    assert os.path.exists(abs_path), f"Voice file not found at {abs_path}"


@pytest.mark.asyncio
async def test_upload_voice_invalid_duration(voice_bank_dir, db):
    """Upload 1s WAV -> raises ValueError with '3-10 seconds'."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=1)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        with pytest.raises(ValueError, match="3-10 seconds"):
            await upload_voice(
                db=db,
                user_id="test-user",
                audio_file_path=audio_path,
                ref_text="Xin chào, đây là giọng nói của tôi",
                name="Short Voice",
                gender="male",
                age_group="adult",
            )


@pytest.mark.asyncio
async def test_upload_voice_duplicate_hash(voice_bank_dir, db):
    """Upload same file twice -> second raises ValueError 'Duplicate'."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        await upload_voice(
            db=db,
            user_id="test-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="First Voice",
            gender="male",
            age_group="adult",
        )

        with pytest.raises(ValueError, match="Duplicate"):
            await upload_voice(
                db=db,
                user_id="test-user",
                audio_file_path=audio_path,
                ref_text="Xin chào lần hai",
                name="Second Voice",
                gender="female",
                age_group="adult",
            )


# =============================================================================
# Publish Tests
# =============================================================================


@pytest.mark.asyncio
async def test_publish_voice(voice_bank_dir, db):
    """Create private voice, publish -> visibility='public'."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="test-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Private Voice",
            gender="female",
            age_group="young_adult",
        )

    assert voice["visibility"] == "private"

    result = await publish_voice(db, voice["id"], "test-user")
    assert result["visibility"] == "public"


@pytest.mark.asyncio
async def test_publish_voice_not_owner(voice_bank_dir, db):
    """Try to publish another user's voice -> raises ValueError."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="owner-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Owner Voice",
            gender="male",
            age_group="adult",
        )

    with pytest.raises(ValueError, match="You do not own"):
        await publish_voice(db, voice["id"], "other-user")


# =============================================================================
# Delist Tests
# =============================================================================


@pytest.mark.asyncio
async def test_delist_voice(voice_bank_dir, db):
    """Publish then delist -> visibility='delisted'."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="test-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Voice to Delist",
            gender="female",
            age_group="adult",
        )

    await publish_voice(db, voice["id"], "test-user")
    result = await delist_voice(db, voice["id"], "test-user")
    assert result["visibility"] == "delisted"


# =============================================================================
# Delete Tests
# =============================================================================


@pytest.mark.asyncio
async def test_delete_voice(voice_bank_dir, db):
    """Create voice, delete -> record gone + file deleted."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="test-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Voice to Delete",
            gender="male",
            age_group="adult",
        )

    abs_path = os.path.join(voice_bank_dir, voice["ref_audio_path"])
    assert os.path.exists(abs_path), "Voice file should exist before delete"

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        await delete_voice(db, voice["id"], "test-user")

    # Record should be gone
    deleted = await db.get_voice_sample(voice["id"])
    assert deleted is None

    # File should be deleted
    assert not os.path.exists(abs_path), "Voice file should be deleted"


@pytest.mark.asyncio
async def test_delete_voice_not_owner(voice_bank_dir, db):
    """Try to delete another user's voice -> raises ValueError."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="owner-user",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Owner Voice",
            gender="male",
            age_group="adult",
        )

    with pytest.raises(ValueError, match="You do not own"):
        await delete_voice(db, voice["id"], "other-user")


# =============================================================================
# Vote Tests
# =============================================================================


@pytest.mark.asyncio
async def test_vote_voice(voice_bank_dir, db):
    """Vote +1 -> score increases."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="owner",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Voteable Voice",
            gender="male",
            age_group="adult",
        )

    await publish_voice(db, voice["id"], "owner")

    score = await vote_voice(db, voice["id"], "voter-1", 1)
    assert score == 1

    score = await vote_voice(db, voice["id"], "voter-2", 1)
    assert score == 2


@pytest.mark.asyncio
async def test_vote_voice_change(voice_bank_dir, db):
    """Vote +1 then change to -1 -> score reflects latest."""
    audio_path = _make_valid_wav(voice_bank_dir, duration_s=5)

    with patch("vvr_scraper.voice_bank.storage.get_voice_bank_dir", return_value=voice_bank_dir):
        voice = await upload_voice(
            db=db,
            user_id="owner",
            audio_file_path=audio_path,
            ref_text="Xin chào, đây là giọng nói của tôi",
            name="Voteable Voice",
            gender="female",
            age_group="adult",
        )

    await publish_voice(db, voice["id"], "owner")

    await vote_voice(db, voice["id"], "voter-a", 1)
    score = await vote_voice(db, voice["id"], "voter-b", 1)
    assert score == 2

    # Change vote from +1 to -1
    await vote_voice(db, voice["id"], "voter-a", -1)
    score = await vote_voice(db, voice["id"], "voter-b", 1)
    assert score == 0  # -1 + 1 = 0
