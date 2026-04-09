"""
Tests for tao_so_do_cay.py - Chapter tree extraction utilities
"""

import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vvr_scraper.tao_so_do_cay import (
    get_chapter_tree,
    get_chapter_tree_folder,
    get_chapter_tree_list,
    get_chapters_by_volume_index,
)
from vvr_scraper.utils import HEADERS

# =============================================================================
# TESTS FOR get_chapter_tree
# =============================================================================


class TestGetChapterTree:
    """Tests for the get_chapter_tree function"""

    @pytest.mark.asyncio
    async def test_basic_chapter_extraction(self, tmp_path):
        """Test basic chapter tree extraction from HTML"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-1">Chương 1</a>
                </div>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-2">Chương 2</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "tree.txt")

        with patch("httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", output_file)

            assert os.path.exists(output_file)
            with open(output_file, encoding="utf-8") as f:
                content = f.read()

            assert "Volume 1" in content
            assert "Chương 1" in content
            assert "Chương 2" in content

    @pytest.mark.asyncio
    async def test_no_volumes_found(self):
        """Test handling when no volumes are found"""
        mock_html = "<html><body>No content</body></html>"

        with patch("httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            # Should return without error (no volumes = no output file created)
            await get_chapter_tree("https://example.com/story", "/tmp/test_no_vol.txt")

    @pytest.mark.asyncio
    async def test_volume_without_title(self, tmp_path):
        """Test handling volumes without titles"""
        mock_html = """
        <html>
            <div class="module-container">
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-1">Chương 1</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "tree.txt")

        with patch("httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", output_file)

            with open(output_file, encoding="utf-8") as f:
                content = f.read()

            assert "[Không có tiêu đề tập]" in content

    @pytest.mark.asyncio
    async def test_empty_volume(self, tmp_path):
        """Test handling volumes with no chapters"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Empty Volume</h3>
            </div>
        </html>
        """

        output_file = str(tmp_path / "tree.txt")

        with patch("httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", output_file)

            with open(output_file, encoding="utf-8") as f:
                content = f.read()

            assert "[Không có chương nào trong tập này]" in content


# =============================================================================
# TESTS FOR get_chapter_tree_folder
# =============================================================================


class TestGetChapterTreeFolder:
    """Tests for the get_chapter_tree_folder function"""

    @pytest.mark.asyncio
    async def test_sanitizes_volume_titles(self, tmp_path):
        """Test that volume titles are sanitized for folder names"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1: Special*Chars?</h3>
            </div>
        </html>
        """

        output_file = str(tmp_path / "tree.txt")

        with patch("httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree_folder("https://example.com/story", output_file)

            with open(output_file, encoding="utf-8") as f:
                content = f.read()

            # Special characters should be replaced with " -"
            assert "*" not in content
            assert "?" not in content
            assert ":" not in content

    @pytest.mark.asyncio
    async def test_multiple_volumes(self, tmp_path):
        """Test extraction of multiple volumes"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
            </div>
            <div class="module-container">
                <h3 class="module-title">Volume 2</h3>
            </div>
            <div class="module-container">
                <h3 class="module-title">Volume 3</h3>
            </div>
        </html>
        """

        output_file = str(tmp_path / "tree.txt")

        with patch("httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree_folder("https://example.com/story", output_file)

            with open(output_file, encoding="utf-8") as f:
                content = f.read()

            assert "Volume 1" in content
            assert "Volume 2" in content
            assert "Volume 3" in content


# =============================================================================
# TESTS FOR get_chapter_tree_list
# =============================================================================


class TestGetChapterTreeList:
    """Tests for the get_chapter_tree_list function (uses Playwright)"""

    def _setup_mock_playwright(self, mock_playwright, mock_html):
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value=mock_html)

        mock_p_instance = MagicMock()
        mock_p_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
        mock_browser.__aexit__ = AsyncMock(return_value=None)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_playwright.return_value.__aenter__.return_value = mock_p_instance
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)
        return mock_browser, mock_context, mock_page

    @pytest.mark.asyncio
    async def test_creates_json_output(self, tmp_path):
        """Test that JSON output file is created with correct structure"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-1">Chương 1</a>
                </div>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-2">Chương 2</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "chapters.json")

        with patch("vvr_scraper.tao_so_do_cay.async_playwright") as mock_playwright:
            self._setup_mock_playwright(mock_playwright, mock_html)
            result = await get_chapter_tree_list("https://example.com/story", output_file)

            assert os.path.exists(output_file)
            with open(output_file, encoding="utf-8") as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]["volume"] == "Volume 1"
            assert len(data[0]["chapters"]) == 2
            assert data[0]["chapters"][0]["title"] == "Chương 1"
            assert data[0]["chapters"][0]["url"] == "/chap-1"

    @pytest.mark.asyncio
    async def test_crawls_both_published_and_protected_chapters(self, tmp_path):
        """Test that both published and protected chapters are crawled"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
                <div class="module-chapter-item chapter-item-animated chapter-mode-published">
                    <a class="chapter-title-link" href="/chap-published">Published</a>
                </div>
                <div class="module-chapter-item chapter-item-animated chapter-mode-protected">
                    <a class="chapter-title-link" href="/chap-protected">Protected</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "chapters_mixed.json")

        with patch("vvr_scraper.tao_so_do_cay.async_playwright") as mock_playwright:
            self._setup_mock_playwright(mock_playwright, mock_html)
            result = await get_chapter_tree_list("https://example.com/story", output_file)

            assert len(result[0]["chapters"]) == 2
            urls = [c["url"] for c in result[0]["chapters"]]
            assert "/chap-published" in urls
            assert "/chap-protected" in urls

    @pytest.mark.asyncio
    async def test_uses_session_state(self, tmp_path):
        """Test that session_state is passed to Playwright context"""
        mock_html = (
            "<html><div class='module-chapter-item'><a class='chapter-title-link' href='/c1'>C1</a></div></html>"
        )
        output_file = str(tmp_path / "session_test.json")
        session_state = {"cookies": [{"name": "test", "value": "val"}]}

        with patch("vvr_scraper.tao_so_do_cay.async_playwright") as mock_playwright:
            mock_browser, _, _ = self._setup_mock_playwright(mock_playwright, mock_html)
            await get_chapter_tree_list("https://example.com/story", output_file, session_state=session_state)
            mock_browser.new_context.assert_called_with(
                storage_state=session_state, user_agent=HEADERS.get("User-Agent")
            )

    @pytest.mark.asyncio
    async def test_includes_minh_hoa_chapters(self, tmp_path):
        """Test that 'minh-hoa' (illustration) chapters are NOT filtered out"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-1">Chương 1</a>
                </div>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-2-minh-hoa">Minh Họa</a>
                </div>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/chap-3">Chương 3</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "chapters_filter.json")

        with patch("vvr_scraper.tao_so_do_cay.async_playwright") as mock_playwright:
            self._setup_mock_playwright(mock_playwright, mock_html)
            result = await get_chapter_tree_list("https://example.com/story", output_file)

            assert len(result[0]["chapters"]) == 3
            urls = [c["url"] for c in result[0]["chapters"]]
            assert "/chap-2-minh-hoa" in urls

    @pytest.mark.asyncio
    async def test_detects_locked_chapters(self, tmp_path):
        """Test that locked chapters are correctly detected"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
                <div class="module-chapter-item chapter-mode-published">
                    <a class="chapter-title-link" href="/chap-1">Chương 1</a>
                </div>
                <div class="module-chapter-item locked-chapter">
                    <a class="chapter-title-link" href="/chap-2">Chương 2</a>
                </div>
                <div class="module-chapter-item chapter-mode-protected">
                    <a class="chapter-title-link" href="/chap-3">Chương 3</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "chapters_locked.json")

        with patch("vvr_scraper.tao_so_do_cay.async_playwright") as mock_playwright:
            self._setup_mock_playwright(mock_playwright, mock_html)
            result = await get_chapter_tree_list("https://example.com/story", output_file)

            chapters = result[0]["chapters"]
            assert chapters[0]["locked"] == False
            assert chapters[1]["locked"] == True
            assert chapters[2]["locked"] == True

    @pytest.mark.asyncio
    async def test_handles_missing_href(self, tmp_path):
        """Test handling of chapters without href attribute"""
        mock_html = """
        <html>
            <div class="module-container">
                <h3 class="module-title">Volume 1</h3>
                <div class="module-chapter-item">
                    <a class="chapter-title-link">No href</a>
                </div>
                <div class="module-chapter-item">
                    <a class="chapter-title-link" href="/valid-chap">Valid</a>
                </div>
            </div>
        </html>
        """

        output_file = str(tmp_path / "chapters_href.json")

        with patch("vvr_scraper.tao_so_do_cay.async_playwright") as mock_playwright:
            self._setup_mock_playwright(mock_playwright, mock_html)
            result = await get_chapter_tree_list("https://example.com/story", output_file)

            assert len(result[0]["chapters"]) == 1
            assert result[0]["chapters"][0]["url"] == "/valid-chap"


# =============================================================================
# TESTS FOR get_chapters_by_volume_index
# =============================================================================


class TestGetChaptersByVolumeIndex:
    """Tests for the get_chapters_by_volume_index function"""

    def test_valid_index(self, tmp_path):
        """Test getting chapters with valid index"""
        test_data = [
            {"volume": "Volume 1", "chapters": [{"title": "C1", "url": "/chap-1"}, {"title": "C2", "url": "/chap-2"}]},
            {"volume": "Volume 2", "chapters": [{"title": "C3", "url": "/chap-3"}, {"title": "C4", "url": "/chap-4"}]},
        ]

        json_file = str(tmp_path / "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f, ensure_ascii=False)

        result = get_chapters_by_volume_index(json_file, 0)
        assert result == [{"title": "C1", "url": "/chap-1"}, {"title": "C2", "url": "/chap-2"}]

    def test_second_volume(self, tmp_path):
        """Test getting chapters from second volume"""
        test_data = [
            {"volume": "Volume 1", "chapters": [{"title": "C1", "url": "/chap-1"}, {"title": "C2", "url": "/chap-2"}]},
            {"volume": "Volume 2", "chapters": [{"title": "C3", "url": "/chap-3"}, {"title": "C4", "url": "/chap-4"}]},
        ]

        json_file = str(tmp_path / "test.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f, ensure_ascii=False)

        result = get_chapters_by_volume_index(json_file, 1)
        assert result == [{"title": "C3", "url": "/chap-3"}, {"title": "C4", "url": "/chap-4"}]

    def test_invalid_index_negative(self):
        """Test handling of negative index"""
        test_data = [{"volume": "Volume 1", "chapters": ["/chap-1"]}]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            json_file = f.name

        try:
            result = get_chapters_by_volume_index(json_file, -1)
            assert result == []
        finally:
            os.unlink(json_file)

    def test_invalid_index_out_of_range(self):
        """Test handling of index out of range"""
        test_data = [{"volume": "Volume 1", "chapters": ["/chap-1"]}]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            json_file = f.name

        try:
            result = get_chapters_by_volume_index(json_file, 100)
            assert result == []
        finally:
            os.unlink(json_file)

    def test_nonexistent_file(self):
        """Test handling of nonexistent file"""
        result = get_chapters_by_volume_index("/nonexistent/file.json", 0)
        assert result == []


# =============================================================================
# TESTS FOR HEADERS CONFIGURATION
# =============================================================================


class TestTaoSoDoCayHeaders:
    """Tests for HEADERS configuration in tao_so_do_cay"""

    def test_headers_contains_required_fields(self):
        """Test that HEADERS contains all required fields"""
        assert "User-Agent" in HEADERS
        assert "Accept" in HEADERS
        assert "Accept-Language" in HEADERS

    def test_user_agent_is_browser_like(self):
        """Test that User-Agent looks like a real browser"""
        ua = HEADERS["User-Agent"]
        assert "Mozilla" in ua
        assert "Chrome" in ua
