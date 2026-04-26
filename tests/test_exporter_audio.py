import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import CharacterProfile, ContentItem
from vvr_scraper.tts.base import SynthesisResult, VoiceInfo, VoiceSpec, WordAlignment


def test_elevenlabs_synthesis_concurrency_defaults_to_plan_limit(monkeypatch):
    """ElevenLabs synthesis should not exceed the common 3-request plan limit by default."""
    from vvr_scraper.exporter import _get_synthesis_concurrency

    monkeypatch.delenv("VVR_TTS_CONCURRENCY", raising=False)

    assert _get_synthesis_concurrency("elevenlabs") == 3


def test_synthesis_concurrency_can_be_lowered_by_env(monkeypatch):
    """Users should be able to lower synthesis concurrency to protect paid APIs."""
    from vvr_scraper.exporter import _get_synthesis_concurrency

    monkeypatch.setenv("VVR_TTS_CONCURRENCY", "1")

    assert _get_synthesis_concurrency("elevenlabs") == 1


@pytest.mark.asyncio
async def test_tao_file_audiodrama_serializes_same_voice_synthesis(tmp_path, monkeypatch):
    """ElevenLabs can reject parallel requests for the same voice; same voice must be serialized."""
    from vvr_scraper.audio_drama import ScriptResult

    filename = str(tmp_path / "same_voice.mp3")
    story_id = "same_voice_story"
    content_list = [ContentItem(type="text", data="Line one. Line two.")]

    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    mock_db.get_character_profiles = AsyncMock(return_value=[])

    active_voice_ids: set[str] = set()

    class ConflictIfSameVoiceConcurrentProvider:
        async def discover_voices(self):
            return []

        async def synthesize(self, text, voice):
            voice_id = voice.voice_id or "auto"
            if voice_id in active_voice_ids:
                raise Exception("same voice synthesized concurrently")
            active_voice_ids.add(voice_id)
            try:
                await asyncio.sleep(0.01)
                return SynthesisResult(audio_bytes=b"audio", sample_rate=44100, duration_ms=500)
            finally:
                active_voice_ids.remove(voice_id)

        async def preview_voice(self, voice, text):
            return b"audio"

        async def close(self):
            pass

    mock_script = ScriptResult([
        {"type": "segment", "role": "narrator", "text": "Line one."},
        {"type": "segment", "role": "narrator", "text": "Line two."},
    ])

    monkeypatch.setenv("VVR_TTS_CONCURRENCY", "3")

    with (
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.tts.get_provider", return_value=ConflictIfSameVoiceConcurrentProvider()),
        patch("pydub.AudioSegment.from_file", return_value=MockAudio(1000)),
        patch("pydub.AudioSegment.silent", side_effect=lambda duration: MockAudio(duration)),
        patch("vvr_scraper.exporter.BGMManager") as MockBGM,
        patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
        patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
        patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator,
    ):
        MockParser.return_value.parse_chapter = AsyncMock(return_value=mock_script)
        MockBGM.return_value.get_random_track.return_value = None
        MockFreesound.return_value.search_bgm = AsyncMock(return_value=[])
        MockImageGenerator.return_value.generate = AsyncMock(return_value="fake_bg.webp")
        MockMixing.return_value.create_looped_background.return_value = MockAudio(1000)
        MockMixing.return_value.overlay_voice_on_background.return_value = MockAudio(1000)

        await tao_file_audiodrama(content_list, filename, story_id, mock_db, tts_provider_name="elevenlabs")


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
            vm_instance.get_voice = AsyncMock(return_value=VoiceSpec(voice_id="fake_voice_id"))
            vm_instance.synthesize = AsyncMock(
                return_value=SynthesisResult(
                    audio_bytes=b"fake_audio",
                    sample_rate=44100,
                    duration_ms=500,
                    word_alignments=[WordAlignment(word="Hello", start=0, end=500)],
                )
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
            vm_instance.get_voice = AsyncMock(return_value=VoiceSpec(voice_id="fake_voice_id"))
            vm_instance.synthesize = AsyncMock(
                return_value=SynthesisResult(
                    audio_bytes=b"audio",
                    sample_rate=44100,
                    duration_ms=500,
                    word_alignments=[WordAlignment(word="Action", start=0, end=500)],
                )
            )
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
async def test_tao_file_audiodrama_accepts_freesound_dict_results(tmp_path):
    """Freesound search results may be dicts; exporter should still download by id."""
    from vvr_scraper.audio_drama import ScriptResult

    filename = str(tmp_path / "dict_freesound.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="Some text")]

    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})

    mock_script = ScriptResult([
        {"type": "mood_shift", "mood": "mysterious", "tags": ["mysterious"], "visual_prompt": None},
        {"type": "segment", "role": "narrator", "text": "Hello."},
    ])

    with (
        patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager,
        patch("pydub.AudioSegment.from_file", return_value=MockAudio(1000)),
        patch("pydub.AudioSegment.silent", side_effect=lambda duration: MockAudio(duration)),
        patch("vvr_scraper.exporter.BGMManager") as MockBGM,
        patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
        patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
        patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator,
    ):
        MockParser.return_value.parse_chapter = AsyncMock(return_value=mock_script)
        MockBGM.return_value.get_random_track.return_value = None
        MockImageGenerator.return_value.generate = AsyncMock(return_value="fake_bg.webp")
        MockMixing.return_value.create_looped_background.return_value = MockAudio(1000)
        MockMixing.return_value.overlay_voice_on_background.return_value = MockAudio(1000)

        vm_instance = MockVoiceManager.return_value
        vm_instance.get_known_characters = AsyncMock(return_value=[])
        vm_instance.resolve_aliases = MagicMock(side_effect=lambda x: x)
        vm_instance.get_voice = AsyncMock(return_value=VoiceSpec(voice_id="fake_voice_id"))
        vm_instance.synthesize = AsyncMock(
            return_value=SynthesisResult(audio_bytes=b"audio", sample_rate=44100, duration_ms=500)
        )
        vm_instance.close = AsyncMock()

        fs_instance = MockFreesound.return_value
        fs_instance.search_bgm = AsyncMock(return_value=[{"id": 123, "name": "bgm.wav"}])
        fs_instance.download_and_convert = AsyncMock(return_value="fake_bgm.wav")

        await tao_file_audiodrama(content_list, filename, story_id, mock_db)

        fs_instance.download_and_convert.assert_awaited_once()
        assert fs_instance.download_and_convert.await_args.args[0] == 123


@pytest.mark.asyncio
async def test_tao_file_mp3_flow(tmp_path):
    """Tests the audiobook generation flow with TTS provider."""
    from vvr_scraper.exporter import tao_file_mp3

    filename = str(tmp_path / "test_audiobook.mp3")
    content_list = [ContentItem(type="text", data="Chapter text here.")]

    with (
        patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
        patch("vvr_scraper.tts.get_provider") as MockGetProvider,
        patch("pydub.AudioSegment.from_file") as MockFromFile,
    ):
        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(
            return_value=SynthesisResult(audio_bytes=b"fake_audio", sample_rate=44100, duration_ms=1000)
        )
        MockGetProvider.return_value = mock_provider

        MockFromFile.return_value = MockAudio(1000)

        await tao_file_mp3(content_list, filename, "Test Title")

        # Should be called for title and text
        assert mock_provider.synthesize.call_count == 2


@pytest.mark.asyncio
async def test_tao_file_audiodrama_fallback(tmp_path):
    """TTS synthesis failure should stop immediately instead of emitting paid silence."""
    filename = str(tmp_path / "fallback.mp3")
    story_id = "test_story"
    content_list = [ContentItem(type="text", data="text")]

    mock_db = MagicMock()
    mock_db.get_all_story_voices = AsyncMock(return_value={})
    mock_db.get_character_profiles = AsyncMock(return_value=[])
    mock_db.save_character_profile = AsyncMock()

    # Mock provider to fail during synthesis
    with (
        patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}),
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.tts.get_provider") as MockGetProvider,
        patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager,
        patch("pydub.AudioSegment.silent") as MockSilent,
    ):
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(
            return_value=[{"type": "segment", "role": "narrator", "text": "text"}]
        )

        # Provider works but VoiceManager.synthesize fails
        mock_provider = MagicMock()
        MockGetProvider.return_value = mock_provider

        vm_instance = MockVoiceManager.return_value
        vm_instance.get_known_characters = AsyncMock(return_value=[])
        vm_instance.resolve_aliases = MagicMock(side_effect=lambda x: x)
        vm_instance.get_voice = AsyncMock(return_value=VoiceSpec(voice_id="fake_voice_id"))
        # Simulate synthesis failure - returns silent audio
        vm_instance.synthesize = AsyncMock(side_effect=Exception("Synthesis failed"))
        vm_instance.close = AsyncMock()

        MockSilent.return_value = MockAudio(500)

        with pytest.raises(Exception, match="Synthesis failed"):
            await tao_file_audiodrama(content_list, filename, story_id, mock_db)

        MockSilent.assert_not_called()


@pytest.mark.asyncio
async def test_tao_file_audiodrama_uses_voice_saved_by_selection_callback(tmp_path):
    """Voice selections saved after parsing must affect the same synthesis run."""
    from vvr_scraper.audio_drama import ScriptResult

    filename = str(tmp_path / "selected_voice.mp3")
    story_id = "story_with_callback"
    content_list = [ContentItem(type="text", data="Alice speaks.")]
    profiles: dict[str, CharacterProfile] = {}

    class FakeDB:
        async def get_all_story_voices(self, story_id):
            return {}

        async def get_character_profiles(self, story_id):
            return list(profiles.values())

        async def save_character_profile(self, profile):
            profiles[profile.name.lower()] = profile

    class RecordingProvider:
        def __init__(self):
            self.synthesized: list[tuple[str, VoiceSpec]] = []

        async def discover_voices(self):
            return []

        async def synthesize(self, text, voice):
            self.synthesized.append((text, voice))
            return SynthesisResult(audio_bytes=b"audio", sample_rate=44100, duration_ms=500, format="mp3")

        async def preview_voice(self, voice, text):
            return b"audio"

        async def close(self):
            pass

    provider = RecordingProvider()

    async def select_voices_callback(characters, callback_story_id):
        assert callback_story_id == story_id
        assert characters == [{"name": "Alice", "gender": "female"}]
        profiles["alice"] = CharacterProfile(name="Alice", story_id=story_id, gender="female", voice_id="alice-voice")

    mock_script = ScriptResult([{"type": "segment", "role": "Alice", "gender": "female", "text": "Hello."}])

    with (
        patch("vvr_scraper.exporter.OpenAIParser") as MockParser,
        patch("vvr_scraper.tts.get_provider", return_value=provider),
        patch("pydub.AudioSegment.from_file", return_value=MockAudio(1000)),
        patch("pydub.AudioSegment.silent", side_effect=lambda duration: MockAudio(duration)),
        patch("vvr_scraper.exporter.BGMManager") as MockBGM,
        patch("vvr_scraper.exporter.MixingEngine") as MockMixing,
        patch("vvr_scraper.exporter.FreesoundManager") as MockFreesound,
        patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator,
    ):
        MockParser.return_value.parse_chapter = AsyncMock(return_value=mock_script)
        MockBGM.return_value.get_random_track.return_value = None
        MockFreesound.return_value.search_bgm = AsyncMock(return_value=[])
        MockImageGenerator.return_value.generate = AsyncMock(return_value="fake_bg.webp")
        MockMixing.return_value.create_looped_background.return_value = MockAudio(1000)
        MockMixing.return_value.overlay_voice_on_background.return_value = MockAudio(1000)

        await tao_file_audiodrama(
            content_list,
            filename,
            story_id,
            FakeDB(),
            tts_provider_name="elevenlabs",
            select_voices_callback=select_voices_callback,
        )

    assert provider.synthesized
    assert provider.synthesized[0][1].voice_id == "alice-voice"


@pytest.mark.asyncio
async def test_cli_elevenlabs_voice_selection_saves_voice_id(monkeypatch):
    """ElevenLabs CLI selection should persist voice_id, not ref-audio fields."""
    from vvr_scraper.cli import ValvrareScraperCLI

    saved_profiles = []
    cli = ValvrareScraperCLI.__new__(ValvrareScraperCLI)
    cli.db_manager = MagicMock()
    cli.db_manager.save_character_profile = AsyncMock(side_effect=lambda profile: saved_profiles.append(profile))

    class FakeProvider:
        async def discover_voices(self):
            return [VoiceInfo(voice_id="voice-1", name="Rachel", gender="female", labels={"gender": "female"})]

        async def close(self):
            pass

    with (
        patch("vvr_scraper.cli.InteractiveUI.show_menu", side_effect=[0, 0]),
        patch("vvr_scraper.tts.get_provider", return_value=FakeProvider()),
    ):
        await cli._select_voices_interactive(
            [{"name": "Alice", "gender": "female"}],
            "story-elevenlabs",
            provider_name="elevenlabs",
        )

    assert len(saved_profiles) == 1
    saved = saved_profiles[0]
    assert saved.name == "Alice"
    assert saved.story_id == "story-elevenlabs"
    assert saved.gender == "female"
    assert saved.voice_id == "voice-1"
    assert saved.ref_audio_path is None
    assert saved.ref_text is None


@pytest.mark.asyncio
async def test_cli_elevenlabs_voice_selection_accepts_custom_voice_id():
    """ElevenLabs CLI selection should allow manually entering a custom voice ID."""
    from vvr_scraper.cli import ValvrareScraperCLI

    saved_profiles = []
    cli = ValvrareScraperCLI.__new__(ValvrareScraperCLI)
    cli.db_manager = MagicMock()
    cli.db_manager.save_character_profile = AsyncMock(side_effect=lambda profile: saved_profiles.append(profile))

    fake_session = MagicMock()
    fake_session.prompt_async = AsyncMock(return_value=" custom-voice-123 ")

    with (
        patch("vvr_scraper.cli.InteractiveUI.show_menu", return_value=1),
        patch("vvr_scraper.cli.PromptSession", return_value=fake_session),
    ):
        await cli._select_voices_interactive(
            [{"name": "Alice", "gender": "female"}],
            "story-elevenlabs",
            provider_name="elevenlabs",
        )

    assert len(saved_profiles) == 1
    saved = saved_profiles[0]
    assert saved.name == "Alice"
    assert saved.story_id == "story-elevenlabs"
    assert saved.gender == "female"
    assert saved.voice_id == "custom-voice-123"
    assert saved.ref_audio_path is None
    assert saved.ref_text is None


@pytest.mark.asyncio
async def test_cli_elevenlabs_per_character_menu_accepts_custom_voice_id():
    """Per-character ElevenLabs voice list should also offer custom voice ID input."""
    from vvr_scraper.cli import ValvrareScraperCLI

    saved_profiles = []
    cli = ValvrareScraperCLI.__new__(ValvrareScraperCLI)
    cli.db_manager = MagicMock()
    cli.db_manager.save_character_profile = AsyncMock(side_effect=lambda profile: saved_profiles.append(profile))

    class FakeProvider:
        async def discover_voices(self):
            return [VoiceInfo(voice_id="listed-voice-1", name="Rachel", gender="female", labels={})]

        async def close(self):
            pass

    fake_session = MagicMock()
    fake_session.prompt_async = AsyncMock(return_value=" custom-per-character-voice ")

    with (
        patch("vvr_scraper.cli.InteractiveUI.show_menu", side_effect=[0, 1]),
        patch("vvr_scraper.tts.get_provider", return_value=FakeProvider()),
        patch("vvr_scraper.cli.PromptSession", return_value=fake_session),
    ):
        await cli._select_voices_interactive(
            [{"name": "Alice", "gender": "female"}],
            "story-elevenlabs",
            provider_name="elevenlabs",
        )

    assert len(saved_profiles) == 1
    saved = saved_profiles[0]
    assert saved.name == "Alice"
    assert saved.voice_id == "custom-per-character-voice"
    assert saved.ref_audio_path is None
    assert saved.ref_text is None


@pytest.mark.asyncio
async def test_cli_write_to_formats_passes_voice_selector_for_explicit_elevenlabs(tmp_path):
    """--select-voices must work when the user explicitly chooses ElevenLabs."""
    import argparse

    from vvr_scraper.cli import ValvrareScraperCLI
    from vvr_scraper.models import StoryInfo

    cli = ValvrareScraperCLI.__new__(ValvrareScraperCLI)
    cli.args = argparse.Namespace(select_voices=True, tts_provider="elevenlabs")
    cli.db_manager = MagicMock()
    cli._select_voices_interactive = AsyncMock()

    with patch("vvr_scraper.cli.tao_file_audiodrama", new_callable=AsyncMock) as mock_audio_drama:
        await cli._write_to_formats(
            str(tmp_path),
            "Chapter 1",
            [ContentItem(type="text", data="Hello")],
            StoryInfo(title="Story", author="Author", description="", slug="story"),
            {"formats": ["AD-MP3"]},
            [],
        )

    callback = mock_audio_drama.call_args.kwargs.get("select_voices_callback")
    assert callback is not None
