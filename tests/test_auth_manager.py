"""Tests for CLI client — TokenManager and AuthenticationRequired."""
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from vvr_scraper.cli_client.auth_manager import AuthenticationRequired, TokenManager


class TestTokenManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.token_path = os.path.join(self.tmpdir, "token.json")

    def teardown_method(self):
        if os.path.exists(self.token_path):
            os.remove(self.token_path)
        os.rmdir(self.tmpdir)

    def test_get_token_from_constructor(self):
        mgr = TokenManager(token="test-token-123", token_path=self.token_path)
        assert mgr.get_token() == "test-token-123"

    def test_get_token_from_env_var(self):
        with patch.dict(os.environ, {"VVR_TOKEN": "env-token-456"}):
            mgr = TokenManager(token_path=self.token_path)
            assert mgr.get_token() == "env-token-456"

    def test_get_token_from_file(self):
        data = {
            "token": "file-token-789",
            "username": "alice",
            "user_id": "uuid-1",
            "role": "member",
            "created_at": "2026-04-21T10:00:00Z",
        }
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        assert mgr.get_token() == "file-token-789"

    def test_get_token_priority_constructor_over_env(self):
        with patch.dict(os.environ, {"VVR_TOKEN": "env-token"}):
            mgr = TokenManager(token="ctor-token", token_path=self.token_path)
            assert mgr.get_token() == "ctor-token"

    def test_get_token_priority_env_over_file(self):
        data = {"token": "file-token", "username": "a", "user_id": "b", "role": "member", "created_at": "2026-01-01T00:00:00Z"}
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        with patch.dict(os.environ, {"VVR_TOKEN": "env-token"}):
            mgr = TokenManager(token_path=self.token_path)
            assert mgr.get_token() == "env-token"

    def test_no_token_raises_authentication_required(self):
        mgr = TokenManager(token_path=self.token_path)
        with pytest.raises(AuthenticationRequired):
            mgr.get_token()

    def test_logout_deletes_token_file(self):
        data = {"token": "tok", "username": "a", "user_id": "b", "role": "member", "created_at": "2026-01-01T00:00:00Z"}
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        mgr.logout()
        assert not os.path.exists(self.token_path)

    def test_is_authenticated_with_file(self):
        data = {"token": "tok", "username": "a", "user_id": "b", "role": "member", "created_at": "2026-01-01T00:00:00Z"}
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        assert mgr.is_authenticated() is True

    def test_is_authenticated_without_any_token(self):
        mgr = TokenManager(token_path=self.token_path)
        assert mgr.is_authenticated() is False

    def test_save_token_writes_file(self):
        mgr = TokenManager(token_path=self.token_path)
        token_data = {
            "token": "new-token",
            "username": "bob",
            "user_id": "uuid-2",
            "role": "admin",
            "created_at": "2026-04-21T12:00:00Z",
        }
        mgr.save_token(token_data)
        assert os.path.exists(self.token_path)
        with open(self.token_path) as f:
            saved = json.load(f)
        assert saved["token"] == "new-token"
        assert saved["username"] == "bob"