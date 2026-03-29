import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.audio_drama import OpenAIParser, VoiceManager

@pytest.mark.asyncio
async def test_openai_parser_success():
    """Tests OpenAIParser with a successful mocked response."""
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock()
        
        mock_message = MagicMock()
        mock_message.content = json.dumps({
            "script": [
                {"type": "segment", "role": "narrator", "text": "Đó là một ngày nắng đẹp.", "gender": "unknown"},
                {"type": "segment", "role": "Nam", "text": "Chào buổi sáng!", "gender": "male"}
            ]
        })
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
async def test_openai_parser_error():
    """Tests OpenAIParser handling of errors."""
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        
        parser = OpenAIParser(api_key="fake_key", base_url="fake_url")
        result = await parser.parse_chapter("Nội dung...")
        
        assert result == []

@pytest.mark.asyncio
async def test_voice_manager_narrator():
    """Tests that VoiceManager always returns NARRATOR_VOICE_ID for narrator."""
    from vvr_scraper.audio_drama import VoiceManager
    mock_db = MagicMock()
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)
    
    # Direct "narrator"
    assert await vm.get_voice("narrator") == VoiceManager.NARRATOR_VOICE_ID
    # Case insensitive
    assert await vm.get_voice("NARRATOR") == VoiceManager.NARRATOR_VOICE_ID
    # Empty name
    assert await vm.get_voice("") == VoiceManager.NARRATOR_VOICE_ID
    assert await vm.get_voice(None) == VoiceManager.NARRATOR_VOICE_ID

@pytest.mark.asyncio
async def test_voice_manager_assignment_and_persistence():
    """Tests voice assignment and DB persistence for characters."""
    from vvr_scraper.audio_drama import VoiceManager
    mock_db = MagicMock()
    mock_db.save_character_voice = AsyncMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)
    
    # 1. New character assignment
    char_name = "Lâm"
    voice1 = await vm.get_voice(char_name)
    # By default, without API key, it should fallback to NARRATOR_VOICE_ID
    assert voice1 == VoiceManager.NARRATOR_VOICE_ID
    # Should have saved to DB with normalized name
    mock_db.save_character_voice.assert_called_with(story_id, "lâm", voice1)
    
    # 2. Existing character from cache
    voice2 = await vm.get_voice(char_name)
    assert voice2 == voice1
    # Should NOT have saved to DB again (it was already in DB/cache)
    assert mock_db.save_character_voice.call_count == 1

@pytest.mark.asyncio
async def test_voice_manager_normalization():
    """Tests that VoiceManager normalizes names (case-insensitive, stripped)."""
    from vvr_scraper.audio_drama import VoiceManager
    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={"nam": "voice_1"})
    
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)
    
    # "Nam" vs " nam " vs "NAM"
    assert await vm.get_voice("Nam") == "voice_1"
    assert await vm.get_voice(" nam ") == "voice_1"
    assert await vm.get_voice("NAM") == "voice_1"
    
    # Only queried once via _init_cache
    assert mock_db.get_all_story_voices.call_count == 1
