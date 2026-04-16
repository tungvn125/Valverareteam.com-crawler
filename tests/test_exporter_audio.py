import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    def __mul__(self, multiplier):
        return MockAudio(self.length * multiplier)

    def fade_out(self, duration):
        return self

    def fade_in(self, duration):
        return self

    def export(self, *args, **kwargs):
        pass

    def apply_gain(self, gain):
        return self

    def overlay(self, other, position=0):
        return self

    def append(self, other, crossfade=0):
        return MockAudio(self.length + len(other))


@pytest.mark.asyncio
async def test_tao_file_audiodrama_flow(tmp_path):
    """Tests the full orchestration flow of tao_file_audiodrama with ElevenLabs mocks."""
    from vvr_scraper.audio_drama import ScriptResult

    filename = str(tmp_path / "test_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Narrator text. Character: Hello!")]

    # Mock DB manager
    mock_db = MagicMock()
    mock_db.save_character_voice = AsyncMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})

    mock_script = ScriptResult(
        [
            {"type": "segment", "role": "narrator", "text": "Narrator text."},
            {"type": "segment", "role": "Character", "text": "Hello!"},
        ]
    )

    # Mock OpenAIParser
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)

        # Mock VoiceManager, pydub
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
            patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager,
            patch("pydub.AudioSegment.from_file") as MockFromFile,
            patch("pydub.AudioSegment.silent") as MockSilent,
            patch("vvr_scraper.exporter.BGMManager"),
            patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
            patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
            patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator,
        ):
            vm_instance = MockVoiceManager.return_value
            vm_instance.get_known_characters = AsyncMock(return_value=[])
            vm_instance.resolve_aliases = MagicMock(side_effect=lambda x: x)
            vm_instance.get_voice = AsyncMock(return_value="fake_voice_id")
            vm_instance.synthesize = AsyncMock(
                return_value=(b"fake_audio", [{"word": "Hello", "start": 0, "end": 500}])
            )
            vm_instance.close = AsyncMock()

            fs_instance = MockFreesound.return_value
            fs_instance.search_bgm = AsyncMock(return_value=[])
            fs_instance.download_and_convert = AsyncMock(return_value="fake_bgm.wav")

            MockImageGenerator.return_value.generate = AsyncMock(return_value="fake_bg.webp")

            MockSilent.side_effect = lambda duration: MockAudio(duration)
            MockFromFile.return_value = MockAudio(1000)

            mixing_instance = MockMixing.return_value
            mixing_instance.create_looped_background.return_value = MockAudio(1000)
            mixing_instance.overlay_voice_on_background.return_value = MockAudio(1000)

            await tao_file_audiodrama(content_list, filename, story_id, mock_db)

            # Verify OpenAI was called
            parser_instance.parse_chapter.assert_called_once()

            # Verify VoiceManager.synthesize was called for each segment (2 segments)
            assert vm_instance.synthesize.call_count == 2


@pytest.mark.asyncio
async def test_tao_file_audiodrama_v2_with_moods(tmp_path):
    """Tests Audio Drama v2 with mood shifts and ElevenLabs."""
    from vvr_scraper.audio_drama import ScriptResult

    filename = str(tmp_path / "v2_drama.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]

    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})

    mock_script = ScriptResult(
        [
            {
                "type": "mood_shift",
                "mood": "action",
                "tags": ["action"],
                "visual_prompt": "action",
                "vfx": [],
                "transition": "fade",
                "duration": 1000,
            },
            {"type": "segment", "role": "narrator", "text": "Action starts!"},
        ]
    )

    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)

        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
            patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager,
            patch("pydub.AudioSegment.from_file") as MockFromFile,
            patch("pydub.AudioSegment.silent") as MockSilent,
            patch("vvr_scraper.exporter.BGMManager") as MockBGM,
            patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
            patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
            patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator,
        ):
            vm_instance = MockVoiceManager.return_value
            vm_instance.get_known_characters = AsyncMock(return_value=[])
            vm_instance.resolve_aliases = MagicMock(side_effect=lambda x: x)
            vm_instance.get_voice = AsyncMock(return_value="fake_voice_id")
            vm_instance.synthesize = AsyncMock(return_value=(b"audio", [{"word": "Action", "start": 0, "end": 500}]))
            vm_instance.close = AsyncMock()

            fs_instance = MockFreesound.return_value
            fs_instance.search_bgm = AsyncMock(return_value=[])
            fs_instance.download_and_convert = AsyncMock(return_value="fake_bgm.wav")

            MockImageGenerator.return_value.generate = AsyncMock(return_value="fake_bg.webp")

            bgm_instance = MockBGM.return_value
            bgm_instance.get_random_track.return_value = "fake_bgm.mp3"

            MockSilent.side_effect = lambda duration: MockAudio(duration)
            MockFromFile.return_value = MockAudio(1000)

            mixing_instance = MockMixing.return_value
            mixing_instance.create_looped_background.return_value = MockAudio(1000)
            mixing_instance.overlay_voice_on_background.return_value = MockAudio(1000)

            await tao_file_audiodrama(content_list, filename, story_id, mock_db)

            assert bgm_instance.get_random_track.called
            assert vm_instance.synthesize.call_count == 1


@pytest.mark.asyncio
async def test_tao_file_mp3_flow(tmp_path):
    """Tests the audiobook generation flow with ElevenLabs."""
    from vvr_scraper.exporter import tao_file_mp3

    filename = str(tmp_path / "test_audiobook.mp3")
    content_list = [ContentItem(type="text", data="Chapter text here.")]

    with (
        patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
        patch("elevenlabs.client.ElevenLabs") as MockElevenLabs,
        patch("pydub.AudioSegment.from_file") as MockFromFile,
    ):
        client_instance = MockElevenLabs.return_value
        client_instance.text_to_speech.convert.return_value = [b"chunk1"]

        MockFromFile.return_value = MockAudio(1000)

        await tao_file_mp3(content_list, filename, "Test Title")

        # Should be called for title and text
        assert client_instance.text_to_speech.convert.call_count == 2


@pytest.mark.asyncio
async def test_tao_file_audiodrama_fallback(tmp_path):
    """Tests fallback behavior (should fail gracefully if API key missing)."""
    filename = str(tmp_path / "fallback.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="text")]

    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    mock_db.get_character_profiles = AsyncMock(return_value=[])
    mock_db.save_character_profile = AsyncMock()

    # Don't use clear=True to preserve PATH for pydub
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}):
        with patch("vvr_scraper.exporter.OpenAIParser") as MockParser:
            parser_instance = MockParser.return_value
            parser_instance.parse_chapter = AsyncMock(
                return_value=[{"type": "segment", "role": "narrator", "text": "text"}]
            )

            # Should log error and return
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)
            assert not os.path.exists(filename)
