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
    # Test with explicit path
    manager = BGMManager(base_dir=str(mock_bgm_dir))
    assert "happy" in manager.available_moods
    assert "sad" in manager.available_moods
    assert "empty" not in manager.available_moods # Should only include moods with tracks

def test_bgm_manager_default_init():
    """Test that BGMManager can be initialized with default 'bgm' dir."""
    with patch("vvr_scraper.bgm_manager.Path.exists") as mock_exists:
        mock_exists.return_value = False
        manager = BGMManager()
        assert manager.library_path == Path("bgm")

def test_get_random_track_success(mock_bgm_dir):
    """Test retrieving a random track for a valid mood."""
    manager = BGMManager(mock_bgm_dir)
    track = manager.get_random_track("Happy") # Test case-insensitivity
    assert track is not None
    assert isinstance(track, str)
    assert track.endswith((".mp3", ".wav", ".ogg"))
    assert "happy" in track.lower()

def test_get_random_track_ogg_support(mock_bgm_dir):
    """Test that .ogg files are supported."""
    ogg_dir = mock_bgm_dir / "mysterious"
    ogg_dir.mkdir()
    (ogg_dir / "track.ogg").touch()
    
    manager = BGMManager(mock_bgm_dir)
    assert "mysterious" in manager.available_moods
    track = manager.get_random_track("mysterious")
    assert track.endswith(".ogg")

def test_get_random_track_additional_formats(mock_bgm_dir):
    """Test that .flac and .m4a files are supported."""
    new_formats_dir = mock_bgm_dir / "high_quality"
    new_formats_dir.mkdir()
    (new_formats_dir / "track.flac").touch()
    (new_formats_dir / "track.m4a").touch()
    
    manager = BGMManager(mock_bgm_dir)
    assert "high_quality" in manager.available_moods
    track = manager.get_random_track("high_quality")
    assert track.endswith((".flac", ".m4a"))

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
