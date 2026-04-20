"""Tests for TTS provider implementations."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.tts.base import SynthesisResult, VoiceSpec


class TestElevenLabsProvider:
    @pytest.mark.asyncio
    async def test_synthesize_with_timestamps(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        chunk1 = {
            "audio_base64": base64.b64encode(b"audio1").decode(),
            "alignment": {
                "characters": ["H", "e", "l", "l", "o", " "],
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            },
        }
        chunk2 = {
            "audio_base64": base64.b64encode(b"audio2").decode(),
            "alignment": {
                "characters": ["w", "o", "r", "l", "d"],
                "character_start_times_seconds": [0.6, 0.7, 0.8, 0.9, 1.0],
                "character_end_times_seconds": [0.7, 0.8, 0.9, 1.0, 1.1],
            },
        }

        class MockResponse:
            status_code = 200

            async def aiter_lines(self):
                for chunk in [chunk1, chunk2]:
                    yield json.dumps(chunk)

            async def aread(self):
                return b""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=MockResponse())
        mock_stream_ctx.__aexit__ = AsyncMock()

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            voice = VoiceSpec(voice_id="test_voice")
            result = await provider.synthesize("Hello world", voice)

            assert isinstance(result, SynthesisResult)
            assert result.audio_bytes == b"audio1audio2"
            assert result.word_alignments is not None
            assert len(result.word_alignments) == 2
            assert result.word_alignments[0].word == "Hello"
            assert result.word_alignments[0].start == 0
            assert result.word_alignments[0].end == 500
            assert result.word_alignments[1].word == "world"
            assert result.word_alignments[1].start == 600
            assert result.word_alignments[1].end == 1100

    @pytest.mark.asyncio
    async def test_discover_voices(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        mock_voice = MagicMock()
        mock_voice.voice_id = "abc123"
        mock_voice.name = "Rachel"
        mock_voice.labels = {"gender": "female"}

        mock_client = MagicMock()
        mock_client.voices.get_all.return_value.voices = [mock_voice]

        with patch("elevenlabs.client.ElevenLabs", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            voices = await provider.discover_voices()
            assert len(voices) == 1
            assert voices[0].voice_id == "abc123"
            assert voices[0].name == "Rachel"
            assert voices[0].gender == "female"

    @pytest.mark.asyncio
    async def test_preview_voice(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        mock_client = MagicMock()
        mock_client.generate.return_value = [b"audio_chunk"]

        with patch("elevenlabs.client.ElevenLabs", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            voice = VoiceSpec(voice_id="test_voice")
            audio = await provider.preview_voice(voice, "Test")
            assert audio == b"audio_chunk"

    @pytest.mark.asyncio
    async def test_close(self):
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

        mock_client = AsyncMock()
        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = ElevenLabsProvider(api_key="test_key")
            await provider.close()
            mock_client.aclose.assert_called_once()


class TestOpenAITTSProvider:
    @pytest.mark.asyncio
    async def test_synthesize(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_mp3_audio_bytes"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(side_effect=Exception("no /voices endpoint"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider(
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="tts-1",
                default_voice="alloy",
            )
            voice = VoiceSpec(voice_id="echo")
            result = await provider.synthesize("Hello world", voice)

            assert result.audio_bytes == b"fake_mp3_audio_bytes"
            assert result.word_alignments is None

            call_kwargs = mock_client.post.call_args[1]["json"]
            assert call_kwargs["voice"] == "echo"
            assert call_kwargs["model"] == "tts-1"

    @pytest.mark.asyncio
    async def test_synthesize_uses_default_voice_when_no_voice_id(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock(side_effect=Exception("no /voices"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider(default_voice="nova")
            voice = VoiceSpec()
            await provider.synthesize("Hello", voice)

            call_kwargs = mock_client.post.call_args[1]["json"]
            assert call_kwargs["voice"] == "nova"

    @pytest.mark.asyncio
    async def test_discover_voices_fallback(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("no endpoint"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider()
            voices = await provider.discover_voices()
            names = [v.voice_id for v in voices]
            assert "alloy" in names
            assert "echo" in names
            assert len(voices) == 6

    @pytest.mark.asyncio
    async def test_discover_voices_from_api(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"voices": [{"id": "custom1", "name": "Custom Voice 1"}]}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider()
            voices = await provider.discover_voices()
            assert len(voices) == 1
            assert voices[0].voice_id == "custom1"

    @pytest.mark.asyncio
    async def test_close(self):
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider

        mock_client = AsyncMock()
        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = OpenAITTSProvider()
            await provider.close()
            mock_client.aclose.assert_called_once()


class TestOmniVoiceProvider:
    @pytest.mark.asyncio
    async def test_synthesize_clone_mode(self):
        # Create mock numpy module
        mock_np = MagicMock()
        mock_np.zeros = MagicMock(return_value=[0.0] * 24000)
        mock_np.float32 = "float32"

        mock_model = MagicMock()
        mock_model.generate.return_value = [[0.0] * 24000]
        mock_model.sampling_rate = 24000

        mock_omnivoice = MagicMock()
        mock_omnivoice.from_pretrained.return_value = mock_model

        mock_modules = {
            "omnivoice": mock_omnivoice,
            "omnivoice.OmniVoice": mock_omnivoice,
            "numpy": mock_np,
            "soundfile": MagicMock(),
        }

        with patch.dict("sys.modules", mock_modules):
            with patch("soundfile.write", side_effect=lambda buf, data, sr, **kw: buf.write(b"WAV_DATA")):
                from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

                provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
                provider._model = mock_model
                provider._sampling_rate = 24000

                voice = VoiceSpec(ref_audio_path="voices/narrator/sample.wav", ref_text="Hello")
                result = await provider.synthesize("Hello world", voice)

                assert result.word_alignments is None
                assert result.sample_rate == 24000
                mock_model.generate.assert_called_once_with(
                    text="Hello world",
                    ref_audio="voices/narrator/sample.wav",
                    ref_text="Hello",
                )

    @pytest.mark.asyncio
    async def test_synthesize_design_mode(self):
        mock_model = MagicMock()
        mock_model.generate.return_value = [[0.0] * 12000]
        mock_model.sampling_rate = 24000

        mock_sf = MagicMock()
        mock_sf.write = MagicMock(side_effect=lambda buf, data, sr, **kw: buf.write(b"WAV_DATA"))

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

            provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
            provider._model = mock_model
            provider._sampling_rate = 24000

            voice = VoiceSpec(instruct="female, low pitch")
            result = await provider.synthesize("Hello", voice)

            mock_model.generate.assert_called_once_with(text="Hello", instruct="female, low pitch")
            assert result.duration_ms == 500

    @pytest.mark.asyncio
    async def test_synthesize_auto_mode(self):
        mock_model = MagicMock()
        mock_model.generate.return_value = [[0.0] * 12000]
        mock_model.sampling_rate = 24000

        mock_sf = MagicMock()
        mock_sf.write = MagicMock(side_effect=lambda buf, data, sr, **kw: buf.write(b"WAV_DATA"))

        with patch.dict("sys.modules", {"soundfile": mock_sf}):
            from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

            provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
            provider._model = mock_model
            provider._sampling_rate = 24000

            voice = VoiceSpec()
            await provider.synthesize("Hello", voice)

            mock_model.generate.assert_called_once_with(text="Hello")

    @pytest.mark.asyncio
    async def test_discover_voices_returns_empty(self):
        from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider

        provider = OmniVoiceProvider.__new__(OmniVoiceProvider)
        voices = await provider.discover_voices()
        assert voices == []
