"""
Unit tests for scraper_core.py — lay_chuong_httpx, lay_chuong_voi_hinh_anh, scrape_chapters.
All network calls are mocked.
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.models import ContentItem
from vvr_scraper.scraper_core import (
    lay_thong_tin_truyen,
    lay_chuong_httpx,
    lay_chuong_voi_hinh_anh,
    scrape_chapters,
)
from vvr_scraper.utils import HEADERS

# =============================================================================
# lay_chuong_httpx (Fast Mode)
# =============================================================================


class TestLayChuongHttpx:
    @pytest.mark.asyncio
    async def test_extracts_text_and_images(self):
        html = """<html><body>
        <div class="chapter-content">
            <p>Đoạn văn 1</p>
            <img src="https://cdn.example.com/img.jpg"/>
            <p>Đoạn văn 2</p>
        </div>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_response)
        client.headers = HEADERS.copy()

        result = await lay_chuong_httpx(client, "https://valvrareteam.net/chuong-1")

        assert result is not None
        assert len(result) == 3
        assert result[0].type == "text"
        assert result[0].data == "Đoạn văn 1"
        assert result[1].type == "image"
        assert result[1].data == "https://cdn.example.com/img.jpg"
        assert result[2].type == "text"
        assert result[2].data == "Đoạn văn 2"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_chapter_content(self):
        html = '<html><body><div class="other-class">No content here</div></body></html>'

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_response)
        client.headers = HEADERS.copy()

        result = await lay_chuong_httpx(client, "https://valvrareteam.net/chuong-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("Connection timeout"))
        client.headers = HEADERS.copy()

        result = await lay_chuong_httpx(client, "https://valvrareteam.net/chuong-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_content(self):
        html = '<html><body><div class="chapter-content"></div></body></html>'

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_response)
        client.headers = HEADERS.copy()

        result = await lay_chuong_httpx(client, "https://valvrareteam.net/chuong-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_token_added_to_headers(self):
        html = '<html><body><div class="chapter-content"><p>Text</p></div></body></html>'

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_response)
        client.headers = MagicMock()
        client.headers.copy.return_value = dict(HEADERS)

        await lay_chuong_httpx(client, "https://valvrareteam.net/chuong-1", token="my-jwt-token")

        # Verify get was called with headers containing Authorization
        call_kwargs = client.get.call_args
        headers_used = call_kwargs.kwargs.get("headers", {})
        assert headers_used.get("Authorization") == "Bearer my-jwt-token"

    @pytest.mark.asyncio
    async def test_skips_empty_paragraphs(self):
        html = """<html><body>
        <div class="chapter-content">
            <p>Real text</p>
            <p>   </p>
            <p></p>
            <p>More text</p>
        </div>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_response)
        client.headers = HEADERS.copy()

        result = await lay_chuong_httpx(client, "https://valvrareteam.net/chuong-1")

        assert len(result) == 2
        assert result[0].data == "Real text"
        assert result[1].data == "More text"

    @pytest.mark.asyncio
    async def test_verbose_mode_debug_logging(self):
        """Verbose mode should not crash on errors."""
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("Test error"))
        client.headers = HEADERS.copy()

        result = await lay_chuong_httpx(client, "https://valvrareteam.net/c1", verbose=True)
        assert result is None


class TestLayThongTinTruyen:
    @pytest.mark.asyncio
    async def test_cleans_up_temp_cover_file_when_save_fails(self, tmp_path):
        story_html = '<html><img class="rd-cover-image" src="https://cdn.example.com/cover.jpg"></html>'

        story_resp = MagicMock()
        story_resp.text = story_html
        story_resp.raise_for_status = MagicMock()

        image_resp = MagicMock()
        image_resp.content = b"fake-image-bytes"
        image_resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(side_effect=[story_resp, image_resp])

        cover_path = tmp_path / "vvr_cover_test.jpg"

        def fake_mkstemp(*args, **kwargs):
            path = Path(cover_path)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            return fd, str(path)

        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            if str(path) == str(cover_path) and mode == "wb":
                raise OSError("disk full")
            return real_open(path, mode, *args, **kwargs)

        with patch("vvr_scraper.scraper_core.tempfile.mkstemp", side_effect=fake_mkstemp):
            with patch("builtins.open", side_effect=fake_open):
                result = await lay_thong_tin_truyen(client, "test-story")

        assert result.cover_path is None
        assert cover_path.exists() is False


# =============================================================================
# lay_chuong_voi_hinh_anh (Playwright Reliable Mode)
# =============================================================================


class TestLayChuongVoiHinhAnh:
    @pytest.mark.asyncio
    async def test_extracts_content_from_playwright(self):
        # Mock the Playwright elements
        mock_page = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_elements = AsyncMock()
        mock_elements.count = AsyncMock(return_value=2)

        # Element 0: P tag
        mock_p = AsyncMock()
        mock_p.evaluate = AsyncMock(return_value="P")
        mock_p.inner_text = AsyncMock(return_value="Hello World")

        # Element 1: IMG tag
        mock_img = AsyncMock()
        mock_img.evaluate = AsyncMock(return_value="IMG")
        mock_img.get_attribute = AsyncMock(return_value="https://cdn.example.com/img.jpg")

        mock_elements.nth = lambda i: [mock_p, mock_img][i]

        mock_page.locator = MagicMock(return_value=mock_elements)

        result = await lay_chuong_voi_hinh_anh(mock_browser, "https://example.com/chuong-1")

        assert result is not None
        assert len(result) == 2
        assert result[0].type == "text"
        assert result[0].data == "Hello World"
        assert result[1].type == "image"

    @pytest.mark.asyncio
    async def test_returns_none_after_max_retries(self):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Timeout"))
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        result = await lay_chuong_voi_hinh_anh(mock_browser, "https://example.com/chuong-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        mock_page = AsyncMock()
        call_count = 0

        async def goto_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Transient error")

        mock_page.goto = AsyncMock(side_effect=goto_side_effect)

        mock_elements = AsyncMock()
        mock_elements.count = AsyncMock(return_value=1)
        mock_p = AsyncMock()
        mock_p.evaluate = AsyncMock(return_value="P")
        mock_p.inner_text = AsyncMock(return_value="Success after retry")
        mock_elements.nth = lambda i: mock_p
        mock_page.locator = MagicMock(return_value=mock_elements)

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        result = await lay_chuong_voi_hinh_anh(mock_browser, "https://example.com/chuong-1")
        assert result is not None
        assert result[0].data == "Success after retry"

    @pytest.mark.asyncio
    async def test_uses_session_state(self):
        session = {"cookies": [{"name": "test", "value": "123"}]}
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("fail"))
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        await lay_chuong_voi_hinh_anh(mock_browser, "https://example.com/c1", session_state=session)

        # Should have been called with storage_state
        mock_browser.new_page.assert_called_with(storage_state=session)


# =============================================================================
# scrape_chapters (Hybrid orchestrator)
# =============================================================================


class TestScrapeChapters:
    @pytest.mark.asyncio
    async def test_httpx_success_skips_playwright(self):
        """When HTTPX succeeds, Playwright should NOT be called."""
        content = [ContentItem(type="text", data="Content from HTTPX")]

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx", return_value=content):
            with patch("vvr_scraper.scraper_core.lay_chuong_voi_hinh_anh") as mock_pw:
                mock_browser = AsyncMock()
                result = await scrape_chapters(
                    mock_browser,
                    ["https://valvrareteam.net/chuong-1"],
                )

                assert "https://valvrareteam.net/chuong-1" in result
                assert result["https://valvrareteam.net/chuong-1"] == content
                mock_pw.assert_not_called()

    @pytest.mark.asyncio
    async def test_httpx_fails_fallback_to_playwright(self):
        """When HTTPX fails, should fallback to Playwright."""
        pw_content = [ContentItem(type="text", data="Content from Playwright")]

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx", return_value=None):
            with patch("vvr_scraper.scraper_core.lay_chuong_voi_hinh_anh", return_value=pw_content):
                mock_browser = AsyncMock()
                result = await scrape_chapters(
                    mock_browser,
                    ["https://valvrareteam.net/chuong-1"],
                )

                assert "https://valvrareteam.net/chuong-1" in result
                assert result["https://valvrareteam.net/chuong-1"] == pw_content

    @pytest.mark.asyncio
    async def test_both_fail_adds_to_skipped(self):
        """When both methods fail, URL should be in skipped_urls."""
        skipped = []

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx", return_value=None):
            with patch("vvr_scraper.scraper_core.lay_chuong_voi_hinh_anh", return_value=None):
                mock_browser = AsyncMock()
                result = await scrape_chapters(
                    mock_browser,
                    ["https://valvrareteam.net/chuong-1"],
                    skipped_urls=skipped,
                )

                assert len(result) == 0
                assert "https://valvrareteam.net/chuong-1" in skipped

    @pytest.mark.asyncio
    async def test_pre_scraped_skips_fetching(self):
        """Pre-scraped content should not trigger any HTTP call."""
        pre = {"https://valvrareteam.net/c1": [ContentItem(type="text", data="Cached")]}

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx") as mock_httpx:
            mock_browser = AsyncMock()
            result = await scrape_chapters(
                mock_browser,
                ["https://valvrareteam.net/c1"],
                pre_scraped=pre,
            )

            assert result["https://valvrareteam.net/c1"][0].data == "Cached"
            mock_httpx.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_chapter_done_callback(self):
        """Callback should be called for each chapter."""
        callback = AsyncMock()
        content = [ContentItem(type="text", data="OK")]

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx", return_value=content):
            mock_browser = AsyncMock()
            await scrape_chapters(
                mock_browser,
                ["https://valvrareteam.net/c1", "https://valvrareteam.net/c2"],
                on_chapter_done=callback,
            )

            assert callback.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_urls_concurrent(self):
        """Multiple URLs should be processed."""
        call_count = 0

        async def fake_httpx(client, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return [ContentItem(type="text", data=f"Content {call_count}")]

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx", side_effect=fake_httpx):
            mock_browser = AsyncMock()
            urls = [f"https://valvrareteam.net/c{i}" for i in range(5)]
            result = await scrape_chapters(mock_browser, urls, concurrent_tasks=3)

            assert len(result) == 5

    @pytest.mark.asyncio
    async def test_session_cookies_passed(self):
        """Session cookies should be used for httpx client."""
        session = {
            "cookies": [
                {"name": "session_id", "value": "abc123"},
                {"name": "cf_clearance", "value": "xyz"},
            ]
        }
        content = [ContentItem(type="text", data="OK")]

        with patch("vvr_scraper.scraper_core.lay_chuong_httpx", return_value=content):
            mock_browser = AsyncMock()
            result = await scrape_chapters(
                mock_browser,
                ["https://valvrareteam.net/c1"],
                session_state=session,
            )

            assert len(result) == 1
