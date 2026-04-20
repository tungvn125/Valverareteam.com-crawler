"""
Unit tests for cli.py — argument parsing, chapter filtering, chapter selection,
URL resolution, export config, and cleanup.
"""

import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

# =============================================================================
# Argument Parsing
# =============================================================================


class TestArgumentParsing:
    """Test CLI argument parsing without running the full CLI."""

    def _parse(self, args_list):
        """Helper to parse args without triggering side effects."""
        with patch.object(sys, "argv", ["vvrt"] + args_list):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        return cli

    def test_default_format_is_epub(self):
        cli = self._parse(["ten-truyen"])
        assert cli.args.format == ["EPUB"]

    def test_multiple_formats(self):
        cli = self._parse(["ten-truyen", "-f", "EPUB", "PDF", "MP3"])
        assert set(cli.args.format) == {"EPUB", "PDF", "MP3"}

    def test_all_flag(self):
        cli = self._parse(["ten-truyen", "--all"])
        assert cli.args.all is True
        assert cli.args.volumes is None
        assert cli.args.chapters is None

    def test_volumes_selection(self):
        cli = self._parse(["ten-truyen", "--volumes", "1", "3"])
        assert cli.args.volumes == [1, 3]
        assert cli.args.all is False

    def test_chapters_selection(self):
        cli = self._parse(["ten-truyen", "--chapters", "1", "5", "10"])
        assert cli.args.chapters == [1, 5, 10]

    def test_gop_default_is_rieng(self):
        cli = self._parse(["ten-truyen"])
        assert cli.args.gop == "rieng"

    def test_gop_volume(self):
        cli = self._parse(["ten-truyen", "-g", "volume"])
        assert cli.args.gop == "volume"

    def test_gop_tatca(self):
        cli = self._parse(["ten-truyen", "-g", "tatca"])
        assert cli.args.gop == "tatca"

    def test_output_folder(self):
        cli = self._parse(["ten-truyen", "-o", "/tmp/output"])
        assert cli.args.output_folder == "/tmp/output"

    def test_tasks_default(self):
        cli = self._parse(["ten-truyen"])
        assert cli.args.tasks == 5

    def test_custom_tasks(self):
        cli = self._parse(["ten-truyen", "-t", "10"])
        assert cli.args.tasks == 10

    def test_login_flag(self):
        cli = self._parse(["ten-truyen", "--login"])
        assert cli.args.login is True

    def test_verbose_flag(self):
        cli = self._parse(["ten-truyen", "--verbose"])
        assert cli.args.verbose is True

    def test_fps_default(self):
        cli = self._parse(["ten-truyen"])
        assert cli.args.fps == 30

    def test_render_format_default(self):
        cli = self._parse(["ten-truyen"])
        assert cli.args.render_format == "landscape"

    def test_web_server_args(self):
        cli = self._parse(["web", "--host", "0.0.0.0", "--port", "9000"])
        assert cli.args.host == "0.0.0.0"
        assert cli.args.port == 9000

    def test_skip_illustrations(self):
        cli = self._parse(["ten-truyen", "--khong-minh-hoa"])
        assert cli.args.khong_minh_hoa is True

    def test_head_playwright_flag(self):
        cli = self._parse(["ten-truyen", "--head-playwright"])
        assert cli.args.head_playwright is True
        assert cli.args.headless_playwright is False

    def test_headless_playwright_flag(self):
        cli = self._parse(["ten-truyen", "--headless-playwright"])
        assert cli.args.headless_playwright is True
        assert cli.args.head_playwright is False

    def test_head_playwright_and_headless_playwright_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            self._parse(["ten-truyen", "--head-playwright", "--headless-playwright"])

    def test_no_positional_args(self):
        cli = self._parse([])
        assert cli.args.ten_truyen == []

    def test_multiple_novels(self):
        cli = self._parse(["truyen-1", "truyen-2", "truyen-3"])
        assert cli.args.ten_truyen == ["truyen-1", "truyen-2", "truyen-3"]

    def test_is_cli_mode_with_args(self):
        # Simulate having args in sys.argv
        with patch.object(sys, "argv", ["vvrt", "ten-truyen"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        assert cli.is_cli_mode is True


# =============================================================================
# Chapter Filtering
# =============================================================================


class TestFilterChapters:
    def _make_cli(self, khong_minh_hoa=False):
        with patch.object(sys, "argv", ["vvrt", "test"] + (["--khong-minh-hoa"] if khong_minh_hoa else [])):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        return ValvrareScraperCLI()

    def test_skip_illustrations(self):
        cli = self._make_cli(khong_minh_hoa=True)
        chapter_data = [
            {
                "volume": "V1",
                "chapters": [
                    {"title": "Chương 1", "url": "/c1"},
                    {"title": "Minh họa Vol 1", "url": "/mh1"},
                    {"title": "Chương 2", "url": "/c2"},
                ],
            }
        ]
        result = cli.filter_chapters(chapter_data)
        assert len(result) == 1
        assert len(result[0]["chapters"]) == 2
        titles = [c["title"] for c in result[0]["chapters"]]
        assert "Minh họa Vol 1" not in titles

    def test_keep_all_without_flag(self):
        cli = self._make_cli(khong_minh_hoa=False)
        chapter_data = [
            {
                "volume": "V1",
                "chapters": [
                    {"title": "Chương 1", "url": "/c1"},
                    {"title": "Minh họa", "url": "/mh"},
                ],
            }
        ]
        result = cli.filter_chapters(chapter_data)
        assert len(result[0]["chapters"]) == 2

    def test_empty_volume_after_filter(self):
        cli = self._make_cli(khong_minh_hoa=True)
        chapter_data = [
            {
                "volume": "Minh họa",
                "chapters": [
                    {"title": "Minh họa 1", "url": "/mh1"},
                    {"title": "Minh họa 2", "url": "/mh2"},
                ],
            },
            {
                "volume": "V1",
                "chapters": [
                    {"title": "Chương 1", "url": "/c1"},
                ],
            },
        ]
        result = cli.filter_chapters(chapter_data)
        assert len(result) == 1
        assert result[0]["volume"] == "V1"


# =============================================================================
# Chapter Selection (CLI Mode)
# =============================================================================


class TestSelectChapters:
    def _make_cli(self, extra_args=None):
        args = ["vvrt", "test"] + (extra_args or [])
        with patch.object(sys, "argv", args):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        return ValvrareScraperCLI()

    def test_select_all_chapters(self):
        cli = self._make_cli()
        data = [
            {
                "volume": "V1",
                "chapters": [
                    {"title": "C1", "url": "/c1"},
                    {"title": "C2", "url": "/c2"},
                ],
            },
            {
                "volume": "V2",
                "chapters": [
                    {"title": "C3", "url": "/c3"},
                ],
            },
        ]
        selected = cli.select_chapters_to_download(data)
        assert len(selected) == 3

    def test_select_by_volumes(self):
        cli = self._make_cli(["--volumes", "2"])
        data = [
            {"volume": "V1", "chapters": [{"title": "C1", "url": "/c1"}]},
            {"volume": "V2", "chapters": [{"title": "C2", "url": "/c2"}, {"title": "C3", "url": "/c3"}]},
        ]
        selected = cli.select_chapters_to_download(data)
        assert len(selected) == 2
        assert selected[0]["title"] == "C2"

    def test_select_by_chapters(self):
        cli = self._make_cli(["--chapters", "1", "3"])
        data = [
            {
                "volume": "V1",
                "chapters": [
                    {"title": "C1", "url": "/c1"},
                    {"title": "C2", "url": "/c2"},
                    {"title": "C3", "url": "/c3"},
                ],
            },
        ]
        selected = cli.select_chapters_to_download(data)
        assert len(selected) == 2
        assert selected[0]["title"] == "C1"
        assert selected[1]["title"] == "C3"

    def test_out_of_range_volumes_ignored(self):
        cli = self._make_cli(["--volumes", "99"])
        data = [{"volume": "V1", "chapters": [{"title": "C1", "url": "/c1"}]}]
        selected = cli.select_chapters_to_download(data)
        assert len(selected) == 0

    def test_out_of_range_chapters_ignored(self):
        cli = self._make_cli(["--chapters", "100"])
        data = [{"volume": "V1", "chapters": [{"title": "C1", "url": "/c1"}]}]
        selected = cli.select_chapters_to_download(data)
        assert len(selected) == 0


# =============================================================================
# Export Config (CLI Mode)
# =============================================================================


class TestExportConfig:
    @pytest.mark.asyncio
    async def test_cli_mode_config(self):
        with patch.object(sys, "argv", ["vvrt", "test", "-f", "EPUB", "PDF", "-g", "tatca", "-t", "3"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        config = await cli._get_export_config("https://valvrareteam.net/test")

                        assert config["mode_idx"] == 0  # tatca
                        assert "EPUB" in config["formats"]
                        assert "PDF" in config["formats"]
                        assert config["tasks"] == 3
                        assert config["fps"] == 30
                        assert config["render_format"] == "landscape"

    @pytest.mark.asyncio
    async def test_gop_rieng_mapping(self):
        with patch.object(sys, "argv", ["vvrt", "test", "-g", "rieng"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        config = await cli._get_export_config("https://valvrareteam.net/test")
                        assert config["mode_idx"] == 1  # rieng

    @pytest.mark.asyncio
    async def test_gop_volume_mapping(self):
        with patch.object(sys, "argv", ["vvrt", "test", "-g", "volume"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        config = await cli._get_export_config("https://valvrareteam.net/test")
                        assert config["mode_idx"] == 2  # volume


# =============================================================================
# Cleanup
# =============================================================================


class TestCleanup:
    def test_cleanup_no_skipped(self):
        with patch.object(sys, "argv", ["vvrt", "test"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        cli.skipped_urls = []
                        cli.output_folder = "/tmp/test_output"
                        cli._cleanup()  # Should not raise

    def test_cleanup_with_skipped(self, tmp_path):
        with patch.object(sys, "argv", ["vvrt", "test"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        cli.skipped_urls = [
                            "https://valvrareteam.net/c1",
                            "https://valvrareteam.net/c2",
                        ]
                        cli.output_folder = str(tmp_path)
                        cli._cleanup()

                        log_file = tmp_path / "cac_chuong_da_bo_qua.txt"
                        assert log_file.exists()
                        content = log_file.read_text()
                        assert "https://valvrareteam.net/c1" in content
                        assert "https://valvrareteam.net/c2" in content


# =============================================================================
# Run command dispatch
# =============================================================================


class TestRunCommandDispatch:
    @pytest.mark.asyncio
    async def test_run_command_missing_manifest(self):
        with patch.object(sys, "argv", ["vvrt", "run"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        await cli.run()  # Should log error but not crash

    @pytest.mark.asyncio
    async def test_web_command_dispatch(self):
        with patch.object(sys, "argv", ["vvrt", "web", "--port", "9999"]):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        # run_web_server is imported lazily inside run(), so patch at source
                        with patch("vvr_scraper.web.run_web_server", new_callable=AsyncMock) as mock_web:
                            from vvr_scraper.cli import ValvrareScraperCLI

                            cli = ValvrareScraperCLI()
                            with patch("webbrowser.open"):
                                await cli.run()
                            mock_web.assert_called_once_with(
                                host="127.0.0.1", port=9999, num_workers=1, playwright_mode=None
                            )


class TestSocialCreateAdminCommand:
    def test_social_create_admin_command_parses(self):
        with patch.object(
            sys, "argv", ["vvrt", "social", "create-admin", "--username", "alice", "--password", "secret123"]
        ):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        assert cli.args.ten_truyen[:2] == ["social", "create-admin"]
                        assert cli.args.username == "alice"
                        assert cli.args.password == "secret123"

    def test_social_create_admin_defaults_display_name(self):
        with patch.object(
            sys, "argv", ["vvrt", "social", "create-admin", "--username", "bob", "--password", "pass1234"]
        ):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        assert cli.args.display_name is None

    @pytest.mark.asyncio
    async def test_social_create_admin_dispatches(self):
        with patch.object(
            sys, "argv", ["vvrt", "social", "create-admin", "--username", "alice", "--password", "secret123"]
        ):
            with patch("vvr_scraper.cli.configure_logger"):
                with patch("vvr_scraper.cli.get_config_path", return_value="/tmp/fake.db"):
                    with patch("vvr_scraper.cli.DatabaseManager"):
                        from vvr_scraper.cli import ValvrareScraperCLI

                        cli = ValvrareScraperCLI()
                        with patch("vvr_scraper.social.db.SocialDatabaseManager") as MockSocialDB:
                            mock_db = AsyncMock()
                            mock_db.create_admin_user = AsyncMock(return_value={"username": "alice"})
                            MockSocialDB.return_value = mock_db
                            with patch("vvr_scraper.social.auth.hash_password", return_value="hashed_pw"):
                                await cli.run()
                        mock_db.init_db.assert_called_once()
                        mock_db.create_admin_user.assert_called_once_with(
                            username="alice", hashed_password="hashed_pw", display_name="alice"
                        )
                        mock_db.close.assert_called_once()


class TestRunWebServerPlaywrightModeEnvRestore:
    @pytest.mark.asyncio
    async def test_restore_previous_env_value_after_serve(self, monkeypatch):
        monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "head")

        from vvr_scraper.web import run_web_server

        mock_server = Mock()
        mock_server.serve = AsyncMock(return_value=None)

        with patch("vvr_scraper.web.uvicorn.Config", return_value=Mock()):
            with patch("vvr_scraper.web.uvicorn.Server", return_value=mock_server):
                await run_web_server(playwright_mode="headless")

        assert os.environ["VVR_PLAYWRIGHT_MODE"] == "head"

    @pytest.mark.asyncio
    async def test_remove_env_when_originally_unset(self, monkeypatch):
        monkeypatch.delenv("VVR_PLAYWRIGHT_MODE", raising=False)

        from vvr_scraper.web import run_web_server

        mock_server = Mock()
        mock_server.serve = AsyncMock(return_value=None)

        with patch("vvr_scraper.web.uvicorn.Config", return_value=Mock()):
            with patch("vvr_scraper.web.uvicorn.Server", return_value=mock_server):
                await run_web_server(playwright_mode="headless")

        assert "VVR_PLAYWRIGHT_MODE" not in os.environ

    @pytest.mark.asyncio
    async def test_restore_env_on_serve_exception(self, monkeypatch):
        monkeypatch.setenv("VVR_PLAYWRIGHT_MODE", "head")

        from vvr_scraper.web import run_web_server

        mock_server = Mock()
        mock_server.serve = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("vvr_scraper.web.uvicorn.Config", return_value=Mock()):
            with patch("vvr_scraper.web.uvicorn.Server", return_value=mock_server):
                with pytest.raises(RuntimeError, match="boom"):
                    await run_web_server(playwright_mode="headless")

        assert os.environ["VVR_PLAYWRIGHT_MODE"] == "head"
