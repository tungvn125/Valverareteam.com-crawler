from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Default ElevenLabs voice ID (Bella - professional female voice)
DEFAULT_ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"


@dataclass
class VoiceSpec:
    """Provider-agnostic voice descriptor.

    Modes (checked in priority order):
    1. clone: ref_audio_path + ref_text (OmniVoice voice cloning)
    2. voice_id: voice_id string (ElevenLabs cloud voice)
    3. design: instruct string (OmniVoice voice design fallback)
    4. auto: no preference
    """

    ref_audio_path: str | None = None
    ref_text: str | None = None
    voice_id: str | None = None
    instruct: str | None = None
    settings: dict = field(default_factory=dict)

    @property
    def mode(self) -> str:
        if self.ref_audio_path:
            return "clone"
        if self.voice_id:
            return "voice_id"
        if self.instruct:
            return "design"
        return "auto"


@dataclass
class WordAlignment:
    word: str
    start: int  # milliseconds
    end: int  # milliseconds


@dataclass
class SynthesisResult:
    audio_bytes: bytes
    sample_rate: int
    duration_ms: int
    word_alignments: list[WordAlignment] | None = None


@dataclass
class VoiceInfo:
    voice_id: str | None = None
    name: str = ""
    gender: str = "unknown"
    ref_audio_path: str | None = None
    labels: dict = field(default_factory=dict)


ELEVENLABS_TAG_MAP: dict[str, str] = {
    "[laughter]": "[laughs]",
    "[sigh]": "[sighs]",
    "[surprise]": "[gasps]",
    "[whisper]": "[whispers]",
    "[pause]": "...",
}

OMNIVOICE_TAG_MAP: dict[str, str] = {
    "[laughter]": "[laughter]",
    "[sigh]": "[sigh]",
    "[surprise]": "[surprise-ah]",
    "[whisper]": "[whisper]",
    "[pause]": "...",
}

OPENAI_TTS_TAG_MAP: dict[str, str] = {
    "[laughter]": "",
    "[sigh]": "",
    "[surprise]": "",
    "[whisper]": "",
    "[pause]": "...",
}


def map_tags(text: str, provider_name: str) -> str:
    tag_map = {
        "elevenlabs": ELEVENLABS_TAG_MAP,
        "omnivoice": OMNIVOICE_TAG_MAP,
        "openai_tts": OPENAI_TTS_TAG_MAP,
    }.get(provider_name, {})
    for generic, specific in tag_map.items():
        text = text.replace(generic, specific)
    return text


@runtime_checkable
class TTSProvider(Protocol):
    async def synthesize(self, text: str, voice: VoiceSpec) -> SynthesisResult: ...
    async def discover_voices(self) -> list[VoiceInfo]: ...
    async def preview_voice(self, voice: VoiceSpec, text: str) -> bytes: ...
    async def close(self) -> None: ...
