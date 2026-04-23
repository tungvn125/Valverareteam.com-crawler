"""
Extended tests for utils.py — covering normalize_vietnamese_url, get_config_path,
get_token_from_state, create_folders_from_tree, and configure_logger.
"""

import json
import os

import vvr_scraper.utils as utils
from vvr_scraper.utils import (
    configure_logger,
    create_folders_from_tree,
    get_config_dir,
    get_config_path,
    get_token_from_state,
    normalize_vietnamese_url,
)

# =============================================================================
# normalize_vietnamese_url
# =============================================================================


class TestNormalizeVietnameseUrl:
    def test_basic_vietnamese(self):
        assert normalize_vietnamese_url("Đấu Phá Thương Khung") == "dau-pha-thuong-khung"

    def test_all_diacritics(self):
        result = normalize_vietnamese_url("ăâđêôơư")
        assert result == "aadeoou"

    def test_special_chars_removed(self):
        assert normalize_vietnamese_url("Tên ~ Truyện: (Tập 1)") == "ten-truyen-tap-1"

    def test_collapse_multiple_hyphens(self):
        assert normalize_vietnamese_url("a  -  b") == "a-b"

    def test_strip_leading_trailing_hyphens(self):
        assert normalize_vietnamese_url("--hello--") == "hello"

    def test_empty_string(self):
        assert normalize_vietnamese_url("") == ""

    def test_none_input(self):
        assert normalize_vietnamese_url(None) == ""

    def test_numbers_preserved(self):
        assert normalize_vietnamese_url("Chương 123") == "chuong-123"

    def test_mixed_case_lowered(self):
        assert normalize_vietnamese_url("ABC DEF") == "abc-def"

    def test_complex_title(self):
        result = normalize_vietnamese_url("Vật Chủ Tế Của Sakuchishi ~Nghi Thức Dị Giáo~")
        assert "vat-chu-te-cua-sakuchishi" in result
        assert "~" not in result

    def test_dots_and_commas_removed(self):
        result = normalize_vietnamese_url("Vol.1, Chapter.2")
        assert "." not in result
        assert "," not in result


# =============================================================================
# get_token_from_state
# =============================================================================


class TestGetTokenFromState:
    def test_none_state(self):
        assert get_token_from_state(None) is None

    def test_empty_dict(self):
        assert get_token_from_state({}) is None

    def test_no_origins(self):
        assert get_token_from_state({"other": "data"}) is None

    def test_direct_access_token(self):
        state = {
            "origins": [
                {"origin": "https://valvrareteam.net", "localStorage": [{"name": "accessToken", "value": "jwt-123"}]}
            ]
        }
        assert get_token_from_state(state) == "jwt-123"

    def test_direct_token_key(self):
        state = {
            "origins": [{"origin": "https://valvrareteam.net", "localStorage": [{"name": "token", "value": "tok-456"}]}]
        }
        assert get_token_from_state(state) == "tok-456"

    def test_direct_jwt_key(self):
        state = {
            "origins": [{"origin": "https://valvrareteam.net", "localStorage": [{"name": "jwt", "value": "jwt-789"}]}]
        }
        assert get_token_from_state(state) == "jwt-789"

    def test_auth_storage_nested(self):
        state = {
            "origins": [
                {
                    "origin": "https://valvrareteam.net",
                    "localStorage": [
                        {"name": "auth-storage", "value": json.dumps({"state": {"token": "nested-token-abc"}})}
                    ],
                }
            ]
        }
        assert get_token_from_state(state) == "nested-token-abc"

    def test_auth_storage_with_access_token(self):
        state = {
            "origins": [
                {
                    "origin": "https://valvrareteam.net",
                    "localStorage": [
                        {"name": "auth-storage", "value": json.dumps({"state": {"accessToken": "at-xyz"}})}
                    ],
                }
            ]
        }
        assert get_token_from_state(state) == "at-xyz"

    def test_auth_storage_invalid_json(self):
        state = {
            "origins": [
                {
                    "origin": "https://valvrareteam.net",
                    "localStorage": [{"name": "auth-storage", "value": "not-valid-json{{"}],
                }
            ]
        }
        assert get_token_from_state(state) is None

    def test_no_matching_origin(self):
        state = {
            "origins": [{"origin": "https://other-site.com", "localStorage": [{"name": "accessToken", "value": "abc"}]}]
        }
        assert get_token_from_state(state) is None

    def test_empty_local_storage(self):
        state = {"origins": [{"origin": "https://valvrareteam.net", "localStorage": []}]}
        assert get_token_from_state(state) is None


# =============================================================================
# get_config_dir / get_config_path
# =============================================================================


class TestConfigPaths:
    def test_get_config_dir_creates_directory(self):
        config_dir = get_config_dir()
        assert os.path.isdir(config_dir)
        assert ".config/vvr-scraper" in config_dir

    def test_get_config_path_returns_path(self):
        path = get_config_path("test_config.json")
        assert path.endswith("test_config.json")
        assert ".config/vvr-scraper" in path

    def test_get_config_path_auto_migrate(self, tmp_path, monkeypatch):
        """Test that files in CWD are auto-migrated to config dir."""
        # Create a file in a fake CWD
        cwd_file = tmp_path / "migrate_test.json"
        cwd_file.write_text('{"key": "value"}')

        # Monkeypatch CWD and config dir
        fake_config = tmp_path / "config"
        fake_config.mkdir()
        monkeypatch.setattr("vvr_scraper.utils.get_config_dir", lambda: str(fake_config))
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

        from vvr_scraper.utils import get_config_path

        result = get_config_path("migrate_test.json")

        assert os.path.exists(result)
        assert str(fake_config) in result


# =============================================================================
# create_folders_from_tree
# =============================================================================


class TestCreateFoldersFromTree:
    def test_creates_folders_from_file(self, tmp_path):
        tree_file = tmp_path / "tree.txt"
        tree_file.write_text("Volume 1\nVolume 2\nVolume 3\n")
        base = str(tmp_path / "output")

        create_folders_from_tree(str(tree_file), base)

        assert os.path.isdir(os.path.join(base, "Volume 1"))
        assert os.path.isdir(os.path.join(base, "Volume 2"))
        assert os.path.isdir(os.path.join(base, "Volume 3"))

    def test_handles_missing_file(self, tmp_path):
        base = str(tmp_path / "output")
        create_folders_from_tree("/nonexistent/file.txt", base)
        # Should create base folder as fallback
        assert os.path.isdir(base)

    def test_skips_empty_lines(self, tmp_path):
        tree_file = tmp_path / "tree.txt"
        tree_file.write_text("Volume 1\n\n\nVolume 2\n")
        base = str(tmp_path / "output")

        create_folders_from_tree(str(tree_file), base)

        subdirs = os.listdir(base)
        assert len(subdirs) == 2


# =============================================================================
# resolve_playwright_headless
# =============================================================================


def test_resolve_playwright_headless_defaults_to_true(monkeypatch):
    monkeypatch.delenv("VVR_PLAYWRIGHT_MODE", raising=False)
    assert utils.resolve_playwright_headless() is True


def test_resolve_playwright_headless_from_env_head(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "head")
    assert utils.resolve_playwright_headless() is False


def test_resolve_playwright_headless_from_env_headless(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "headless")
    assert utils.resolve_playwright_headless() is True


def test_resolve_playwright_headless_invalid_env_falls_back_default(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "invalid")
    assert utils.resolve_playwright_headless() is True


def test_resolve_playwright_headless_cli_head_overrides_env(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "headless")
    assert utils.resolve_playwright_headless(cli_mode="head") is False


def test_resolve_playwright_headless_cli_headless_overrides_env(monkeypatch):
    monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "head")
    assert utils.resolve_playwright_headless(cli_mode="headless") is True


# =============================================================================
# configure_logger
# =============================================================================


class TestConfigureLogger:
    def test_verbose_mode(self):
        # Should not raise
        configure_logger(verbose=True)

    def test_normal_mode(self):
        configure_logger(verbose=False)


# --- Tests cho Fix #4: slug_candidates refactor ---
import pytest
from unittest.mock import AsyncMock, patch

from vvr_scraper.models import StoryInfo


@pytest.mark.asyncio
async def test_resolve_story_url_uses_registry_slug_candidates(monkeypatch):
    """resolve_story_url() phải dùng REGISTRY.slug_candidates() thay vì hardcoded list."""
    mock_source = AsyncMock()
    mock_source.get_info = AsyncMock(
        return_value=StoryInfo(
            title="Found Story",
            author="Author",
            description="Desc",
            slug="my-novel",
        )
    )

    class FakeSource:
        pass

    with (
        patch("vvr_scraper.utils.REGISTRY") as mock_registry,
        patch("vvr_scraper.utils.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("sitemap fail"))
        mock_client_cls.return_value = mock_client

        mock_registry.slug_candidates.return_value = [
            (FakeSource, "https://newsite.test/truyen/my-novel")
        ]
        mock_registry.get.return_value = mock_source

        from vvr_scraper.utils import resolve_story_url

        result = await resolve_story_url("my-novel")

    mock_registry.slug_candidates.assert_called_once()
    assert result == "https://newsite.test/truyen/my-novel"


@pytest.mark.asyncio
async def test_resolve_story_url_skips_candidate_when_title_unknown(monkeypatch):
    """resolve_story_url() phải bỏ qua candidate nếu source trả title='Unknown'."""
    mock_source = AsyncMock()
    mock_source.get_info = AsyncMock(
        return_value=StoryInfo(
            title="Unknown",
            author="",
            description="",
            slug="my-novel",
        )
    )

    class FakeSource:
        pass

    with (
        patch("vvr_scraper.utils.REGISTRY") as mock_registry,
        patch("vvr_scraper.utils.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("sitemap fail"))
        mock_client_cls.return_value = mock_client

        mock_registry.slug_candidates.return_value = [
            (FakeSource, "https://newsite.test/truyen/my-novel")
        ]
        mock_registry.get.return_value = mock_source

        from vvr_scraper.utils import resolve_story_url

        result = await resolve_story_url("my-novel")

    assert result is None  # title="Unknown" → không accept
