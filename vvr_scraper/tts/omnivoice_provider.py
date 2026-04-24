"""OmniVoice TTS provider — local model with voice cloning and design."""

import asyncio
import io
import os

from loguru import logger

from .base import SynthesisResult, VoiceInfo, VoiceSpec


class OmniVoiceProvider:
    """OmniVoice local TTS provider with voice cloning and design support."""

    def __init__(self, model_name: str = "k2-fsa/OmniVoice", device: str | None = None):
        try:
            import omnivoice  # noqa: F401 — validate install early
        except ImportError as e:
            raise ImportError("OmniVoice is required for OmniVoiceProvider. Install with: pip install omnivoice") from e

        self._model_name = model_name
        self._device = device or os.getenv("VVR_OMNIVOICE_DEVICE", "cuda:0")
        self._model = None  # lazy-loaded on first synthesize
        self._sampling_rate = None
        self._load_lock = asyncio.Lock()

    async def _ensure_model(self) -> None:
        """Load model on first use (thread-safe lazy init)."""
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            logger.info(f"Loading OmniVoice model '{self._model_name}' on {self._device}...")

            def _load():
                from omnivoice import OmniVoice
                m = OmniVoice.from_pretrained(self._model_name, device_map=self._device, dtype="float16")
                m.load_asr_model()
                return m

            self._model = await asyncio.to_thread(_load)
            self._sampling_rate = self._model.sampling_rate
            logger.info("OmniVoice model loaded.")

    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult:
        """Synthesize using OmniVoice local model."""
        import functools

        await self._ensure_model()

        if voice.ref_audio_path:
            gen_fn = functools.partial(
                self._model.generate,
                text=text,
                ref_audio=voice.ref_audio_path,
                ref_text=voice.ref_text,
            )
        elif voice.instruct:
            gen_fn = functools.partial(self._model.generate, text=text, instruct=voice.instruct)
        else:
            gen_fn = functools.partial(self._model.generate, text=text)

        audio_np = await asyncio.to_thread(gen_fn)

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
            format="wav",
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

            if hasattr(self, "_model"):
                del self._model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as e:
            logger.warning(f"Failed to close OmniVoice model: {e}")
