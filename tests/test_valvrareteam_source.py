"""Unit tests for ValvrareteamSource."""

import os
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from vvr_scraper.sources.valvrareteam import ValvrareteamSource


class TestValvrareteamGetInfo:
    @pytest.mark.asyncio
    async def test_get_info_extracts_title(self):
        html = """<html><body>
        <h1 class="rd-novel-title">Test Novel</h1>
        <span class="rd-author-name">Author One</span>
        <div class="rd-description-content">Test description</div>
        </body></html>"""

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_resp)

        source = ValvrareteamSource(client=mock_client)
        info = await source.get_info("https://valvrareteam.net/truyen/test-novel")

        assert info.title == "Test Novel"
        assert info.author == "Author One"
        assert info.description == "Test description"

    @pytest.mark.asyncio
    async def test_get_info_strips_status_suffix_from_title(self):
        html = """<html><body>
        <h1 class="rd-novel-title">Test Novel+Đang tiến hành</h1>
        <span class="rd-author-name">Author</span>
        <div class="rd-description-content">Desc</div>
        </body></html>"""

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_resp)

        source = ValvrareteamSource(client=mock_client)
        info = await source.get_info("https://valvrareteam.net/truyen/test-novel")

        assert info.title == "Test Novel"

    @pytest.mark.asyncio
    async def test_get_info_extracts_rd_stat_item_stats(self):
        html = """<html><body>
        <h1 class="rd-novel-title">Title</h1>
        <div class="rd-stat-item">
            <span class="rd-stat-value">100</span>
            <span class="rd-stat-label">Chương</span>
        </div>
        <div class="rd-stat-item">
            <span class="rd-stat-value">50000</span>
            <span class="rd-stat-label">Từ</span>
        </div>
        <div class="rd-stat-item">
            <span class="rd-stat-value">1234</span>
            <span class="rd-stat-label">Lượt xem</span>
        </div>
        </body></html>"""

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_resp)

        source = ValvrareteamSource(client=mock_client)
        info = await source.get_info("https://valvrareteam.net/truyen/test-novel")

        assert info.total_chapters == "100"
        assert info.word_count == "50000"
        assert info.views == "1234"

    @pytest.mark.asyncio
    async def test_get_info_uses_ssr_url_env(self, monkeypatch):
        """get_info() phải dùng VVR_SSR_URL env thay vì valvrareteam.net."""
        monkeypatch.setenv("VVR_SSR_URL", "custom-ssr.example.com")

        html = '<html><body><h1 class="rd-novel-title">Test</h1></body></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_resp)

        source = ValvrareteamSource(client=mock_client)
        await source.get_info("https://valvrareteam.net/truyen/test-novel")

        called_url = mock_client.get.call_args[0][0]
        assert "custom-ssr.example.com" in called_url
        assert "valvrareteam.net" not in called_url

    @pytest.mark.asyncio
    async def test_get_info_returns_unknown_title_when_not_found(self):
        html = "<html><body><p>Not a novel page</p></body></html>"

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_resp)

        source = ValvrareteamSource(client=mock_client)
        info = await source.get_info("https://valvrareteam.net/truyen/unknown")

        assert info.title == "Unknown Title"

    @pytest.mark.asyncio
    async def test_get_info_downloads_cover(self):
        html = '<html><body><h1 class="rd-novel-title">Title</h1><img class="rd-cover-image" src="https://cdn.example.com/cover.jpg"></body></html>'

        info_resp = MagicMock()
        info_resp.text = html
        info_resp.raise_for_status = MagicMock()

        cover_resp = MagicMock()
        cover_resp.content = b"fake-image-bytes"
        cover_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[info_resp, cover_resp])

        source = ValvrareteamSource(client=mock_client)
        info = await source.get_info("https://valvrareteam.net/truyen/test-novel")

        assert info.cover_url == "https://cdn.example.com/cover.jpg"
        assert info.cover_path is not None
        if info.cover_path and os.path.exists(info.cover_path):
            os.remove(info.cover_path)


class TestValvrareteamGetChapterList:
    def _make_mock_browser_with_html(self, html: str) -> MagicMock:
        """Helper: tạo mock browser trả về HTML cho Playwright scraping."""
        mock_browser = MagicMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value=html)
        mock_page.wait_for_selector = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        return mock_browser

    @pytest.mark.asyncio
    async def test_get_chapter_list_returns_volumes_and_chapters(self):
        html = """<html><body>
        <div class="module-container">
            <h3 class="module-title">Volume 1</h3>
            <div class="module-chapter-item chapter-mode-published">
                <a class="chapter-title-link" href="/truyen/test/chuong-1">Chương 1</a>
            </div>
            <div class="module-chapter-item chapter-mode-published">
                <a class="chapter-title-link" href="/truyen/test/chuong-2">Chương 2</a>
            </div>
        </div>
        </body></html>"""

        mock_browser = self._make_mock_browser_with_html(html)
        source = ValvrareteamSource(browser=mock_browser)
        result = await source.get_chapter_list("https://valvrareteam.net/truyen/test")

        assert len(result) >= 1
        assert result[0].volume == "Volume 1"
        assert len(result[0].chapters) == 2
        assert result[0].chapters[0].title == "Chương 1"
        assert "valvrareteam.net" in result[0].chapters[0].url

    @pytest.mark.asyncio
    async def test_get_chapter_list_skips_unpublished_chapters(self):
        html = """<html><body>
        <div class="module-container">
            <h3 class="module-title">Volume 1</h3>
            <div class="module-chapter-item chapter-mode-published">
                <a class="chapter-title-link" href="/truyen/test/chuong-1">Chương 1</a>
            </div>
            <div class="module-chapter-item chapter-mode-draft">
                <a class="chapter-title-link" href="/truyen/test/chuong-2">Chương 2 (nháp)</a>
            </div>
        </div>
        </body></html>"""

        mock_browser = self._make_mock_browser_with_html(html)
        source = ValvrareteamSource(browser=mock_browser)
        result = await source.get_chapter_list("https://valvrareteam.net/truyen/test")

        published_chapters = [ch for v in result for ch in v.chapters]
        chapter_titles = [ch.title for ch in published_chapters]
        assert "Chương 2 (nháp)" not in chapter_titles

    @pytest.mark.asyncio
    async def test_get_chapter_list_makes_urls_absolute(self):
        html = """<html><body>
        <div class="module-container">
            <h3 class="module-title">Vol 1</h3>
            <div class="module-chapter-item chapter-mode-published">
                <a class="chapter-title-link" href="/truyen/test/chuong-1">Ch 1</a>
            </div>
        </div>
        </body></html>"""

        mock_browser = self._make_mock_browser_with_html(html)
        source = ValvrareteamSource(browser=mock_browser)
        result = await source.get_chapter_list("https://valvrareteam.net/truyen/test")

        assert result[0].chapters[0].url.startswith("https://valvrareteam.net")

    @pytest.mark.asyncio
    async def test_get_chapter_list_raises_when_no_browser(self):
        source = ValvrareteamSource()
        with pytest.raises((RuntimeError, NotImplementedError)):
            await source.get_chapter_list("https://valvrareteam.net/truyen/test")


class TestValvrareteamGetContent:
    @pytest.mark.asyncio
    async def test_get_content_extracts_paragraphs(self):
        html = """<html><body>
        <div class="vvr-chapter-content">
            <p>Paragraph one.</p>
            <p>Paragraph two.</p>
        </div>
        </body></html>"""

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value=html)
        mock_page.wait_for_selector = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        source = ValvrareteamSource(browser=mock_browser)
        result = await source.get_content("https://valvrareteam.net/truyen/test/chuong-1")

        assert len(result) == 2
        texts = [item.data for item in result if item.type == "text"]
        assert "Paragraph one." in texts
        assert "Paragraph two." in texts

    @pytest.mark.asyncio
    async def test_get_content_extracts_images(self):
        html = """<html><body>
        <div class="vvr-chapter-content">
            <p>Some text.</p>
            <img src="https://cdn.example.com/image1.jpg" alt="illustration">
        </div>
        </body></html>"""

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value=html)
        mock_page.wait_for_selector = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        source = ValvrareteamSource(browser=mock_browser)
        result = await source.get_content("https://valvrareteam.net/truyen/test/chuong-1")

        image_items = [item for item in result if item.type == "image"]
        assert len(image_items) >= 1
        assert any(item.data == "https://cdn.example.com/image1.jpg" for item in image_items)

    @pytest.mark.asyncio
    async def test_get_content_raises_when_no_browser(self):
        source = ValvrareteamSource()
        with pytest.raises(RuntimeError, match="[Bb]rowser"):
            await source.get_content("https://valvrareteam.net/truyen/test/chuong-1")

    @pytest.mark.asyncio
    async def test_get_content_raises_when_content_empty(self):
        html = "<html><body><p>No chapter div here</p></body></html>"

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value=html)
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        source = ValvrareteamSource(browser=mock_browser)
        with pytest.raises(RuntimeError):
            await source.get_content("https://valvrareteam.net/truyen/test/chuong-1")
