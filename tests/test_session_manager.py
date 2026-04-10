"""
Tests for session_manager.py — save_session, load_session.
capture_session is not tested because it requires a real browser.
"""

import json
import os

from vvr_scraper.session_manager import load_session, save_session


class TestSaveSession:
    def test_saves_valid_json(self, tmp_path):
        file_path = str(tmp_path / "session.json")
        state = {
            "cookies": [{"name": "cf_clearance", "value": "abc123"}],
            "origins": [{"origin": "https://valvrareteam.net", "localStorage": []}]
        }

        save_session(state, file_path)

        assert os.path.exists(file_path)
        with open(file_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == state

    def test_preserves_unicode(self, tmp_path):
        file_path = str(tmp_path / "session.json")
        state = {"note": "tiếng Việt đầy đủ dấu"}

        save_session(state, file_path)

        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        assert "tiếng Việt đầy đủ dấu" in content

    def test_overwrites_existing(self, tmp_path):
        file_path = str(tmp_path / "session.json")
        save_session({"first": True}, file_path)
        save_session({"second": True}, file_path)

        with open(file_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == {"second": True}


class TestLoadSession:
    def test_loads_valid_session(self, tmp_path):
        file_path = str(tmp_path / "session.json")
        data = {"cookies": [], "origins": []}
        with open(file_path, "w") as f:
            json.dump(data, f)

        result = load_session(file_path)
        assert result == data

    def test_returns_none_for_missing_file(self):
        result = load_session("/nonexistent/path/session.json")
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        file_path = str(tmp_path / "bad.json")
        with open(file_path, "w") as f:
            f.write("not valid json {{{}}")

        result = load_session(file_path)
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path):
        file_path = str(tmp_path / "empty.json")
        with open(file_path, "w") as f:
            f.write("")

        result = load_session(file_path)
        assert result is None
