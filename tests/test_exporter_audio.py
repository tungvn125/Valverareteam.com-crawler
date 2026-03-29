import pytest
import os
import json
import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem

class MockAudio:
    def __init__(self, length=1000):
        self.length = length
    def __len__(self):
        return self.length
    def __add__(self, other):
        return MockAudio(self.length + len(other))
    def __getitem__(self, index):
        return self
    def fade_out(self, duration):
        return self
    def export(self, *args, **kwargs):
        pass
    def apply_gain(self, gain):
        return self
    def overlay(self, other, position=0):
        return self

@pytest.mark.asyncio
async def test_tao_file_audiodrama_flow(tmp_path):
    """Tests the full orchestration flow of tao_file_audiodrama with ElevenLabs mocks."""
    filename = str(tmp_path / "test_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Narrator text. Character: Hello!")]
    
    # Mock DB manager
    mock_db = MagicMock()
    mock_db.save_character_voice = AsyncMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    mock_script = [
        {"type": "segment", "role": "narrator", "text": "Narrator text."},
        {"type": "segment", "role": "Character", "text": "Hello!"}
    ]
    
    # Mock OpenAIParser
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)
        
        # Mock ElevenLabs, pydub
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}), \
             patch("elevenlabs.client.ElevenLabs") as MockElevenLabs, \
             patch("pydub.AudioSegment.from_file") as MockFromFile, \
             patch("pydub.AudioSegment.silent") as MockSilent, \
             patch("vvr_scraper.bgm_manager.BGMManager") as MockBGM, \
             patch("vvr_scraper.mixing_engine.MixingEngine") as MockMixing:
            
            client_instance = MockElevenLabs.return_value
            client_instance.generate.return_value = [b"fake_audio_chunk"]
            
            MockSilent.side_effect = lambda duration: MockAudio(duration)
            MockFromFile.return_value = MockAudio(1000)
            
            mixing_instance = MockMixing.return_value
            mixing_instance.mix_with_ducking.return_value = MockAudio(1000)
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            # Verify OpenAI was called
            parser_instance.parse_chapter.assert_called_once()
            
            # Verify ElevenLabs was called for each segment (2 segments)
            assert client_instance.generate.call_count == 2

@pytest.mark.asyncio
async def test_tao_file_audiodrama_v2_with_moods(tmp_path):
    """Tests Audio Drama v2 with mood shifts and ElevenLabs."""
    filename = str(tmp_path / "v2_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]
    
    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    mock_script = [
        {"type": "mood_shift", "mood": "action"},
        {"type": "segment", "role": "narrator", "text": "Action starts!"}
    ]
    
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)
        
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}), \
             patch("elevenlabs.client.ElevenLabs") as MockElevenLabs, \
             patch("pydub.AudioSegment.from_file") as MockFromFile, \
             patch("pydub.AudioSegment.silent") as MockSilent, \
             patch("vvr_scraper.bgm_manager.BGMManager") as MockBGM, \
             patch("vvr_scraper.mixing_engine.MixingEngine") as MockMixing:
            
            client_instance = MockElevenLabs.return_value
            client_instance.generate.return_value = [b"audio"]
            
            bgm_instance = MockBGM.return_value
            bgm_instance.get_random_track.return_value = "fake_bgm.mp3"
            
            MockSilent.side_effect = lambda duration: MockAudio(duration)
            MockFromFile.return_value = MockAudio(1000)
            
            mixing_instance = MockMixing.return_value
            mixing_instance.mix_with_ducking.return_value = MockAudio(1000)
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            assert bgm_instance.get_random_track.called
            assert client_instance.generate.call_count == 1

@pytest.mark.asyncio
async def test_tao_file_mp3_flow(tmp_path):
    """Tests the audiobook generation flow with ElevenLabs."""
    from vvr_scraper.exporter import tao_file_mp3
    filename = str(tmp_path / "test_audiobook.mp3")
    content_list = [ContentItem(type="text", data="Chapter text here.")]
    
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}), \
         patch("elevenlabs.client.ElevenLabs") as MockElevenLabs, \
         patch("pydub.AudioSegment.from_file") as MockFromFile:
        
        client_instance = MockElevenLabs.return_value
        client_instance.generate.return_value = [b"chunk1"]
            
        MockFromFile.return_value = MockAudio(1000)
        
        await tao_file_mp3(content_list, filename, "Test Title")
        
        # Should be called for title and text
        assert client_instance.generate.call_count == 2

@pytest.mark.asyncio
async def test_tao_file_audiodrama_fallback(tmp_path):
    """Tests fallback behavior (should fail gracefully if API key missing)."""
    filename = str(tmp_path / "fallback.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="text")]
    
    mock_db = MagicMock()
    
    # Don't use clear=True to preserve PATH for pydub
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}):
        with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
            parser_instance = MockParser.return_value
            parser_instance.parse_chapter = AsyncMock(return_value=[{"type": "segment", "role": "narrator", "text": "text"}])
            
            # Should log error and return
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            assert not os.path.exists(filename)
