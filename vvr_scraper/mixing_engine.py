import math
from dataclasses import dataclass, field
from typing import Optional

from pydub import AudioSegment

from loguru import logger


@dataclass
class TimelineConfig:
    crossfade_battle_ms: int = 500
    crossfade_default_ms: int = 2000
    crossfade_voice_ms: int = 1000
    bgm_volume_db: float = -20.0
    voice_overlay_offset_ms: int = 1000
    gap_between_segments_ms: int = 500
    voice_fade_in_ms: int = 500
    voice_fade_out_ms: int = 500
    chunk_size_ms: int = 300000

    @classmethod
    def from_dict(cls, d: dict) -> "TimelineConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Track:
    audio: AudioSegment
    segment_type: str
    mood: str
    start_ms: int = 0


@dataclass
class BackgroundTrack:
    bgm_path: str
    mood: str
    volume_db: float = -20.0
    start_ms: int = 0
    duration_ms: int = 0


@dataclass
class Crossfade:
    at_ms: int
    from_mood: str
    to_mood: str
    duration_ms: int = 0


FAST_TRANSITIONS = {
    ("peaceful", "battle"),
    ("romance", "battle"),
    ("peaceful", "tension"),
    ("battle", "peaceful"),
}


class AudioTimeline:
    def __init__(self, config: TimelineConfig | None = None):
        self.config = config or TimelineConfig()
        self.tracks: list[Track] = []
        self.backgrounds: list[BackgroundTrack] = []
        self.crossfades: list[Crossfade] = []
        self._block_index: list[dict] = []

    def add_segment(self, audio: AudioSegment, segment_type: str, mood: str, start_ms: int | None = None):
        pos = start_ms if start_ms is not None else self._next_position()
        self.tracks.append(Track(audio=audio, segment_type=segment_type, mood=mood, start_ms=pos))

    def add_background(
        self, bgm_path: str, mood: str, volume_db: float | None = None, start_ms: int = 0, duration_ms: int = 0
    ):
        self.backgrounds.append(
            BackgroundTrack(
                bgm_path=bgm_path,
                mood=mood,
                volume_db=volume_db if volume_db is not None else self.config.bgm_volume_db,
                start_ms=start_ms,
                duration_ms=duration_ms,
            )
        )

    def add_crossfade(self, at_ms: int, from_mood: str, to_mood: str, duration_ms: int | None = None):
        if duration_ms is None:
            duration_ms = self._get_crossfade_duration(from_mood, to_mood)
        self.crossfades.append(Crossfade(at_ms=at_ms, from_mood=from_mood, to_mood=to_mood, duration_ms=duration_ms))

    def add_block(
        self,
        block_index: int,
        voice: AudioSegment,
        mood: str,
        bgm_path: str | None,
        manifest_events: list[dict] | None = None,
    ):
        self._block_index.append(
            {
                "block_index": block_index,
                "mood": mood,
                "bgm_path": bgm_path,
                "voice_duration_ms": len(voice),
                "crossfade_with_previous": block_index > 0,
            }
        )
        self.add_segment(voice, "voice_block", mood)
        if bgm_path:
            self.add_background(bgm_path, mood, duration_ms=len(voice) + self.config.voice_overlay_offset_ms * 2)

    def _next_position(self) -> int:
        if not self.tracks:
            return 0
        return max(t.start_ms + len(t.audio) for t in self.tracks)

    def _get_crossfade_duration(self, from_mood: str, to_mood: str) -> int:
        if (from_mood, to_mood) in FAST_TRANSITIONS:
            return self.config.crossfade_battle_ms
        return self.config.crossfade_default_ms

    def render(self, output_path: str, mixing_engine: "MixingEngine") -> AudioSegment:
        cfg = self.config
        blocks = self._block_index
        if not blocks:
            logger.warning("AudioTimeline: no blocks to render")
            return AudioSegment.silent(duration=0)

        final_audio: AudioSegment | None = None
        prev_mood: str | None = None

        for i, block_info in enumerate(blocks):
            voice_segments = [t for t in self.tracks if t.segment_type == "voice_block"]
            if i >= len(voice_segments):
                break
            voice = voice_segments[i]
            mood = block_info["mood"]
            bgm_path = block_info.get("bgm_path")

            combined_voice = voice.audio
            combined_voice = combined_voice.fade_in(cfg.voice_fade_in_ms).fade_out(cfg.voice_fade_out_ms)

            bg_duration = len(combined_voice) + cfg.voice_overlay_offset_ms * 2
            bgm_audio = self._load_bgm(bgm_path, mood, mixing_engine)
            background = mixing_engine.create_looped_background(bgm_audio, bg_duration, gain_db=cfg.bgm_volume_db)

            block_audio = mixing_engine.overlay_voice_on_background(
                background, combined_voice, position=cfg.voice_overlay_offset_ms
            )

            if final_audio is None:
                final_audio = block_audio
            else:
                if prev_mood is not None and prev_mood != mood:
                    for cf in self.crossfades:
                        if cf.from_mood == prev_mood and cf.to_mood == mood:
                            bgm_out = block_audio[: cf.duration_ms].fade_in(cf.duration_ms)
                            tail_keep = len(block_audio) - cf.duration_ms
                            if tail_keep > 0:
                                block_audio = bgm_out + block_audio[cf.duration_ms :]
                            break

                final_audio = final_audio.append(block_audio, crossfade=cfg.crossfade_voice_ms)

            prev_mood = mood

        return final_audio

    def _load_bgm(self, bgm_path: str | None, mood: str, mixing_engine: "MixingEngine") -> AudioSegment:
        import os

        if bgm_path and os.path.exists(bgm_path):
            try:
                return AudioSegment.from_file(bgm_path)
            except Exception as e:
                logger.warning(f"Failed to load BGM {bgm_path}: {e}")

        return AudioSegment.silent(duration=10000)


class MixingEngine:
    """
    Core audio logic for mixing background music (BGM) with voice segments.
    """

    def create_looped_background(
        self, bgm_segment: AudioSegment, duration_ms: int, gain_db: float = -18.0
    ) -> AudioSegment:
        """
        Creates a looped background track from a BGM segment to match the target duration.

        Args:
            bgm_segment: The BGM audio segment to loop.
            duration_ms: Target duration in milliseconds.
            gain_db: Fixed gain in dB to apply to the background.

        Returns:
            The looped and truncated AudioSegment with gain applied.
        """
        if len(bgm_segment) == 0:
            return AudioSegment.silent(duration=duration_ms, frame_rate=bgm_segment.frame_rate)

        loops_needed = math.ceil(duration_ms / len(bgm_segment))
        looped = bgm_segment * loops_needed
        truncated = looped[:duration_ms]
        return truncated.apply_gain(gain_db)

    def overlay_voice_on_background(
        self, background: AudioSegment, voice_track: AudioSegment, position: int = 1000
    ) -> AudioSegment:
        """
        Overlays a voice track onto a background track.

        Args:
            background: The background audio segment.
            voice_track: The voice audio segment to overlay.
            position: Offset in milliseconds for the voice track.

        Returns:
            The mixed AudioSegment.
        """
        return background.overlay(voice_track, position=position)
