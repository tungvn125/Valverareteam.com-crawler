from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.cli import ValvrareScraperCLI


@pytest.mark.asyncio
async def test_freesound_login_subcommand():
    # Mock FreesoundManager
    mock_fs_instance = MagicMock()
    mock_fs_instance.get_auth_url.return_value = "https://mock-auth-url"
    mock_fs_instance.exchange_code = AsyncMock()

    # Mock input
    mock_input = MagicMock(return_value="mock-code")

    # Mock Console to avoid actual printing during tests
    with patch("vvr_scraper.cli.console"):
        with patch("vvr_scraper.cli.ValvrareScraperCLI._parse_arguments") as mock_parse:
            args = MagicMock()
            args.ten_truyen = ["freesound-login"]
            args.verbose = False
            mock_parse.return_value = args

            cli = ValvrareScraperCLI()

            # Patch where it's DEFINED since it's imported inside run()
            with patch("vvr_scraper.freesound_manager.FreesoundManager") as mock_fs_class:
                mock_fs_class.return_value = mock_fs_instance
                with patch("builtins.input", mock_input):
                    await cli.run()

    mock_fs_instance.get_auth_url.assert_called_once()
    mock_input.assert_called_once()
    mock_fs_instance.exchange_code.assert_called_once_with("mock-code")


@pytest.mark.asyncio
async def test_freesound_login_empty_code():
    mock_fs_instance = MagicMock()
    mock_fs_instance.get_auth_url.return_value = "https://mock-auth-url"
    mock_input = MagicMock(return_value="")  # Empty code

    with patch("vvr_scraper.cli.console"):
        with patch("vvr_scraper.cli.ValvrareScraperCLI._parse_arguments") as mock_parse:
            args = MagicMock()
            args.ten_truyen = ["freesound-login"]
            args.verbose = False
            mock_parse.return_value = args
            cli = ValvrareScraperCLI()
            with patch("vvr_scraper.freesound_manager.FreesoundManager") as mock_fs_class:
                mock_fs_class.return_value = mock_fs_instance
                with patch("builtins.input", mock_input):
                    await cli.run()

    mock_fs_instance.exchange_code.assert_not_called()


@pytest.mark.asyncio
async def test_freesound_login_error():
    mock_fs_instance = MagicMock()
    mock_fs_instance.get_auth_url.return_value = "https://mock-auth-url"
    mock_fs_instance.exchange_code = AsyncMock(side_effect=Exception("Auth error"))
    mock_input = MagicMock(return_value="mock-code")

    with patch("vvr_scraper.cli.console"):
        with patch("vvr_scraper.cli.logger") as mock_logger:
            with patch("vvr_scraper.cli.ValvrareScraperCLI._parse_arguments") as mock_parse:
                args = MagicMock()
                args.ten_truyen = ["freesound-login"]
                args.verbose = False
                mock_parse.return_value = args
                cli = ValvrareScraperCLI()
                with patch("vvr_scraper.freesound_manager.FreesoundManager") as mock_fs_class:
                    mock_fs_class.return_value = mock_fs_instance
                    with patch("builtins.input", mock_input):
                        await cli.run()

    mock_logger.error.assert_called_with("Lỗi khi đăng nhập Freesound: Auth error")
