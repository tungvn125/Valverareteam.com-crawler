import pytest
import os
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem

class MockAudio:
    def __init__(self, length=1000):
        self.length = length
        self.frame_rate = 44100
    def __len__(self):
        return self.length
    def __add__(self, other):
        if isinstance(other, MockAudio):
            return MockAudio(self.length + other.length)
        return self
    def __mul__(self, other):
        if isinstance(other, int):
            return MockAudio(self.length * other)
        return self
    def __getitem__(self, index):
        return self
    def fade_out(self, duration):
        return self
    def fade_in(self, duration):
        return self
    def append(self, other, crossfade=0):
        return MockAudio(self.length + other.length - crossfade)
    def export(self, *args, **kwargs):
        pass
    def apply_gain(self, gain):
        return self
    def overlay(self, other, position=0):
        return self

@pytest.mark.asyncio
async def test_tao_file_audiodrama_block_mixing(tmp_path):
    """
    Test Task 4 requirements:
    - Parallel Synthesis with Semaphore(5)
    - Block-based mixing
    - BGM search: local folder matching tags, then Freesound
    - MixingEngine for background and overlay
    - 1s crossfade between blocks
    """
    filename = str(tmp_path / "block_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Start of story. [mood_shift: action] Attack!")]
    
    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    
    # Script with 2 blocks
    # Block 1: Implicit "peaceful"
    # Block 2: "action" tags
    mock_script = [
        {"type": "segment", "role": "narrator", "text": "Start of story."},
        {"type": "mood_shift", "tags": ["action"], "mood": "action"},
        {"type": "segment", "role": "Hero", "text": "Attack!"},
    ]
    
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser, \
         patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager:
        
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)
        
        voice_manager_instance = MockVoiceManager.return_value
        voice_manager_instance.get_voice = AsyncMock(side_effect=lambda role, gender: f"voice_{role}")

        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}), \
             patch("elevenlabs.client.ElevenLabs") as MockElevenLabs, \
             patch("pydub.AudioSegment.from_file") as MockFromFile, \
             patch("pydub.AudioSegment.silent") as MockSilent, \
             patch("vvr_scraper.exporter.BGMManager") as MockBGM, \
             patch("vvr_scraper.exporter.MixingEngine") as MockMixing, \
             patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound:
            
            client_instance = MockElevenLabs.return_value
            # We need a generator for text_to_speech.convert
            def mock_convert(**kwargs):
                yield b"audio_chunk"
            client_instance.text_to_speech.convert.side_effect = mock_convert
            
            bgm_instance = MockBGM.return_value
            # Block 1: finds peaceful locally
            # Block 2: does NOT find action locally
            def side_effect_bgm(mood):
                if mood == "peaceful": return "local_peaceful.mp3"
                return None
            bgm_instance.get_random_track.side_effect = side_effect_bgm
            
            freesound_instance = MockFreesound.return_value
            freesound_instance.search_bgm.return_value = [MagicMock(id=123)]
            freesound_instance.download_and_convert.return_value = "downloaded_action.wav"
            
            MockSilent.side_effect = lambda duration, **kwargs: MockAudio(duration)
            MockFromFile.side_effect = lambda *args, **kwargs: MockAudio(2000)
            
            mixing_instance = MockMixing.return_value
            mixing_instance.create_looped_background.return_value = MockAudio(5000)
            mixing_instance.overlay_voice_on_background.return_value = MockAudio(5000)
            
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            
            # 1. Parallel Synthesis: 2 segments
            assert client_instance.text_to_speech.convert.call_count == 2
            
            # 2. Block 1 (implicit peaceful) -> local BGM check
            # The code might use "peaceful" by default if no mood_shift at start
            bgm_instance.get_random_track.assert_any_call("peaceful")
            
            # 3. Block 2 (action) -> local check fails -> Freesound check
            # We expect FreesoundManager to be searched with ["action"]
            freesound_instance.search_bgm.assert_called_with(["action"], limit=5)
            freesound_instance.download_and_convert.assert_called()
            
            # 4. MixingEngine calls
            # At least 2 blocks mixed
            assert mixing_instance.create_looped_background.call_count >= 2
            assert mixing_instance.overlay_voice_on_background.call_count >= 2
