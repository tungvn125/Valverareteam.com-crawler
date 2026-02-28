"""
Tests for tao_so_do_cay.py - Chapter tree extraction utilities
"""
import pytest
import os
import sys
import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tao_so_do_cay import (
    get_chapter_tree,
    get_chapter_tree_folder,
    get_chapter_tree_list,
    get_chapters_by_volume_index,
    HEADERS
)


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

        with patch('httpx.AsyncClient') as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", output_file)

            assert os.path.exists(output_file)
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()

            assert 'Volume 1' in content
            assert 'Chương 1' in content
            assert 'Chương 2' in content

    @pytest.mark.asyncio
    async def test_no_volumes_found(self, capsys):
        """Test handling when no volumes are found"""
        mock_html = "<html><body>No content</body></html>"

        with patch('httpx.AsyncClient') as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", "/tmp/test.txt")

            captured = capsys.readouterr()
            assert "Không tìm thấy container nào" in captured.out

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

        with patch('httpx.AsyncClient') as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", output_file)

            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()

            assert '[Không có tiêu đề tập]' in content

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

        with patch('httpx.AsyncClient') as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree("https://example.com/story", output_file)

            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()

            assert '[Không có chương nào trong tập này]' in content


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

        with patch('httpx.AsyncClient') as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree_folder("https://example.com/story", output_file)

            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Special characters should be replaced with " -"
            assert '*' not in content
            assert '?' not in content
            assert ':' not in content

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

        with patch('httpx.AsyncClient') as MockClient:
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()

            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            await get_chapter_tree_folder("https://example.com/story", output_file)

            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()

            assert 'Volume 1' in content
            assert 'Volume 2' in content
            assert 'Volume 3' in content


# =============================================================================
# TESTS FOR get_chapter_tree_list
# =============================================================================

class TestGetChapterTreeList:
    """Tests for the get_chapter_tree_list function (uses Playwright)"""

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

        # Mock Playwright
        with patch('tao_so_do_cay.async_playwright') as mock_playwright:
            mock_browser = AsyncMock()
            mock_page = AsyncMock()
            mock_page.content = AsyncMock(return_value=mock_html)

            mock_p_instance = MagicMock()
            mock_p_instance.chromium.launch = AsyncMock(return_value=mock_browser)

            mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
            mock_browser.__aexit__ = AsyncMock(return_value=None)
            mock_browser.new_page = AsyncMock(return_value=mock_page)

            mock_playwright.return_value.__aenter__.return_value = mock_p_instance
            mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await get_chapter_tree_list("https://example.com/story", output_file)

            assert os.path.exists(output_file)
            with open(output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]['volume'] == 'Volume 1'
            assert len(data[0]['chapters']) == 2

    @pytest.mark.asyncio
    async def test_filters_minh_hoa_chapters(self, tmp_path):
        """Test that 'minh-hoa' (illustration) chapters are filtered out"""
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

        output_file = str(tmp_path / "chapters.json")

        with patch('tao_so_do_cay.async_playwright') as mock_playwright:
            mock_browser = AsyncMock()
            mock_page = AsyncMock()
            mock_page.content = AsyncMock(return_value=mock_html)

            mock_p_instance = MagicMock()
            mock_p_instance.chromium.launch = AsyncMock(return_value=mock_browser)

            mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
            mock_browser.__aexit__ = AsyncMock(return_value=None)
            mock_browser.new_page = AsyncMock(return_value=mock_page)

            mock_playwright.return_value.__aenter__.return_value = mock_p_instance
            mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await get_chapter_tree_list("https://example.com/story", output_file)

            # Should only have chap-1 and chap-3, not minh-hoa
            assert len(result[0]['chapters']) == 2
            assert '/chap-2-minh-hoa' not in result[0]['chapters']

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

        output_file = str(tmp_path / "chapters.json")

        with patch('tao_so_do_cay.async_playwright') as mock_playwright:
            mock_browser = AsyncMock()
            mock_page = AsyncMock()
            mock_page.content = AsyncMock(return_value=mock_html)

            mock_p_instance = MagicMock()
            mock_p_instance.chromium.launch = AsyncMock(return_value=mock_browser)

            mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
            mock_browser.__aexit__ = AsyncMock(return_value=None)
            mock_browser.new_page = AsyncMock(return_value=mock_page)

            mock_playwright.return_value.__aenter__.return_value = mock_p_instance
            mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await get_chapter_tree_list("https://example.com/story", output_file)

            # Should only have the valid chapter
            assert len(result[0]['chapters']) == 1
            assert '/valid-chap' in result[0]['chapters']


# =============================================================================
# TESTS FOR get_chapters_by_volume_index
# =============================================================================

class TestGetChaptersByVolumeIndex:
    """Tests for the get_chapters_by_volume_index function"""

    def test_valid_index(self, tmp_path):
        """Test getting chapters with valid index"""
        # Create test JSON file
        test_data = [
            {"volume": "Volume 1", "chapters": ["/chap-1", "/chap-2"]},
            {"volume": "Volume 2", "chapters": ["/chap-3", "/chap-4"]},
        ]

        json_file = str(tmp_path / "test.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False)

        result = get_chapters_by_volume_index(json_file, 0)

        assert result == ["/chap-1", "/chap-2"]

    def test_second_volume(self, tmp_path):
        """Test getting chapters from second volume"""
        test_data = [
            {"volume": "Volume 1", "chapters": ["/chap-1", "/chap-2"]},
            {"volume": "Volume 2", "chapters": ["/chap-3", "/chap-4"]},
        ]

        json_file = str(tmp_path / "test.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False)

        result = get_chapters_by_volume_index(json_file, 1)

        assert result == ["/chap-3", "/chap-4"]

    def test_invalid_index_negative(self, capsys):
        """Test handling of negative index"""
        test_data = [{"volume": "Volume 1", "chapters": ["/chap-1"]}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            json_file = f.name

        try:
            result = get_chapters_by_volume_index(json_file, -1)
            assert result == []

            captured = capsys.readouterr()
            assert "không hợp lệ" in captured.out
        finally:
            os.unlink(json_file)

    def test_invalid_index_out_of_range(self, capsys):
        """Test handling of index out of range"""
        test_data = [{"volume": "Volume 1", "chapters": ["/chap-1"]}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            json_file = f.name

        try:
            result = get_chapters_by_volume_index(json_file, 100)
            assert result == []

            captured = capsys.readouterr()
            assert "không hợp lệ" in captured.out
        finally:
            os.unlink(json_file)

    def test_nonexistent_file(self, capsys):
        """Test handling of nonexistent file"""
        result = get_chapters_by_volume_index("/nonexistent/file.json", 0)

        assert result == []
        captured = capsys.readouterr()
        assert "Đã xảy ra lỗi" in captured.out


# =============================================================================
# TESTS FOR HEADERS CONFIGURATION
# =============================================================================

class TestTaoSoDoCayHeaders:
    """Tests for HEADERS configuration in tao_so_do_cay"""

    def test_headers_contains_required_fields(self):
        """Test that HEADERS contains all required fields"""
        assert 'User-Agent' in HEADERS
        assert 'Accept' in HEADERS
        assert 'Accept-Language' in HEADERS

    def test_user_agent_is_browser_like(self):
        """Test that User-Agent looks like a real browser"""
        ua = HEADERS['User-Agent']
        assert 'Mozilla' in ua
        assert 'Chrome' in ua
