import pytest
import os
import tempfile
from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "voice_bank.db")
        manager = VoiceBankDatabaseManager(db_path)
        await manager.init_db()
        yield manager
        await manager.close()


@pytest.mark.asyncio
async def test_init_db_creates_tables(db):
    tables = await db.list_table_names()
    assert "voice_samples" in tables
    assert "voice_votes" in tables
    assert "voice_tags" in tables


@pytest.mark.asyncio
async def test_create_and_get_voice_sample(db):
    voice_id = await db.create_voice_sample(
        user_id="local",
        name="Test Voice",
        description="A test voice",
        ref_audio_path="local/test-voice.wav",
        ref_text="Xin chào, đây là giọng test",
        duration_ms=5200,
        sample_rate=22050,
        gender="male",
        age_group="adult",
        language="vi",
        mood=None,
        visibility="private",
        file_hash="abc123",
    )
    assert voice_id is not None

    voice = await db.get_voice_sample(voice_id)
    assert voice["name"] == "Test Voice"
    assert voice["ref_audio_path"] == "local/test-voice.wav"
    assert voice["ref_text"] == "Xin chào, đây là giọng test"
    assert voice["gender"] == "male"
    assert voice["age_group"] == "adult"
    assert voice["visibility"] == "private"
    assert voice["usage_count"] == 0


@pytest.mark.asyncio
async def test_list_my_voices(db):
    v1 = await db.create_voice_sample(
        user_id="local", name="Voice 1", description="",
        ref_audio_path="local/v1.wav", ref_text="Giọng số một",
        duration_ms=3000, sample_rate=22050,
        gender="female", age_group="young_adult", language="vi",
        mood=None, visibility="private", file_hash="h1",
    )
    v2 = await db.create_voice_sample(
        user_id="local", name="Voice 2", description="",
        ref_audio_path="local/v2.wav", ref_text="Giọng số hai",
        duration_ms=4000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="public", file_hash="h2",
    )

    my_voices = await db.list_my_voices(user_id="local", limit=20, offset=0)
    assert my_voices["total"] == 2
    assert len(my_voices["items"]) == 2


@pytest.mark.asyncio
async def test_list_community_voices(db):
    await db.create_voice_sample(
        user_id="local", name="Public Voice", description="",
        ref_audio_path="local/pv.wav", ref_text="Giọng công khai",
        duration_ms=5000, sample_rate=22050,
        gender="female", age_group="teen", language="vi",
        mood=None, visibility="public", file_hash="h3",
    )
    await db.create_voice_sample(
        user_id="local", name="Private Voice", description="",
        ref_audio_path="local/pv2.wav", ref_text="Giọng riêng tư",
        duration_ms=6000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="private", file_hash="h4",
    )

    community = await db.list_community_voices(limit=20, offset=0)
    assert community["total"] == 1
    assert community["items"][0]["name"] == "Public Voice"


@pytest.mark.asyncio
async def test_publish_and_delist(db):
    voice_id = await db.create_voice_sample(
        user_id="local", name="V", description="",
        ref_audio_path="local/v.wav", ref_text="Giọng test",
        duration_ms=3000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="private", file_hash="h5",
    )

    await db.publish_voice(voice_id, user_id="local")
    voice = await db.get_voice_sample(voice_id)
    assert voice["visibility"] == "public"

    await db.delist_voice(voice_id, user_id="local")
    voice = await db.get_voice_sample(voice_id)
    assert voice["visibility"] == "delisted"


@pytest.mark.asyncio
async def test_vote_voice(db):
    voice_id = await db.create_voice_sample(
        user_id="local", name="V", description="",
        ref_audio_path="local/v.wav", ref_text="Giọng test",
        duration_ms=3000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="public", file_hash="h6",
    )

    await db.vote_voice(voice_id, "user_a", 1)
    await db.vote_voice(voice_id, "user_b", 1)
    await db.vote_voice(voice_id, "user_a", -1)  # change vote

    score = await db.get_vote_score(voice_id)
    # user_a changed from +1 to -1, so: -1 + 1 = 0
    assert score == 0


@pytest.mark.asyncio
async def test_add_and_list_tags(db):
    voice_id = await db.create_voice_sample(
        user_id="local", name="V", description="",
        ref_audio_path="local/v.wav", ref_text="Giọng test",
        duration_ms=3000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="public", file_hash="h7",
    )

    await db.set_tags(voice_id, ["tsundere", "hanoi-accent"])
    tags = await db.get_tags(voice_id)
    assert set(tags) == {"tsundere", "hanoi-accent"}


@pytest.mark.asyncio
async def test_find_best_voice(db):
    v1 = await db.create_voice_sample(
        user_id="u1", name="Male Adult", description="",
        ref_audio_path="u1/v1.wav", ref_text="Giọng nam trưởng thành",
        duration_ms=5000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="public", file_hash="h10",
    )
    await db.set_tags(v1, ["serious", "deep"])
    await db.vote_voice(v1, "user_a", 1)
    await db.vote_voice(v1, "user_b", 1)

    v2 = await db.create_voice_sample(
        user_id="u2", name="Male Adult 2", description="",
        ref_audio_path="u2/v2.wav", ref_text="Giọng nam khác",
        duration_ms=4000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="public", file_hash="h11",
    )
    await db.set_tags(v2, ["serious"])
    await db.vote_voice(v2, "user_c", 1)

    # Search with tag "serious" — v1 should rank higher (2 votes + tag match)
    best = await db.find_best_voice(gender="male", tags=["serious"])
    assert best is not None
    assert best["name"] == "Male Adult"


@pytest.mark.asyncio
async def test_duplicate_file_hash_rejected(db):
    await db.create_voice_sample(
        user_id="local", name="V1", description="",
        ref_audio_path="local/v1.wav", ref_text="Giọng 1",
        duration_ms=3000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="private", file_hash="dup_hash",
    )

    with pytest.raises(ValueError, match="Duplicate"):
        await db.create_voice_sample(
            user_id="local", name="V2", description="",
            ref_audio_path="local/v2.wav", ref_text="Giọng 2",
            duration_ms=3000, sample_rate=22050,
            gender="male", age_group="adult", language="vi",
            mood=None, visibility="private", file_hash="dup_hash",
        )


@pytest.mark.asyncio
async def test_delete_voice_removes_tags_and_votes(db):
    voice_id = await db.create_voice_sample(
        user_id="local", name="V", description="",
        ref_audio_path="local/v.wav", ref_text="Giọng test",
        duration_ms=3000, sample_rate=22050,
        gender="male", age_group="adult", language="vi",
        mood=None, visibility="private", file_hash="h_del",
    )
    await db.set_tags(voice_id, ["tag1"])
    await db.vote_voice(voice_id, "user_a", 1)

    await db.delete_voice_sample(voice_id, user_id="local")
    assert await db.get_voice_sample(voice_id) is None
    assert await db.get_tags(voice_id) == []
