import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from vvr_scraper.bgm_manager import BGMManager

@pytest.fixture
def mock_bgm_dir(tmp_path):
    """Creates a mock BGM directory structure."""
    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    
    # Happy mood
    happy_dir = bgm_dir / "happy"
    happy_dir.mkdir()
    (happy_dir / "track1.mp3").touch()
    (happy_dir / "track2.wav").touch()
    
    # Sad mood
    sad_dir = bgm_dir / "sad"
    sad_dir.mkdir()
    (sad_dir / "sad_theme.mp3").touch()
    
    # Empty mood
    empty_dir = bgm_dir / "empty"
    empty_dir.mkdir()
    
    return bgm_dir

def test_bgm_manager_initialization(mock_bgm_dir):
    """Test that BGMManager scans the directory correctly."""
    manager = BGMManager(mock_bgm_dir)
    assert "happy" in manager.available_moods
    assert "sad" in manager.available_moods
    assert "empty" not in manager.available_moods # Should only include moods with tracks

def test_get_random_track_success(mock_bgm_dir):
    """Test retrieving a random track for a valid mood."""
    manager = BGMManager(mock_bgm_dir)
    track = manager.get_random_track("happy")
    assert track is not None
    assert track.suffix in [".mp3", ".wav"]
    assert "happy" in str(track)

def test_get_random_track_invalid_mood_fallback(mock_bgm_dir):
    """Test that an invalid mood returns None."""
    manager = BGMManager(mock_bgm_dir)
    track = manager.get_random_track("nonexistent")
    assert track is None

def test_get_random_track_empty_library(tmp_path):
    """Test behavior when the library is empty."""
    empty_dir = tmp_path / "empty_library"
    empty_dir.mkdir()
    manager = BGMManager(empty_dir)
    assert manager.get_random_track("any") is None
