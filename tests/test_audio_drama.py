import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import OpenAIParser, VoiceManager
from vvr_scraper.tts.base import VoiceSpec


@pytest.mark.asyncio
async def test_openai_parser_success():
    """Tests OpenAIParser with a successful mocked response."""
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock()

        mock_message = MagicMock()
        mock_message.content = json.dumps(
            {
                "script": [
                    {"type": "segment", "role": "narrator", "text": "Đó là một ngày nắng đẹp.", "gender": "unknown"},
                    {"type": "segment", "role": "Nam", "text": "Chào buổi sáng!", "gender": "male"},
                ]
            }
        )
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        parser = OpenAIParser(api_key="fake_key", base_url="fake_url")
        result = await parser.parse_chapter("Nội dung chương truyện...")

        assert len(result) == 2
        assert result[0]["role"] == "narrator"
        assert result[1]["role"] == "Nam"
        assert result[1]["text"] == "Chào buổi sáng!"


@pytest.mark.asyncio
async def test_openai_parser_mood_shift_tags():
    """Tests OpenAIParser with mood_shift containing tags (v2.5)."""
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock()

        mock_message = MagicMock()
        # Mocking new LLM output format
        mock_message.content = json.dumps(
            {
                "script": [
                    {"type": "mood_shift", "tags": ["mysterious", "dark piano"]},
                    {"type": "segment", "role": "narrator", "text": "He entered the room.", "gender": "unknown"},
                    # Backward compatibility: old format
                    {"type": "mood_shift", "mood": "action"},
                ]
            }
        )
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        parser = OpenAIParser(api_key="fake_key", base_url="fake_url")
        result = await parser.parse_chapter("Nội dung...")

        assert len(result) == 3
        # Check first mood shift (new format)
        assert result[0]["type"] == "mood_shift"
        assert result[0]["tags"] == ["mysterious", "dark piano"]
        # It should probably also have 'mood' for backward compatibility with old exporter
        assert result[0]["mood"] == "mysterious"

        # Check second mood shift (old format)
        assert result[2]["type"] == "mood_shift"
        assert result[2].get("tags") == ["action"]
        assert result[2]["mood"] == "action"


@pytest.mark.asyncio
async def test_openai_parser_mood_shift_edge_cases():
    """Tests OpenAIParser with weird mood_shift inputs."""
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(
            {
                "script": [
                    {"type": "mood_shift", "tags": "mysterious"},  # String instead of list
                    {"type": "mood_shift", "tags": None},  # None
                    {"type": "mood_shift"},  # Missing both
                ]
            }
        )
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        parser = OpenAIParser(api_key="fake_key", base_url="fake_url")
        result = await parser.parse_chapter("...")

        assert len(result) == 3
        # String case
        assert result[0]["tags"] == ["mysterious"]
        assert result[0]["mood"] == "mysterious"

        # None case
        assert result[1]["tags"] == []
        assert result[1].get("mood") is None

        # Missing case
        assert result[2]["tags"] == []
        assert result[2].get("mood") is None


@pytest.mark.asyncio
async def test_openai_parser_error():
    """Tests OpenAIParser handling of errors and verification of MAX_RETRIES."""
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        parser = OpenAIParser(api_key="fake_key", base_url="fake_url")
        # In non-interactive mode (default in tests), it should retry up to MAX_RETRIES and then raise RuntimeError
        with pytest.raises(RuntimeError):
            await parser.parse_chapter("Nội dung...")

        # Verify it retried exactly MAX_RETRIES (3) times
        assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_voice_manager_narrator():
    """Tests that VoiceManager always returns narrator_voice for narrator."""
    mock_db = MagicMock()
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)

    # Direct "narrator"
    assert await vm.get_voice("narrator") == vm.narrator_voice
    # Case insensitive
    assert await vm.get_voice("NARRATOR") == vm.narrator_voice
    # Empty name
    assert await vm.get_voice("") == vm.narrator_voice
    assert await vm.get_voice(None) == vm.narrator_voice


@pytest.mark.asyncio
async def test_voice_manager_assignment_and_persistence():
    """Tests voice assignment and DB persistence for characters."""
    # Save original global state
    orig_voices = VoiceManager._global_available_voices
    orig_metadata = VoiceManager._global_voice_metadata

    try:
        # Reset global state for testing and mock no available voices
        VoiceManager._global_available_voices = []
        VoiceManager._global_voice_metadata = {}

        mock_db = MagicMock()
        mock_db.save_character_voice = AsyncMock()
        mock_db.get_all_story_voices = AsyncMock(return_value={})
        mock_db.get_character_profiles = AsyncMock(return_value=[])
        mock_db.save_character_profile = AsyncMock()

        story_id = "story_123"
        vm = VoiceManager(mock_db, story_id)

        # 1. New character assignment (with no available voices)
        char_name = "Lâm"
        # Force _initialized so it doesn't try to fetch from real API
        vm._initialized = True

        voice1 = await vm.get_voice(char_name)
        # By default, with no available voices, it should fallback to narrator_voice
        assert voice1 == vm.narrator_voice
        # Should have saved to DB with normalized name
        mock_db.save_character_profile.assert_called_once()
        saved_profile = mock_db.save_character_profile.call_args[0][0]
        assert saved_profile.name == "Lâm"
        assert saved_profile.voice_id == voice1.voice_id

        # 2. Existing character from cache
        voice2 = await vm.get_voice(char_name)
        assert voice2 == voice1
        # Should NOT have saved to DB again (it was already in DB/cache)
        assert mock_db.save_character_profile.call_count == 1
    finally:
        # Cleanup: restore original global state
        VoiceManager._global_available_voices = orig_voices
        VoiceManager._global_voice_metadata = orig_metadata


@pytest.mark.asyncio
async def test_voice_manager_gender_aware():
    """Tests that VoiceManager respects gender labels if available."""
    # Save original global state
    orig_voices = VoiceManager._global_available_voices
    orig_metadata = VoiceManager._global_voice_metadata

    try:
        # Reset and mock global state
        VoiceManager._global_available_voices = ["voice_m1", "voice_f1", "voice_n1"]
        VoiceManager._global_voice_metadata = {
            "voice_m1": {"name": "Male Voice", "gender": "male"},
            "voice_f1": {"name": "Female Voice", "gender": "female"},
            "voice_n1": {"name": "Neutral Voice", "gender": "neutral"},
        }

        mock_db = MagicMock()
        mock_db.save_character_voice = AsyncMock()
        mock_db.get_all_story_voices = AsyncMock(return_value={})
        mock_db.get_character_profiles = AsyncMock(return_value=[])
        mock_db.save_character_profile = AsyncMock()

        story_id = "story_gender"
        vm = VoiceManager(mock_db, story_id)

        # 1. Request male voice
        v_male = await vm.get_voice("Nam", gender="male")
        assert v_male == VoiceSpec(voice_id="voice_m1")

        # 2. Request female voice
        v_female = await vm.get_voice("Nữ", gender="female")
        assert v_female == VoiceSpec(voice_id="voice_f1")

        # 3. Request unknown gender (should pick from remaining, but excluding narrator if possible)
        # Since narrator is DEFAULT_NARRATOR_VOICE_ID and not in _global_available_voices,
        # candidates will be all available voices.
        v_unknown = await vm.get_voice("Ai Đó", gender="unknown")
        assert v_unknown.voice_id in ["voice_m1", "voice_f1", "voice_n1"]
        # Variety maximization: since m1 and f1 are already assigned in this instance cache,
        # it should prefer n1 if it considers assigned_ids.
        assert v_unknown == VoiceSpec(voice_id="voice_n1")
    finally:
        # Cleanup: restore original global state
        VoiceManager._global_available_voices = orig_voices
        VoiceManager._global_voice_metadata = orig_metadata


@pytest.mark.asyncio
async def test_voice_manager_normalization():
    """Tests that VoiceManager normalizes names (case-insensitive, stripped)."""
    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={"nam": "voice_1"})
    mock_db.get_character_profiles = AsyncMock(return_value=[])
    mock_db.save_character_profile = AsyncMock()

    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)

    # "Nam" vs " nam " vs "NAM"
    assert await vm.get_voice("Nam") == VoiceSpec(voice_id="voice_1")
    assert await vm.get_voice(" nam ") == VoiceSpec(voice_id="voice_1")
    assert await vm.get_voice("NAM") == VoiceSpec(voice_id="voice_1")

    # Only queried once via _init_cache
    assert mock_db.get_all_story_voices.call_count == 1
