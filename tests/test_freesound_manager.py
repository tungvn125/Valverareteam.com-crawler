import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from vvr_scraper.freesound_manager import FreesoundManager

@pytest.fixture
def mock_freesound_client():
    with patch('freesound.FreesoundClient') as mock:
        yield mock

@pytest.fixture
def temp_auth_file(tmp_path):
    return tmp_path / ".vvr_freesound_auth.json"

def test_freesound_manager_init(mock_freesound_client):
    manager = FreesoundManager(client_id="test_id", client_secret="test_secret")
    assert manager.client_id == "test_id"
    assert manager.client_secret == "test_secret"
    mock_freesound_client.assert_called_once()

def test_freesound_manager_load_token(mock_freesound_client, temp_auth_file):
    token_data = {"access_token": "fake_token", "refresh_token": "fake_refresh"}
    temp_auth_file.write_text(json.dumps(token_data))
    
    manager = FreesoundManager(
        client_id="id", 
        client_secret="secret", 
        auth_file=str(temp_auth_file)
    )
    
    assert manager.token == token_data
    manager.client.set_token.assert_called_with("fake_token", "oauth")

def test_freesound_manager_save_token(mock_freesound_client, temp_auth_file):
    manager = FreesoundManager(
        client_id="id", 
        client_secret="secret", 
        auth_file=str(temp_auth_file)
    )
    
    new_token = {"access_token": "new_token", "refresh_token": "new_refresh"}
    manager.save_token(new_token)
    
    assert temp_auth_file.exists()
    saved_data = json.loads(temp_auth_file.read_text())
    assert saved_data == new_token
    assert manager.token == new_token

def test_freesound_manager_search_bgm(mock_freesound_client):
    manager = FreesoundManager(client_id="id", client_secret="secret")
    
    # Mocking search results
    mock_results = MagicMock()
    mock_sound = MagicMock()
    mock_sound.id = 123
    mock_sound.name = "Test Sound"
    mock_results.results = [mock_sound]
    manager.client.text_search.return_value = mock_results
    
    tags = ["loop", "music"]
    results = manager.search_bgm(tags)
    
    assert len(results) == 1
    assert results[0].id == 123
    
    # Check if text_search was called with correct parameters
    # The actual implementation might use tags in the query or filter
    manager.client.text_search.assert_called_once()
    args, kwargs = manager.client.text_search.call_args
    assert "loop" in kwargs["query"]
    assert "music" in kwargs["query"]
    assert "type:(wav OR flac)" in kwargs["filter"]

def test_freesound_manager_download_and_convert(mock_freesound_client, tmp_path):
    manager = FreesoundManager(client_id="id", client_secret="secret")
    
    # Mocking sound object
    mock_sound = MagicMock()
    mock_sound.id = 123
    mock_sound.name = "test_sound.wav"
    manager.client.get_sound.return_value = mock_sound
    
    # Mocking AudioSegment and tempfile.TemporaryDirectory
    with patch('pydub.AudioSegment.from_file') as mock_from_file, \
         patch('tempfile.TemporaryDirectory') as mock_temp_dir:
        
        mock_audio = MagicMock()
        mock_from_file.return_value = mock_audio
        
        # Setup mock temp directory
        mock_temp_path = tmp_path / "fake_temp"
        mock_temp_path.mkdir()
        mock_temp_dir.return_value.__enter__.return_value = str(mock_temp_path)
        
        # Simulate sound.retrieve(temp_dir) - it doesn't take filename in actual lib but path
        def side_effect(directory):
            (Path(directory) / "test_sound.wav").write_text("fake audio data")
            return mock_sound
        
        mock_sound.retrieve.side_effect = side_effect
        
        output_file = tmp_path / "output.wav"
        
        final_path = manager.download_and_convert(123, str(output_file))
        
        assert final_path == str(output_file)
        manager.client.get_sound.assert_called_with(123)
        mock_sound.retrieve.assert_called_once_with(str(mock_temp_path))
        mock_from_file.assert_called_once()
        # Verify it's called with the correct output path and 44.1kHz parameters
        mock_audio.export.assert_called_once_with(
            str(output_file), 
            format="wav", 
            parameters=["-ar", "44100"]
        )
