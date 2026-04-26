"""ElevenLabs TTS provider — cloud API with word-level timestamps."""

import asyncio
import base64
import io
import json
import os

import httpx
from loguru import logger

from .base import DEFAULT_ELEVENLABS_VOICE_ID, SynthesisResult, VoiceInfo, VoiceSpec, WordAlignment


class ElevenLabsProvider:
    """ElevenLabs cloud TTS provider with stream-with-timestamps support."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=300.0)
        self._sync_client = None  # Lazy init

    def _get_sync_client(self):
        if self._sync_client is None:
            from elevenlabs.client import ElevenLabs

            self._sync_client = ElevenLabs(api_key=self._api_key)
        return self._sync_client

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize using ElevenLabs stream-with-timestamps endpoint."""
        voice_id = voice.voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID)
        stability = voice.settings.get("stability", 0.35)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream/with-timestamps"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        data = {
            "text": text,
            "model_id": "eleven_v3",
            "output_format": "mp3_44100_128",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        audio_buffer = io.BytesIO()
        all_alignments = []

        async with self._client.stream("POST", url, headers=headers, json=data) as response:
            if response.status_code != 200:
                error_msg = await response.aread()
                raise Exception(f"ElevenLabs API error ({response.status_code}): {error_msg}")

            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if "audio_base64" in chunk:
                        audio_buffer.write(base64.b64decode(chunk["audio_base64"]))
                    alignment = chunk.get("alignment")
                    if isinstance(alignment, dict):
                        all_alignments.append(alignment)
                except Exception as e:
                    logger.warning(f"Error parsing alignment chunk: {e}")

        full_audio = audio_buffer.getvalue()
        audio_buffer.close()

        word_alignments = _parse_word_alignments(all_alignments)
        duration_ms = _estimate_duration_ms(full_audio)

        return SynthesisResult(
            audio_bytes=full_audio,
            sample_rate=44100,
            duration_ms=duration_ms,
            word_alignments=word_alignments,
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        """List available voices from ElevenLabs cloud API."""
        client = self._get_sync_client()

        def fetch():
            return client.voices.get_all().voices

        voices = await asyncio.to_thread(fetch)
        return [
            VoiceInfo(
                voice_id=v.voice_id,
                name=v.name,
                gender=v.labels.get("gender", "unknown").lower() if v.labels else "unknown",
                labels=v.labels or {},
            )
            for v in voices
        ]

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        """Generate a short audio preview via ElevenLabs."""
        client = self._get_sync_client()
        voice_id = voice.voice_id or DEFAULT_ELEVENLABS_VOICE_ID

        def generate():
            return client.generate(text=text, voice=voice_id, model="eleven_v3")

        audio_chunks = await asyncio.to_thread(generate)
        return b"".join(list(audio_chunks))

    async def close(self) -> None:
        await self._client.aclose()


def _parse_word_alignments(all_alignments: list[dict]) -> list[WordAlignment]:
    """Parse ElevenLabs character-level alignments into word-level alignments."""
    word_alignments = []
    current_word_chars = []
    current_word_start = None
    last_end = 0.0

    for alignment in all_alignments:
        if not isinstance(alignment, dict):
            continue
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])

        for char, start, end in zip(chars, starts, ends, strict=False):
            if char.isspace():
                if current_word_chars:
                    word_text = "".join(current_word_chars)
                    word_alignments.append(
                        WordAlignment(
                            word=word_text,
                            start=int(current_word_start * 1000),
                            end=int(last_end * 1000),
                        )
                    )
                    current_word_chars = []
                    current_word_start = None
                continue

            if not current_word_chars:
                current_word_start = start
            current_word_chars.append(char)
            last_end = end

    if current_word_chars:
        word_text = "".join(current_word_chars)
        word_alignments.append(
            WordAlignment(
                word=word_text,
                start=int(current_word_start * 1000),
                end=int(last_end * 1000),
            )
        )

    return word_alignments


def _estimate_duration_ms(audio_bytes: bytes) -> int:
    """Estimate audio duration from MP3 bytes using pydub."""
    from .base import estimate_duration_ms

    return estimate_duration_ms(audio_bytes)
