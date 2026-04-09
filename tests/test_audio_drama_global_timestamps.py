import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import ScriptResult
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem


@pytest.mark.asyncio
async def test_global_timestamp_calculation(tmp_path):
    # Mock data
    content_list = [ContentItem(type="text", data="Hắn bước vào. Gió thổi mạnh.")]
    filename = str(tmp_path / "test_audio_drama.mp3")
    story_id = "test_story"
    db_manager = MagicMock()

    # Use real ScriptResult populated with mock segments
    mock_script = ScriptResult(
        [
            {
                "type": "mood_shift",
                "tags": ["mysterious"],
                "mood": "mysterious",
                "visual_prompt": "mysterious",
                "vfx": [],
                "transition": "fade",
                "duration": 1000,
            },
            {"type": "segment", "role": "narrator", "text": "Hắn bước vào.", "voice": "voice1"},
            {
                "type": "mood_shift",
                "tags": ["action"],
                "mood": "action",
                "visual_prompt": "action",
                "vfx": [],
                "transition": "fade",
                "duration": 1000,
            },
            {"type": "segment", "role": "narrator", "text": "Gió thổi mạnh.", "voice": "voice1"},
        ]
    )

    with (
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager,
        patch("vvr_scraper.exporter.BGMManager") as MockBGMManager,
        patch("vvr_scraper.exporter.FreesoundManager") as MockFreesoundManager,
        patch("vvr_scraper.exporter.MixingEngine") as MockMixingEngine,
        patch("pydub.AudioSegment.from_file") as MockAudioFromFile,
        patch("pydub.AudioSegment.silent") as MockSilent,
        patch("os.getenv", return_value="fake_key"),
    ):
        # Mock Parser
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)

        # Mock VoiceManager
        vm_instance = MockVoiceManager.return_value
        vm_instance.get_voice = AsyncMock(return_value="voice1")
        vm_instance.close = AsyncMock()

        # Mock FreesoundManager
        fs_instance = MockFreesoundManager.return_value
        fs_instance.search_bgm = AsyncMock(return_value=[])
        fs_instance.download_and_convert = AsyncMock(return_value="fake_bgm.wav")

        # Mock ImageGenerator
        with patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator:
            image_gen_instance = MockImageGenerator.return_value
            image_gen_instance.generate = AsyncMock(return_value="backgrounds/fake.webp")

            # Mock synthesis to return 2s audio and some alignments
            mock_audio_bytes = b"fake audio"

            async def get_mock_alignments(*args, **kwargs):
                return mock_audio_bytes, [
                    {"word": "Hắn", "start": 100, "end": 200},
                    {"word": "bước", "start": 300, "end": 400},
                ]

            vm_instance.synthesize.side_effect = get_mock_alignments

            # Mock AudioSegment
            mock_voice_segment = MagicMock()
            mock_voice_segment.__len__.return_value = 2000  # 2 seconds
            mock_voice_segment.fade_in.return_value = mock_voice_segment
            mock_voice_segment.fade_out.return_value = mock_voice_segment

            mock_block_audio = MagicMock()
            mock_block_audio.__len__.return_value = 4000  # 4 seconds (bg_duration)
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
        manifest_file = os.path.join(os.path.dirname(filename), "manifest.json")
        assert os.path.exists(manifest_file)

        with open(manifest_file, encoding="utf-8") as f:
            data = json.load(f)
            events = data["events"]

            dialogue_events = [e for e in events if e["type"] == "dialogue"]

            # Verify events (implementation uses 'start' and 'character')
            assert dialogue_events[0]["start"] == 1000
            assert dialogue_events[1]["start"] == 4000

            alignments_0 = dialogue_events[0]["alignment"]
            assert alignments_0[0]["start"] == 1100
            assert dialogue_events[0]["character"] == "narrator"
            assert alignments_0[1]["start"] == 1300

            alignments_1 = dialogue_events[1]["alignment"]
            assert alignments_1[0]["start"] == 4100
            assert dialogue_events[1]["character"] == "narrator"
            assert alignments_1[1]["start"] == 4300
