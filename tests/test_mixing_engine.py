import pytest
from pydub import AudioSegment
from vvr_scraper.mixing_engine import MixingEngine

def test_create_looped_background():
    engine = MixingEngine()
    # Create a short BGM segment (100ms)
    # Using silent(duration=100) creates a 100ms segment. 
    # But for testing looping logic, it's better if it's not silent 
    # so we can potentially see the structure, but silent is fine for duration.
    bgm = AudioSegment.silent(duration=100, frame_rate=44100)
    
    # Target duration: 250ms
    duration_ms = 250
    gain_db = -10.0
    
    result = engine.create_looped_background(bgm, duration_ms, gain_db)
    
    # Check duration
    assert len(result) == duration_ms
    
    # Check that it's actually longer than the original
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
    # 500ms background
    background = AudioSegment.silent(duration=500, frame_rate=44100)
    # 200ms voice
    voice = AudioSegment.silent(duration=200, frame_rate=44100)
    
    result = engine.overlay_voice_on_background(background, voice)
    
    # Result should have same length as background (pydub's overlay behavior)
    assert len(result) == len(background)

def test_overlay_voice_longer_than_background():
    engine = MixingEngine()
    background = AudioSegment.silent(duration=200, frame_rate=44100)
    voice = AudioSegment.silent(duration=500, frame_rate=44100)
    
    result = engine.overlay_voice_on_background(background, voice)
    
    # pydub.overlay: "The resulting AudioSegment will be the same length as the 
    # AudioSegment it was called on (the background)."
    # Wait, actually pydub's overlay can extend the length if specified, 
    # but by default it doesn't? No, actually it does NOT extend by default.
    assert len(result) == 200
