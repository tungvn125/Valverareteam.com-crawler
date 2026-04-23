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
