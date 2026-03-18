import os
import json
import pytest
from session_manager import save_session, load_session

def test_save_load_session(tmp_path):
    session_file = tmp_path / ".vvr_session.json"
    test_state = {"cookies": [{"name": "token", "value": "test_token"}], "origins": []}
    save_session(test_state, str(session_file))
    assert session_file.exists()
    loaded_state = load_session(str(session_file))
    assert loaded_state == test_state
