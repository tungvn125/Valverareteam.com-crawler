"""OmniVoice TTS provider — local model with voice cloning and design."""

import io
import os

from loguru import logger

from .base import VoiceInfo, VoiceSpec, SynthesisResult


class OmniVoiceProvider:
    """TTSProvider for OmniVoice local model.

    Supports voice cloning (ref_audio), voice design (instruct), and auto.
    Requires GPU with PyTorch + OmniVoice installed.
    """

    def __init__(self, model_name: str = "k2-fsa/OmniVoice", device: str | None = None):
        try:
            from omnivoice import OmniVoice
        except ImportError as e:
            raise ImportError(
                "OmniVoice is required for OmniVoiceProvider. "
                "Install with: pip install omnivoice"
            ) from e

        device = device or os.getenv("VVR_OMNIVOICE_DEVICE", "cuda:0")
        self._model = OmniVoice.from_pretrained(model_name, device_map=device, dtype="float16")
        self._model.load_asr_model()
        self._sampling_rate = self._model.sampling_rate

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize using OmniVoice local model."""
        if voice.ref_audio_path:
            audio_np = self._model.generate(
                text=text,
                ref_audio=voice.ref_audio_path,
                ref_text=voice.ref_text,
            )
        elif voice.instruct:
            audio_np = self._model.generate(text=text, instruct=voice.instruct)
        else:
            audio_np = self._model.generate(text=text)

        import soundfile as sf

        buf = io.BytesIO()
        sf.write(buf, audio_np[0], self._sampling_rate, format="WAV")
        audio_bytes = buf.getvalue()
        duration_ms = int(len(audio_np[0]) / self._sampling_rate * 1000)

        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate=self._sampling_rate,
            duration_ms=duration_ms,
            word_alignments=None,
        )

    async def discover_voices(self) -> list[VoiceInfo]:
        """Stub — story-specific voice samples require story context."""
        return []

    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes:
        result = await self.synthesize(text, voice)
        return result.audio_bytes

    async def close(self) -> None:
        try:
            import torch
            del self._model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
