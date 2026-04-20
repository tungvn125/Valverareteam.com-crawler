import os
from unittest.mock import patch

import pytest

from vvr_scraper.tts.base import VoiceSpec, WordAlignment, SynthesisResult, VoiceInfo, map_tags


class TestVoiceSpec:
    def test_mode_clone(self):
        spec = VoiceSpec(ref_audio_path="voices/narrator/sample.wav", ref_text="Hello")
        assert spec.mode == "clone"

    def test_mode_voice_id(self):
        spec = VoiceSpec(voice_id="ywBZEqUhld86Jeajq94o")
        assert spec.mode == "voice_id"

    def test_mode_design(self):
        spec = VoiceSpec(instruct="female, low pitch")
        assert spec.mode == "design"

    def test_mode_auto(self):
        spec = VoiceSpec()
        assert spec.mode == "auto"

    def test_clone_takes_priority_over_voice_id(self):
        spec = VoiceSpec(ref_audio_path="voices/narrator/sample.wav", voice_id="abc123")
        assert spec.mode == "clone"

    def test_voice_id_takes_priority_over_design(self):
        spec = VoiceSpec(voice_id="abc123", instruct="female, low pitch")
        assert spec.mode == "voice_id"


class TestSynthesisResult:
    def test_with_alignments(self):
        result = SynthesisResult(
            audio_bytes=b"fake", sample_rate=24000, duration_ms=1000,
            word_alignments=[WordAlignment(word="Hello", start=0, end=500)],
        )
        assert result.word_alignments is not None
        assert len(result.word_alignments) == 1

    def test_without_alignments(self):
        result = SynthesisResult(audio_bytes=b"fake", sample_rate=24000, duration_ms=1000)
        assert result.word_alignments is None


class TestMapTags:
    def test_elevenlabs_tags(self):
        text = "[laughter] That was [sigh] funny."
        result = map_tags(text, "elevenlabs")
        assert result == "[laughs] That was [sighs] funny."

    def test_omnivoice_tags(self):
        text = "[laughter] That was [sigh] funny."
        result = map_tags(text, "omnivoice")
        assert result == "[laughter] That was [sigh] funny."

    def test_openai_tts_strips_tags(self):
        text = "[laughter] That was [sigh] funny."
        result = map_tags(text, "openai_tts")
        assert result == " That was  funny."

    def test_unknown_provider_passes_through(self):
        text = "[laughter] Hello"
        result = map_tags(text, "unknown_provider")
        assert result == "[laughter] Hello"

    def test_pause_tag_all_providers(self):
        text = "Wait[pause]then go."
        assert map_tags(text, "elevenlabs") == "Wait...then go."
        assert map_tags(text, "omnivoice") == "Wait...then go."
        assert map_tags(text, "openai_tts") == "Wait...then go."


class TestRegistry:
    def test_register_and_get(self):
        from vvr_scraper.tts import register, get_provider

        class FakeProvider:
            def __init__(self, **kw): pass
            async def synthesize(self, text, voice): pass
            async def discover_voices(self): return []
            async def preview_voice(self, voice, text): return b""
            async def close(self): pass

        register("fake_test", FakeProvider)
        provider = get_provider("fake_test")
        assert isinstance(provider, FakeProvider)

    def test_get_unknown_raises(self):
        from vvr_scraper.tts import get_provider
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            get_provider("nonexistent_provider_xyz")

    def test_auto_detect_elevenlabs(self):
        from vvr_scraper.tts import auto_detect_provider
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}, clear=False):
            assert auto_detect_provider() == "elevenlabs"

    def test_auto_detect_openai_tts(self):
        from vvr_scraper.tts import auto_detect_provider
        env = {"OPENAI_TTS_API_KEY": "sk-test", "ELEVENLABS_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True):
            assert auto_detect_provider() == "openai_tts"

    def test_auto_detect_explicit_override(self):
        from vvr_scraper.tts import auto_detect_provider
        with patch.dict(os.environ, {"VVR_TTS_PROVIDER": "omnivoice"}, clear=True):
            assert auto_detect_provider() == "omnivoice"

    def test_auto_detect_none_raises(self):
        from vvr_scraper.tts import auto_detect_provider
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="No TTS provider configured"):
                auto_detect_provider()
