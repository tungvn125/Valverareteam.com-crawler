import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.audio_drama import GeminiParser, VoiceManager

@pytest.mark.asyncio
async def test_gemini_parser_success():
    """Tests GeminiParser with a successful mocked response."""
    with patch("google.generativeai.GenerativeModel") as MockModel:
        mock_model_instance = MockModel.return_value
        mock_response = MagicMock()
        mock_response.text = json.dumps([
            {"role": "narrator", "text": "Đó là một ngày nắng đẹp."},
            {"role": "Nam", "text": "Chào buổi sáng!"}
        ])
        mock_model_instance.generate_content_async = AsyncMock(return_value=mock_response)
        
        parser = GeminiParser(api_key="fake_key")
        result = await parser.parse_chapter("Nội dung chương truyện...")
        
        assert len(result) == 2
        assert result[0]["role"] == "narrator"
        assert result[1]["role"] == "Nam"
        assert result[1]["text"] == "Chào buổi sáng!"

@pytest.mark.asyncio
async def test_gemini_parser_error():
    """Tests GeminiParser handling of errors."""
    with patch("google.generativeai.GenerativeModel") as MockModel:
        mock_model_instance = MockModel.return_value
        mock_model_instance.generate_content_async = AsyncMock(side_effect=Exception("API Error"))
        
        parser = GeminiParser(api_key="fake_key")
        result = await parser.parse_chapter("Nội dung...")
        
        assert result == []

@pytest.mark.asyncio
async def test_voice_manager_narrator():
    """Tests that VoiceManager always returns 'Tuyen' for narrator."""
    mock_db = MagicMock()
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)
    
    # Direct "narrator"
    assert await vm.get_voice("narrator") == "Tuyen"
    # Case insensitive
    assert await vm.get_voice("NARRATOR") == "Tuyen"
    # Empty name
    assert await vm.get_voice("") == "Tuyen"
    assert await vm.get_voice(None) == "Tuyen"
    
    # DB should not be queried for narrator
    mock_db.get_character_voice.assert_not_called()

@pytest.mark.asyncio
async def test_voice_manager_assignment_and_persistence():
    """Tests voice assignment and DB persistence for characters."""
    mock_db = MagicMock()
    # First time returns None (not in DB), second time returns "Hung"
    mock_db.get_character_voice = AsyncMock(side_effect=[None, "Hung"])
    mock_db.save_character_voice = AsyncMock()
    
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)
    
    # 1. New character assignment
    char_name = "Lâm"
    voice1 = await vm.get_voice(char_name)
    assert voice1 in VoiceManager.DEFAULT_VOICES
    # Should have checked DB with normalized name
    mock_db.get_character_voice.assert_called_with(story_id, "lâm")
    # Should have saved to DB with normalized name
    mock_db.save_character_voice.assert_called_with(story_id, "lâm", voice1)
    
    # 2. Existing character from DB
    voice2 = await vm.get_voice(char_name)
    assert voice2 == "Hung"
    # Should NOT have saved to DB again (it was already in DB)
    assert mock_db.save_character_voice.call_count == 1

@pytest.mark.asyncio
async def test_voice_manager_normalization():
    """Tests that VoiceManager normalizes names (case-insensitive, stripped)."""
    mock_db = MagicMock()
    mock_db.get_character_voice = AsyncMock(return_value="Mai")
    
    story_id = "story_123"
    vm = VoiceManager(mock_db, story_id)
    
    # "Nam" vs " nam " vs "NAM"
    assert await vm.get_voice("Nam") == "Mai"
    assert await vm.get_voice(" nam ") == "Mai"
    assert await vm.get_voice("NAM") == "Mai"
    
    # All should have queried the DB with the same normalized key "nam"
    assert mock_db.get_character_voice.call_count == 3
    mock_db.get_character_voice.assert_called_with(story_id, "nam")
