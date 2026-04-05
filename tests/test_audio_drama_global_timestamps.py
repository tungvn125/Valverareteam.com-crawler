import pytest
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem

@pytest.mark.asyncio
async def test_global_timestamp_calculation():
    # Mock data
    content_list = [ContentItem(type="text", data="Hắn bước vào. Gió thổi mạnh.")]
    filename = "test_audio_drama.mp3"
    story_id = "test_story"
    db_manager = MagicMock()
    
    # Mock ScriptResult and its blocks
    mock_script = [
        {"type": "mood_shift", "tags": ["mysterious"]},
        {"type": "segment", "role": "narrator", "text": "Hắn bước vào.", "voice": "voice1"},
        {"type": "mood_shift", "tags": ["action"]},
        {"type": "segment", "role": "narrator", "text": "Gió thổi mạnh.", "voice": "voice1"}
    ]
    
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser, \
         patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager, \
         patch("vvr_scraper.exporter.BGMManager") as MockBGMManager, \
         patch("vvr_scraper.exporter.FreesoundManager") as MockFreesoundManager, \
         patch("vvr_scraper.exporter.MixingEngine") as MockMixingEngine, \
         patch("pydub.AudioSegment.from_file") as MockAudioFromFile, \
         patch("pydub.AudioSegment.silent") as MockSilent, \
         patch("os.getenv", return_value="fake_key"):
        
        # Mock Parser
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)
        
        # Mock VoiceManager
        vm_instance = MockVoiceManager.return_value
        vm_instance.get_voice = AsyncMock(return_value="voice1")
        
        # Mock synthesis to return 2s audio and some alignments
        mock_audio_bytes = b"fake audio"
        async def get_mock_alignments(*args, **kwargs):
            return mock_audio_bytes, [
                {"characters": "Hắn", "start_time_ms": 100, "end_time_ms": 200},
                {"characters": "bước", "start_time_ms": 300, "end_time_ms": 400}
            ]
        vm_instance.synthesize.side_effect = get_mock_alignments
        
        # Mock AudioSegment
        mock_voice_segment = MagicMock()
        mock_voice_segment.__len__.return_value = 2000 # 2 seconds
        mock_voice_segment.fade_in.return_value = mock_voice_segment
        mock_voice_segment.fade_out.return_value = mock_voice_segment
        
        mock_block_audio = MagicMock()
        mock_block_audio.__len__.return_value = 4000 # 4 seconds (bg_duration)
        mock_block_audio.append.return_value = mock_block_audio
        
        MockSilent.return_value = mock_voice_segment
        MockAudioFromFile.return_value = mock_voice_segment
        
        # Mock MixingEngine
        me_instance = MockMixingEngine.return_value
        me_instance.create_looped_background.return_value = mock_block_audio
        me_instance.overlay_voice_on_background.return_value = mock_block_audio
        
        # Run the function
        await tao_file_audiodrama(content_list, filename, story_id, db_manager)
        
        # Verify manifest
        manifest_file = f"{filename}.manifest.json"
        assert os.path.exists(manifest_file)
        
        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            alignments = data['word_alignments']
            
            # Trace:
            # Block 1:
            # current_block_start_ms = 0
            # segment_offset = 1000
            # word 1: 100 + 0 + 1000 = 1100
            # word 2: 300 + 0 + 1000 = 1300
            # segment_offset becomes 1000 + 2000 + 500 = 3500
            # block_duration (bg_duration) = 2000 + 2000 = 4000
            # current_block_start_ms becomes 0 + (4000 - 1000) = 3000
            
            # Block 2:
            # current_block_start_ms = 3000
            # segment_offset = 1000
            # word 1: 100 + 3000 + 1000 = 4100
            # word 2: 300 + 3000 + 1000 = 4300
            
            assert alignments[0]['start_time_ms'] == 1100
            assert alignments[1]['start_time_ms'] == 1300
            assert alignments[2]['start_time_ms'] == 4100
            assert alignments[3]['start_time_ms'] == 4300
            
        # Cleanup
        if os.path.exists(manifest_file):
            os.remove(manifest_file)
        if os.path.exists(f"{filename}.script.json"):
            os.remove(f"{filename}.script.json")
