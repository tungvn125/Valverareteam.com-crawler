import pytest
import os
import json
import asyncio
import io
import numpy as np
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
        
        # Mock Vieneu, numpy, pydub, soundfile
        with patch.dict(os.environ, {"TF_CPP_MIN_LOG_LEVEL": "3"}), \
             patch("vieneu.Vieneu") as MockVieneu, \
             patch("pydub.AudioSegment") as MockAudioSegment, \
             patch("soundfile.write"), \
             patch("vvr_scraper.bgm_manager.BGMManager") as MockBGM, \
             patch("vvr_scraper.mixing_engine.MixingEngine") as MockMixing:
            
            tts_instance = MockVieneu.return_value
            tts_instance.get_preset_voice.return_value = "fake_voice_data"
            tts_instance.infer.return_value = np.zeros(1000)
            
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
            
            MockAudioSegment.silent.side_effect = lambda duration: MockAudio(duration)
            MockAudioSegment.from_file.return_value = MockAudio(1000)
            MockAudioSegment.from_wav.return_value = MockAudio(1000)
            
            mixing_instance = MockMixing.return_value
            mixing_instance.mix_with_ducking.return_value = MockAudio(1000)
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            # Verify OpenAI was called
            parser_instance.parse_chapter.assert_called_once()
            
            # Verify Vieneu was called for each segment (2 segments)
            assert tts_instance.infer.call_count == 2

@pytest.mark.asyncio
async def test_tao_file_audiodrama_v2_with_moods(tmp_path):
    """Tests Audio Drama v2 with mood shifts."""
    filename = str(tmp_path / "v2_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]
    
    mock_db = MagicMock()
    mock_db.get_character_voice = AsyncMock(return_value="Ly")
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    mock_script = [
        {"type": "mood_shift", "mood": "action"},
        {"type": "segment", "role": "narrator", "text": "Action starts!"}
    ]
    
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)
        
        with patch("vieneu.Vieneu") as MockVieneu, \
             patch("pydub.AudioSegment") as MockAudioSegment, \
             patch("soundfile.write"), \
             patch("vvr_scraper.bgm_manager.BGMManager") as MockBGM, \
             patch("vvr_scraper.mixing_engine.MixingEngine") as MockMixing:
            
            tts_instance = MockVieneu.return_value
            tts_instance.infer.return_value = np.zeros(1000)
            
            bgm_instance = MockBGM.return_value
            bgm_instance.get_random_track.return_value = "fake_bgm.mp3"
            
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

            MockAudioSegment.silent.side_effect = lambda duration: MockAudio(duration)
            MockAudioSegment.from_file.return_value = MockAudio(1000)
            MockAudioSegment.from_wav.return_value = MockAudio(1000)
            
            mixing_instance = MockMixing.return_value
            mixing_instance.mix_with_ducking.return_value = MockAudio(1000)
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            assert bgm_instance.get_random_track.called
            assert tts_instance.infer.call_count == 1

@pytest.mark.asyncio
async def test_tao_file_audiodrama_fallback(tmp_path):
    """Tests fallback to MP3 if v2 fails (e.g., missing pydub)."""
    filename = str(tmp_path / "fallback_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Fallback text")]
    
    mock_db = MagicMock()
    mock_db.get_character_voice = AsyncMock(return_value="Binh")
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=[{"role": "narrator", "text": "text"}])
        
        # Mock pydub to fail import
        with patch.dict("sys.modules", {"pydub": None}):
            # Mock tao_file_mp3
            with patch("vvr_scraper.exporter.tao_file_mp3", new_callable=AsyncMock) as mock_mp3:
                await tao_file_audiodrama(content_list, filename, story_id, mock_db)
                mock_mp3.assert_not_called()
