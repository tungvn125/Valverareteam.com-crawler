"""Tests for CLI client — APIClient and CLIError."""
import pytest

from vvr_scraper.cli_client.client import APIClient, CLIError


class TestCLIError:
    def test_cli_error_with_message(self):
        err = CLIError("Something went wrong", exit_code=1)
        assert str(err) == "Something went wrong"
        assert err.exit_code == 1

    def test_cli_error_default_exit_code(self):
        err = CLIError("Error")
        assert err.exit_code == 1


class TestAPIClientInit:
    def test_default_base_url(self):
        client = APIClient()
        assert client.base_url == "http://127.0.0.1:8000"

    def test_custom_host_port(self):
        client = APIClient(host="192.168.1.100", port=8080)
        assert client.base_url == "http://192.168.1.100:8080"

    def test_token_passed_to_token_manager(self):
        client = APIClient(token="my-token")
        assert client.token_manager._token == "my-token"


class TestAPIClientErrorMapping:
    def test_error_messages_complete(self):
        client = APIClient()
        assert 401 in client.ERROR_MESSAGES
        assert 403 in client.ERROR_MESSAGES
        assert 404 in client.ERROR_MESSAGES
        assert 413 in client.ERROR_MESSAGES
        assert 429 in client.ERROR_MESSAGES
        assert 500 in client.ERROR_MESSAGES

    def test_401_message(self):
        client = APIClient()
        assert "đăng nhập" in client.ERROR_MESSAGES[401].lower() or "login" in client.ERROR_MESSAGES[401].lower()

    def test_404_message(self):
        client = APIClient()
        assert "không tìm thấy" in client.ERROR_MESSAGES[404].lower() or "not found" in client.ERROR_MESSAGES[404].lower()