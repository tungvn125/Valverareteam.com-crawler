import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock pydub before importing MixingEngine
mock_pydub = MagicMock()
mock_audio_segment = MagicMock()
mock_pydub.AudioSegment = mock_audio_segment
sys.modules['pydub'] = mock_pydub

from vvr_scraper.mixing_engine import MixingEngine

def test_mixing_engine_ducking():
    # Setup mocks
    bgm = MagicMock()
    bgm.__len__.return_value = 10000  # 10 seconds
    
    voice = MagicMock()
    voice.__len__.return_value = 2000   # 2 seconds
    
    # Mock slicing
    during_segment = MagicMock()
    # Mock bgm[1000:3000]
    bgm.__getitem__.side_effect = lambda s: during_segment if s == slice(1000, 3000) else MagicMock()
    
    # Mock AudioSegment.silent
    mock_audio_segment.silent.return_value = MagicMock()
    
    # Mock methods used in implementation
    during_segment.apply_gain.return_value = during_segment
    during_segment.overlay.return_value = during_segment
    
    engine = MixingEngine()
    start_ms = 1000
    
    # Test with default duck_db (-15.0)
    result = engine.mix_with_ducking(bgm, voice, start_ms)
    
    # Verification
    # Implementation should split BGM: 0-1000, 1000-3000, 3000-end
    assert bgm.__getitem__.called
    
    # It should apply gain to the "during" part with default -15.0
    during_segment.apply_gain.assert_called_once_with(-15.0)
    
    # And then overlay voice on it
    during_segment.overlay.assert_called_once_with(voice)
    
    assert result is not None

def test_mixing_engine_padding():
    # Setup mocks
    bgm = MagicMock()
    bgm.__len__.return_value = 1000  # 1 second
    bgm.frame_rate = 44100
    
    voice = MagicMock()
    voice.__len__.return_value = 2000   # 2 seconds
    
    # Mock AudioSegment.silent
    silent_segment = MagicMock()
    mock_audio_segment.silent.return_value = silent_segment
    
    # Mock slicing
    bgm.__getitem__.side_effect = lambda s: MagicMock()
    
    # Mock methods used in implementation
    bgm.apply_gain.return_value = bgm
    bgm.overlay.return_value = bgm
    bgm.__add__.return_value = bgm
    
    engine = MixingEngine()
    start_ms = 2000  # Voice starts after BGM ends
    
    result = engine.mix_with_ducking(bgm, voice, start_ms)
    
    # Verification
    # Should pad with silence
    # padding = end_ms (4000) - len(bgm) (1000) = 3000ms
    mock_audio_segment.silent.assert_called_with(duration=3000, frame_rate=44100)
    assert bgm.__add__.called
    assert result is not None
