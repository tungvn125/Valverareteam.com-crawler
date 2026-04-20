"""Tests for TTS provider implementations."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.tts.base import VoiceSpec, SynthesisResult


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
