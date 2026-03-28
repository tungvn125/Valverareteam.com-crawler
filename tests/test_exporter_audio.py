import pytest
import os
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem

@pytest.mark.asyncio
async def test_tao_file_audiodrama_flow(tmp_path):
    """Tests the full orchestration flow of tao_file_audiodrama with mocks."""
    filename = str(tmp_path / "test_drama.mp3")
    script_file = f"{filename}.script.json"
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Narrator text. Character: Hello!")]
    
    # Mock DB manager
    mock_db = MagicMock()
    # Mocking aiosqlite-like behavior if needed, but here it's just a db_manager passed to VoiceManager
    mock_db.get_character_voice = AsyncMock(return_value="Binh")
    mock_db.save_character_voice = AsyncMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    mock_script = [
        {"role": "narrator", "text": "Narrator text."},
        {"role": "Character", "text": "Hello!"}
    ]
    
    # Mock OpenAIParser
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)
        
        # Mock Vieneu and numpy
        # Use patch.dict for os.environ to avoid side effects
        with patch.dict(os.environ, {"TF_CPP_MIN_LOG_LEVEL": "3"}), \
             patch("vieneu.Vieneu") as MockVieneu, \
             patch("numpy.concatenate") as mock_concat:
            
            tts_instance = MockVieneu.return_value
            tts_instance.get_preset_voice.return_value = "fake_voice_data"
            tts_instance.infer.return_value = "fake_audio"
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            # Verify OpenAI was called
            parser_instance.parse_chapter.assert_called_once()
            
            # Verify script checkpoint was saved
            assert os.path.exists(script_file)
            with open(script_file, 'r', encoding='utf-8') as f:
                saved_script = json.load(f)
            assert saved_script == mock_script
            
            # Verify Vieneu was called for each segment
            assert tts_instance.infer.call_count == 2
            
            # Verify merge and save
            mock_concat.assert_called_once()
            tts_instance.save.assert_called_once()

@pytest.mark.asyncio
async def test_tao_file_audiodrama_with_cache(tmp_path):
    """Tests that tao_file_audiodrama uses the cached script if available."""
    filename = str(tmp_path / "cached_drama.mp3")
    script_file = f"{filename}.script.json"
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]
    
    cached_script = [{"role": "narrator", "text": "Cached text"}]
    with open(script_file, 'w', encoding='utf-8') as f:
        json.dump(cached_script, f)
        
    mock_db = MagicMock()
    mock_db.get_character_voice = AsyncMock(return_value="Ly")
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        # Vieneu mock
        with patch("vieneu.Vieneu") as MockVieneu, \
             patch("numpy.concatenate") as mock_concat:
            
            tts_instance = MockVieneu.return_value
            tts_instance.get_preset_voice.return_value = "fake_voice_data"
            tts_instance.infer.return_value = "fake_audio"
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            # OpenAI should NOT be called
            MockParser.assert_not_called()
            
            # Vieneu should be called for cached segment
            assert tts_instance.infer.call_count == 1

@pytest.mark.asyncio
async def test_tao_file_audiodrama_fallback(tmp_path):
    """Tests that tao_file_audiodrama falls back to tao_file_mp3 on error."""
    filename = str(tmp_path / "fallback_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]
    
    mock_db = MagicMock()
    mock_db.get_character_voice = AsyncMock(return_value="Binh")
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    # Mock OpenAIParser
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=[{"character": "n", "text": "t"}])
        
        # Mock Vieneu to raise an error
        with patch("vieneu.Vieneu", side_effect=Exception("TTS Error")), \
             patch("vvr_scraper.exporter.tao_file_mp3") as mock_fallback:
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            # Verify fallback was called
            mock_fallback.assert_called_once()
