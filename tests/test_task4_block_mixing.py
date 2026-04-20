import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import ScriptResult
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem
from vvr_scraper.tts.base import SynthesisResult, VoiceSpec, WordAlignment


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
    mock_script = ScriptResult(
        [
            {
                "type": "mood_shift",
                "tags": ["peaceful"],
                "mood": "peaceful",
                "visual_prompt": "peaceful",
                "vfx": [],
                "transition": "fade",
                "duration": 1000,
            },
            {"type": "segment", "role": "narrator", "text": "Start of story."},
            {
                "type": "mood_shift",
                "tags": ["action"],
                "mood": "action",
                "visual_prompt": "action",
                "vfx": [],
                "transition": "fade",
                "duration": 1000,
            },
            {"type": "segment", "role": "Hero", "text": "Attack!"},
        ]
    )

    with (
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager,
        patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator,
    ):
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)

        voice_manager_instance = MockVoiceManager.return_value
        voice_manager_instance.get_voice = AsyncMock(
            side_effect=lambda role, gender: VoiceSpec(voice_id=f"voice_{role}")
        )
        # Ensure synthesize returns SynthesisResult in the correct format
        voice_manager_instance.synthesize = AsyncMock(
            return_value=SynthesisResult(
                audio_bytes=b"fake_audio",
                sample_rate=44100,
                duration_ms=1000,
                word_alignments=[WordAlignment(word="test", start=0, end=100)]
            )
        )
        voice_manager_instance.close = AsyncMock()

        # Mock ImageGenerator
        ig_instance = MockImageGenerator.return_value
        ig_instance.generate = AsyncMock(return_value=str(tmp_path / "backgrounds" / "fake.webp"))

        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
            patch("pydub.AudioSegment.from_file") as MockFromFile,
            patch("pydub.AudioSegment.silent") as MockSilent,
            patch("vvr_scraper.exporter.BGMManager") as MockBGM,
            patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
            patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
            patch("os.path.exists") as MockExists,
        ):
            # Make os.path.exists return True for our mocked files
            MockExists.return_value = True

            bgm_instance = MockBGM.return_value

            # Block 1: finds peaceful locally
            # Block 2: does NOT find action locally
            def side_effect_bgm(mood):
                if mood == "peaceful":
                    return "local_peaceful.mp3"
                return None

            bgm_instance.get_random_track.side_effect = side_effect_bgm

            freesound_instance = MockFreesound.return_value
            freesound_instance.search_bgm = AsyncMock(return_value=[MagicMock(id=123)])
            freesound_instance.download_and_convert = AsyncMock(return_value="downloaded_action.wav")

            MockSilent.side_effect = lambda duration, **kwargs: MockAudio(duration)
            MockFromFile.side_effect = lambda *args, **kwargs: MockAudio(2000)

            mixing_instance = MockMixing.return_value
            mixing_instance.create_looped_background.return_value = MockAudio(5000)
            mixing_instance.overlay_voice_on_background.return_value = MockAudio(5000)

            await tao_file_audiodrama(content_list, filename, story_id, mock_db)

            # 1. Parallel Synthesis: 2 segments
            assert voice_manager_instance.synthesize.call_count == 2

            # 2. Block 1 (implicit peaceful) -> local BGM check
            bgm_instance.get_random_track.assert_any_call("peaceful")

            # 3. Block 2 (action) -> local check fails -> Freesound check
            freesound_instance.search_bgm.assert_called_with(["action"], limit=5)
            freesound_instance.download_and_convert.assert_called()

            # 4. MixingEngine calls
            assert mixing_instance.create_looped_background.call_count >= 2
            assert mixing_instance.overlay_voice_on_background.call_count >= 2

            # 5. Verify manifest
            manifest_path = os.path.join(os.path.dirname(filename), "manifest.json")
            assert os.path.exists(manifest_path)
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            dialogue_events = [e for e in manifest["events"] if e["type"] == "dialogue"]
            assert len(dialogue_events) >= 2
            # Actual implementation uses 'character' not 'role'
            assert dialogue_events[0]["character"] == "narrator"
            assert "alignment" in dialogue_events[0]
            assert dialogue_events[0]["alignment"][0]["word"] == "test"

            # 6. Ensure VoiceManager.close was awaited
            voice_manager_instance.close.assert_awaited()
