"""TTS Provider registry and factory."""

import os
from typing import Any

from .base import TTSProvider

_registry: dict[str, type[TTSProvider]] = {}


def register(name: str, provider_cls: type) -> None:
    """Register a TTS provider class under the given name."""
    _registry[name] = provider_cls


def get_provider(name: str, **kwargs: Any) -> TTSProvider:
    """Instantiate a registered provider by name."""
    if name not in _registry:
        raise ValueError(
            f"Unknown TTS provider '{name}'. "
            f"Available: {list(_registry.keys())}. "
            f"Set --tts-provider or VVR_TTS_PROVIDER env var."
        )
    return _registry[name](**kwargs)


def auto_detect_provider() -> str:
    """Determine provider from env vars."""
    explicit = os.getenv("VVR_TTS_PROVIDER")
    if explicit:
        return explicit

    if os.getenv("ELEVENLABS_API_KEY"):
        return "elevenlabs"

    if os.getenv("OPENAI_TTS_API_KEY") or os.getenv("OPENAI_TTS_BASE_URL"):
        return "openai_tts"

    raise ValueError(
        "No TTS provider configured. "
        "Set ELEVENLABS_API_KEY for ElevenLabs, "
        "OPENAI_TTS_API_KEY for OpenAI-compatible TTS, "
        "or set VVR_TTS_PROVIDER=omnivoice for OmniVoice local model."
    )


def _register_builtins() -> None:
    """Auto-register built-in providers (lazy — only if deps available)."""
    try:
        from vvr_scraper.tts.elevenlabs_provider import ElevenLabsProvider
        register("elevenlabs", ElevenLabsProvider)
    except ImportError:
        pass

    try:
        from vvr_scraper.tts.omnivoice_provider import OmniVoiceProvider
        register("omnivoice", OmniVoiceProvider)
    except ImportError:
        pass

    try:
        from vvr_scraper.tts.openai_tts_provider import OpenAITTSProvider
        register("openai_tts", OpenAITTSProvider)
    except ImportError:
        pass


_register_builtins()
