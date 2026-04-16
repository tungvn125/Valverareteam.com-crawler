from pydub import AudioSegment

from vvr_scraper.mixing_engine import (
    AudioTimeline,
    MixingEngine,
    TimelineConfig,
)

# ─── MixingEngine (original) ────────────────────────────────


def test_create_looped_background():
    engine = MixingEngine()
    bgm = AudioSegment.silent(duration=100, frame_rate=44100)
    result = engine.create_looped_background(bgm, 250, -10.0)
    assert len(result) == 250
    assert len(result) > len(bgm)


def test_create_looped_background_empty():
    engine = MixingEngine()
    bgm = AudioSegment.silent(duration=0, frame_rate=44100)
    result = engine.create_looped_background(bgm, 500)
    assert len(result) == 500


def test_create_looped_background_no_loop_needed():
    engine = MixingEngine()
    bgm = AudioSegment.silent(duration=1000, frame_rate=44100)
    result = engine.create_looped_background(bgm, 500)
    assert len(result) == 500


def test_overlay_voice_on_background():
    engine = MixingEngine()
    background = AudioSegment.silent(duration=500, frame_rate=44100)
    voice = AudioSegment.silent(duration=200, frame_rate=44100)
    result = engine.overlay_voice_on_background(background, voice)
    assert len(result) == len(background)


def test_overlay_voice_longer_than_background():
    engine = MixingEngine()
    background = AudioSegment.silent(duration=200, frame_rate=44100)
    voice = AudioSegment.silent(duration=500, frame_rate=44100)
    result = engine.overlay_voice_on_background(background, voice)
    assert len(result) == 200


# ─── TimelineConfig ──────────────────────────────────────────


class TestTimelineConfig:
    def test_defaults(self):
        cfg = TimelineConfig()
        assert cfg.crossfade_battle_ms == 500
        assert cfg.crossfade_default_ms == 2000
        assert cfg.crossfade_voice_ms == 1000
        assert cfg.bgm_volume_db == -20.0
        assert cfg.voice_overlay_offset_ms == 1000
        assert cfg.gap_between_segments_ms == 500
        assert cfg.voice_fade_in_ms == 500
        assert cfg.voice_fade_out_ms == 500
        assert cfg.chunk_size_ms == 300000

    def test_custom_values(self):
        cfg = TimelineConfig(
            crossfade_battle_ms=300,
            crossfade_default_ms=1500,
            bgm_volume_db=-18.0,
            voice_overlay_offset_ms=500,
        )
        assert cfg.crossfade_battle_ms == 300
        assert cfg.crossfade_default_ms == 1500
        assert cfg.bgm_volume_db == -18.0
        assert cfg.voice_overlay_offset_ms == 500

    def test_from_dict(self):
        d = {"crossfade_default_ms": 3000, "bgm_volume_db": -15.0, "gap_between_segments_ms": 400}
        cfg = TimelineConfig.from_dict(d)
        assert cfg.crossfade_default_ms == 3000
        assert cfg.bgm_volume_db == -15.0
        assert cfg.gap_between_segments_ms == 400
        assert cfg.crossfade_battle_ms == 500
        assert cfg.voice_overlay_offset_ms == 1000

    def test_from_dict_ignores_unknown_keys(self):
        d = {"crossfade_default_ms": 3000, "unknown_key": 42}
        cfg = TimelineConfig.from_dict(d)
        assert cfg.crossfade_default_ms == 3000
        assert not hasattr(cfg, "unknown_key")


# ─── AudioTimeline ────────────────────────────────────────────


class TestAudioTimeline:
    def test_add_segment(self):
        timeline = AudioTimeline()
        segment = AudioSegment.silent(duration=1000)
        timeline.add_segment(segment, "voice", "peaceful")
        assert len(timeline.tracks) == 1
        assert timeline.tracks[0].segment_type == "voice"
        assert timeline.tracks[0].mood == "peaceful"

    def test_add_segment_auto_position(self):
        timeline = AudioTimeline()
        s1 = AudioSegment.silent(duration=1000)
        s2 = AudioSegment.silent(duration=2000)
        timeline.add_segment(s1, "voice", "peaceful", start_ms=0)
        timeline.add_segment(s2, "voice", "peaceful")
        assert timeline.tracks[0].start_ms == 0
        assert timeline.tracks[1].start_ms > 0

    def test_add_background(self):
        timeline = AudioTimeline()
        timeline.add_background("/path/to/bgm.mp3", "battle", volume_db=-15.0, duration_ms=5000)
        assert len(timeline.backgrounds) == 1
        assert timeline.backgrounds[0].mood == "battle"
        assert timeline.backgrounds[0].volume_db == -15.0

    def test_add_background_default_volume(self):
        cfg = TimelineConfig(bgm_volume_db=-18.0)
        timeline = AudioTimeline(cfg)
        timeline.add_background("/path/to/bgm.mp3", "peaceful")
        assert timeline.backgrounds[0].volume_db == -18.0

    def test_add_crossfade(self):
        timeline = AudioTimeline()
        timeline.add_crossfade(at_ms=5000, from_mood="peaceful", to_mood="battle")
        assert len(timeline.crossfades) == 1
        assert timeline.crossfades[0].duration_ms == 500  # battle = fast

    def test_add_crossfade_custom_duration(self):
        timeline = AudioTimeline()
        timeline.add_crossfade(at_ms=5000, from_mood="peaceful", to_mood="romance", duration_ms=3000)
        assert timeline.crossfades[0].duration_ms == 3000

    def test_add_crossfade_default_duration(self):
        timeline = AudioTimeline()
        timeline.add_crossfade(at_ms=5000, from_mood="peaceful", to_mood="romance")
        assert timeline.crossfades[0].duration_ms == 2000  # default


# ─── Crossfade Duration Logic ────────────────────────────────


class TestCrossfadeDuration:
    def test_battle_transitions(self):
        timeline = AudioTimeline()
        assert timeline._get_crossfade_duration("peaceful", "battle") == 500
        assert timeline._get_crossfade_duration("romance", "battle") == 500
        assert timeline._get_crossfade_duration("peaceful", "tension") == 500
        assert timeline._get_crossfade_duration("battle", "peaceful") == 500

    def test_default_transitions(self):
        timeline = AudioTimeline()
        assert timeline._get_crossfade_duration("peaceful", "romance") == 2000
        assert timeline._get_crossfade_duration("tension", "peaceful") == 2000
        assert timeline._get_crossfade_duration("battle", "tension") == 2000

    def test_custom_ms(self):
        cfg = TimelineConfig(crossfade_battle_ms=250, crossfade_default_ms=1000)
        timeline = AudioTimeline(cfg)
        assert timeline._get_crossfade_duration("peaceful", "battle") == 250
        assert timeline._get_crossfade_duration("peaceful", "romance") == 1000
