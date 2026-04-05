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
                {"word": "Hắn", "start": 100, "end": 200},
                {"word": "bước", "start": 300, "end": 400}
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
        manifest_file = "test_audio_drama.manifest.json"
        assert os.path.exists(manifest_file)
        
        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            events = data['events']
            
            dialogue_events = [e for e in events if e['type'] == 'dialogue']
            # Trace:
            # Block 1:
            # current_block_start_ms = 0
            # segment_offset = 1000 (VOICE_OVERLAY_OFFSET_MS)
            # word 1: 100 + 0 + 1000 = 1100, role = narrator
            # word 2: 300 + 0 + 1000 = 1300, role = narrator
            # segment_offset becomes 1000 + 2000 (len) + 500 (GAP) = 3500
            # block_duration (bg_duration) = 2000 (combined_voice) + 2000 (padding) = 4000
            # current_block_start_ms becomes 0 + (4000 - 1000) = 3000 (CROSSFADE_MS = 1000)
            
            # Block 2:
            # current_block_start_ms = 3000
            # segment_offset = 1000
            # word 1: 100 + 3000 + 1000 = 4100, role = narrator
            # word 2: 300 + 3000 + 1000 = 4300, role = narrator
            
            assert dialogue_events[0]['time_ms'] == 1000
            assert dialogue_events[1]['time_ms'] == 4000 # 3000 + 1000
            
            alignments_0 = dialogue_events[0]['alignment']
            assert alignments_0[0]['start'] == 1100
            assert dialogue_events[0]['role'] == 'narrator'
            assert alignments_0[1]['start'] == 1300

            alignments_1 = dialogue_events[1]['alignment']
            assert alignments_1[0]['start'] == 4100
            assert dialogue_events[1]['role'] == 'narrator'
            assert alignments_1[1]['start'] == 4300
            
        # Cleanup
        if os.path.exists(manifest_file):
            os.remove(manifest_file)
        if os.path.exists(f"{filename}.script.json"):
            os.remove(f"{filename}.script.json")
