import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import VoiceManager
from vvr_scraper.tts.base import VoiceSpec


@pytest.mark.asyncio
async def test_voice_manager_synthesize_timestamps():
    db = MagicMock()
    vm = VoiceManager(db, "test_story")

    voice_spec = VoiceSpec(voice_id="test_voice")
    text = "Hello world"

    # Mock data from ElevenLabs stream-with-timestamps
    # Each line is a JSON object
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
        def __init__(self, chunks):
            self.chunks = chunks
            self.status_code = 200

        async def aiter_lines(self):
            for chunk in self.chunks:
                yield chunk

        async def aread(self):
            return b""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_response = MockResponse([json.dumps(chunk1), json.dumps(chunk2)])

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    # Mocking the async context manager for httpx.AsyncClient().stream(...)
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock()
    mock_client.stream.return_value = mock_stream_ctx

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test_key"}):
            from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider

            provider = ElevenLabsProvider(api_key="test_key")
            vm = VoiceManager(db, "test_story", provider=provider)
            result = await vm.synthesize(voice=voice_spec, text=text)

            # Verify the API call
            mock_client.stream.assert_called_once()
            method, url = mock_client.stream.call_args[0]
            assert method == "POST"
            assert f"/{voice_spec.voice_id}/stream-with-timestamps" in url

            # Verify payload
            payload = mock_client.stream.call_args[1]["json"]
            assert payload["text"] == text
            assert payload["model_id"] == "eleven_v3"

            # Verify audio concatenation
            assert result.audio_bytes == b"audio1audio2"

            # Verify word-level processing
            # Chunk 1 ends with space, so it should finish "Hello"
            # Chunk 2 has "world" without space, but it's the last word
            assert len(result.word_alignments) == 2

            assert result.word_alignments[0].word == "Hello"
            assert result.word_alignments[0].start == 0
            assert result.word_alignments[0].end == 500  # end of 'o' (character_end_times_seconds[4])

            assert result.word_alignments[1].word == "world"
            assert result.word_alignments[1].start == 600
            assert result.word_alignments[1].end == 1100
