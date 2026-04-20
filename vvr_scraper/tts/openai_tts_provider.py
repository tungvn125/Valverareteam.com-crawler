"""OpenAI-compatible HTTP TTS provider — works with any /v1/audio/speech server."""

import io
import os

import httpx
from loguru import logger

from .base import SynthesisResult, VoiceInfo, VoiceSpec


class OpenAITTSProvider:
    """OpenAI-compatible HTTP TTS provider for /v1/audio/speech endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        default_voice: str | None = None,
    ):
        self._base_url = (base_url or os.getenv("OPENAI_TTS_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._api_key = api_key or os.getenv("OPENAI_TTS_API_KEY")
        self._model = model or os.getenv("OPENAI_TTS_MODEL", "tts-1")
        self._default_voice = default_voice or os.getenv("OPENAI_TTS_DEFAULT_VOICE", "alloy")

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=60.0,
        )

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize via POST /v1/audio/speech."""
        voice_name = voice.voice_id or self._default_voice

        response = await self._client.post(
            "/audio/speech",
            json={
                "model": self._model,
                "input": text,
                "voice": voice_name,
                "response_format": "mp3",
            },
        )
        response.raise_for_status()
        audio_bytes = response.content

        duration_ms = _estimate_duration_ms(audio_bytes)

        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=44100,
            duration_ms=duration_ms,
            word_alignments=None,
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        """Try GET /v1/voices, fall back to hardcoded OpenAI voice list."""
        try:
            response = await self._client.get("/voices")
            if response.status_code == 200:
                data = response.json()
                voice_list = data.get("voices", data if isinstance(data, list) else [])
                return [
                    VoiceInfo(voice_id=v.get("id", v.get("voice_id", "")), name=v.get("name", v.get("id", "")))
                    for v in voice_list
                ]
        except Exception as e:
            logger.warning(f"Failed to discover voices from API: {e}")

        return [
            VoiceInfo(voice_id=name, name=name.title())
            for name in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        ]

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        result = await self.synthesize(text, voice)
        return result.audio_bytes

    async def close(self) -> None:
        await self._client.aclose()


def _estimate_duration_ms(audio_bytes: bytes) -> int:
    """Estimate audio duration from MP3 bytes using pydub."""
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        return len(seg)
    except Exception as e:
        logger.warning(f"Failed to estimate audio duration: {e}")
        return int(len(audio_bytes) * 8 / 128)
