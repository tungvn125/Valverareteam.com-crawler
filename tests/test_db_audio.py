import pytest

from vvr_scraper.db import DatabaseManager


@pytest.mark.asyncio
async def test_character_voice_persistence(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    await db.init_db()

    # Test initial save
    await db.save_character_voice("story1", "Character A", "Hung")
    voice = await db.get_character_voice("story1", "Character A")
    assert voice == "Hung"

    # Test update (ON CONFLICT)
    await db.save_character_voice("story1", "Character A", "Lan")
    voice = await db.get_character_voice("story1", "Character A")
    assert voice == "Lan"

    # Test multiple characters in same story
    await db.save_character_voice("story1", "Character B", "Mai")
    assert await db.get_character_voice("story1", "Character A") == "Lan"
    assert await db.get_character_voice("story1", "Character B") == "Mai"

    # Test multiple stories
    await db.save_character_voice("story2", "Character A", "Nam")
    assert await db.get_character_voice("story1", "Character A") == "Lan"
    assert await db.get_character_voice("story2", "Character A") == "Nam"

    # Test unknown
    assert await db.get_character_voice("story1", "Unknown") is None
    assert await db.get_character_voice("unknown_story", "Character A") is None


@pytest.mark.asyncio
async def test_character_voice_with_ref_audio(tmp_path):
    from vvr_scraper.models import CharacterProfile

    db_path = tmp_path / "test_ref.db"
    db = DatabaseManager(str(db_path))
    await db.init_db()

    profile = CharacterProfile(
        name="Hero",
        story_id="story1",
        gender="male",
        voice_id="abc123",
        ref_audio_path="voices/hero/sample.wav",
        ref_text="I am the hero of this story.",
    )
    await db.save_character_profile(profile)

    loaded = await db.get_character_profiles("story1")
    assert len(loaded) == 1
    assert loaded[0].ref_audio_path == "voices/hero/sample.wav"
    assert loaded[0].ref_text == "I am the hero of this story."
    assert loaded[0].voice_id == "abc123"
