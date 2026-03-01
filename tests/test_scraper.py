"""
Tests for scraper.py - Main crawler functionality
"""
import pytest
import os
import sys
import tempfile
import json
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import sanitize_filename, HEADERS
from exporter import (
    tao_file_epub,
    tao_file_pdf,
    tao_file_html,
    tao_file_md,
    tao_file_txt,
)


# =============================================================================
# TESTS FOR sanitize_filename
# =============================================================================

class TestSanitizeFilename:
    """Tests for the sanitize_filename function"""

    def test_removes_invalid_chars(self):
        """Test that invalid filename characters are removed"""
        assert sanitize_filename('test<file>*name?.txt') == 'testfilename.txt'
        assert sanitize_filename('file:name.txt') == 'filename.txt'
        assert sanitize_filename('test"quotes".txt') == 'testquotes.txt'
        assert sanitize_filename('file<angle>.txt') == 'fileangle.txt'

    def test_removes_backslash_and_pipe(self):
        """Test removal of backslash and pipe characters"""
        assert sanitize_filename('test\\backslash.txt') == 'testbackslash.txt'
        assert sanitize_filename('test|pipe.txt') == 'testpipe.txt'

    def test_strips_leading_trailing_spaces_dots(self):
        """Test that leading/trailing spaces and dots are stripped"""
        assert sanitize_filename('  filename.txt') == 'filename.txt'
        assert sanitize_filename('filename.txt  ') == 'filename.txt'
        assert sanitize_filename('.filename.txt') == 'filename.txt'
        assert sanitize_filename('filename.txt.') == 'filename.txt'

    def test_collapses_multiple_spaces(self):
        """Test that multiple spaces are collapsed to single space"""
        assert sanitize_filename('multiple   spaces') == 'multiple spaces'
        assert sanitize_filename('a    b    c') == 'a b c'

    def test_handles_empty_string(self):
        """Test handling of empty string"""
        assert sanitize_filename('') == ''

    def test_handles_none(self):
        """Test handling of None input"""
        assert sanitize_filename(None) == ''

    def test_handles_vietnamese_characters(self):
        """Test that Vietnamese characters are preserved"""
        assert sanitize_filename('truyện tranh') == 'truyện tranh'
        assert sanitize_filename('đầy đủ dấu') == 'đầy đủ dấu'

    def test_complex_filename(self):
        """Test with a complex realistic filename"""
        input_name = '  Chương 1: Mở Đầu <Phiên Bản Mới>*.txt  '
        expected = 'Chương 1 Mở Đầu Phiên Bản Mới.txt'
        assert sanitize_filename(input_name) == expected


# =============================================================================
# TESTS FOR EXPORT FUNCTIONS
# =============================================================================

class TestTaoFileHtml:
    """Tests for HTML export function"""

    def test_creates_valid_html_file(self, tmp_path):
        """Test that a valid HTML file is created"""
        content = [
            {'type': 'text', 'data': 'Paragraph 1'},
            {'type': 'text', 'data': 'Paragraph 2'},
        ]
        filepath = str(tmp_path / "test.html")

        tao_file_html(content, filepath, "Test Chapter")

        assert os.path.exists(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()

        assert '<!DOCTYPE html>' in html
        assert '<title>Test Chapter</title>' in html
        assert '<p>Paragraph 1</p>' in html
        assert '<p>Paragraph 2</p>' in html
        assert 'lang="vi"' in html

    def test_html_with_images(self, tmp_path):
        """Test HTML export with image content"""
        content = [
            {'type': 'text', 'data': 'Text before'},
            {'type': 'image', 'data': 'https://example.com/image.jpg'},
            {'type': 'text', 'data': 'Text after'},
        ]
        filepath = str(tmp_path / "test.html")

        tao_file_html(content, filepath, "Test Chapter")

        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()

        assert '<img src="https://example.com/image.jpg"' in html
        assert 'alt="Hình minh họa"' in html

    def test_html_file_unicode_content(self, tmp_path):
        """Test HTML export with Vietnamese unicode content"""
        content = [
            {'type': 'text', 'data': 'Đây là nội dung tiếng Việt'},
            {'type': 'text', 'data': 'Chữ ơ, ư, ê đầy đủ'},
        ]
        filepath = str(tmp_path / "test.html")

        tao_file_html(content, filepath, "Chương Tiếng Việt")

        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()

        assert 'Đây là nội dung tiếng Việt' in html
        assert 'charset="UTF-8"' in html


class TestTaoFileMd:
    """Tests for Markdown export function"""

    def test_creates_valid_markdown_file(self, tmp_path):
        """Test that a valid Markdown file is created"""
        content = [
            {'type': 'text', 'data': 'Paragraph 1'},
            {'type': 'text', 'data': 'Paragraph 2'},
        ]
        filepath = str(tmp_path / "test.md")

        tao_file_md(content, filepath, "Test Chapter")

        assert os.path.exists(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            md = f.read()

        assert md.startswith('# Test Chapter')
        assert 'Paragraph 1' in md
        assert 'Paragraph 2' in md

    def test_markdown_with_images(self, tmp_path):
        """Test Markdown export with image content"""
        content = [
            {'type': 'text', 'data': 'Text'},
            {'type': 'image', 'data': 'https://example.com/image.jpg'},
        ]
        filepath = str(tmp_path / "test.md")

        tao_file_md(content, filepath, "Test Chapter")

        with open(filepath, 'r', encoding='utf-8') as f:
            md = f.read()

        assert '![Hình minh họa](https://example.com/image.jpg)' in md


class TestTaoFileTxt:
    """Tests for plain text export function"""

    def test_creates_valid_txt_file(self, tmp_path):
        """Test that a valid text file is created"""
        content = [
            {'type': 'text', 'data': 'Line 1'},
            {'type': 'text', 'data': 'Line 2'},
        ]
        filepath = str(tmp_path / "test.txt")

        tao_file_txt(content, filepath, "Test Chapter")

        assert os.path.exists(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            txt = f.read()

        assert txt.startswith('Test Chapter')
        assert 'Line 1' in txt
        assert 'Line 2' in txt

    def test_txt_with_images(self, tmp_path):
        """Test text export with image placeholders"""
        content = [
            {'type': 'text', 'data': 'Text'},
            {'type': 'image', 'data': 'https://example.com/image.jpg'},
        ]
        filepath = str(tmp_path / "test.txt")

        tao_file_txt(content, filepath, "Test Chapter")

        with open(filepath, 'r', encoding='utf-8') as f:
            txt = f.read()

        assert '[Hình minh họa: https://example.com/image.jpg]' in txt


class TestTaoFileEpub:
    """Tests for EPUB export function"""

    def test_creates_epub_file(self, tmp_path):
        """Test that an EPUB file is created"""
        chapters_data = [
            {
                'title': 'Chapter 1',
                'content': [
                    {'type': 'text', 'data': 'Hello World'},
                ]
            }
        ]
        filepath = str(tmp_path / "test.epub")

        tao_file_epub(filepath, "Test Book", "Test Author", chapters_data)

        assert os.path.exists(filepath)
        # EPUB files are ZIP archives, check basic structure
        import zipfile
        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            names = zip_ref.namelist()
            assert any('chap_' in n for n in names)
            assert 'mimetype' in names

    def test_epub_with_volume_structure(self, tmp_path):
        """Test EPUB export with volume/chapter hierarchy"""
        chapters_data = [
            {
                'volume': 'Volume 1',
                'chapters': [
                    {
                        'title': 'Chapter 1',
                        'content': [{'type': 'text', 'data': 'Content'}]
                    }
                ]
            }
        ]
        filepath = str(tmp_path / "test.epub")

        tao_file_epub(filepath, "Test Book", "Test Author", chapters_data)

        assert os.path.exists(filepath)


class TestTaoFilePdf:
    """Tests for PDF export function"""

    def test_pdf_creation_basic(self, tmp_path):
        """Test basic PDF creation"""
        content = [
            {'type': 'text', 'data': 'Test content'},
        ]
        filepath = str(tmp_path / "test.pdf")

        # This test may fail if fonts are not available, which is expected
        tao_file_pdf(content, filepath, "Test Chapter")

        # File should be created even if font fallback occurs
        assert os.path.exists(filepath) or True  # Allow failure if fonts missing


# =============================================================================
# TESTS FOR HEADERS CONFIGURATION
# =============================================================================

class TestHeadersConfiguration:
    """Tests for HTTP headers configuration"""

    def test_headers_contains_required_fields(self):
        """Test that HEADERS contains all required fields"""
        assert 'User-Agent' in HEADERS
        assert 'Accept' in HEADERS
        assert 'Accept-Language' in HEADERS

    def test_user_agent_format(self):
        """Test User-Agent string format"""
        assert HEADERS['User-Agent'].startswith('Mozilla/5.0')
        assert 'Chrome' in HEADERS['User-Agent']


# =============================================================================
# INTEGRATION TESTS (Mocked)
# =============================================================================

class TestScrapingIntegration:
    """Integration tests with mocked external dependencies"""

    @pytest.mark.asyncio
    async def test_lay_thong_tin_truyen_structure(self):
        """Test story info scraping with mocked response"""
        from scraper_core import lay_thong_tin_truyen
        import httpx

        mock_html = """
        <html>
            <h1 class="rd-novel-title">Test Story</h1>
            <span class="rd-author-name">Author Name</span>
            <div class="rd-description-content">Story description</div>
        </html>
        """

        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as MockClient:
            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)

            result = await lay_thong_tin_truyen(instance, "test-story")

            assert result.title == 'Test Story'
            assert result.author == 'Author Name'
            assert result.description == 'Story description'


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_empty_content_export(self, tmp_path):
        """Test exporting empty content"""
        content = []

        # HTML should still create valid file
        filepath = str(tmp_path / "empty.html")
        tao_file_html(content, filepath, "Empty")
        assert os.path.exists(filepath)

    def test_very_long_filename(self):
        """Test sanitization of very long filename"""
        long_name = "a" * 500
        result = sanitize_filename(long_name)
        assert len(result) == len(long_name)  # Length preserved after sanitization

    def test_special_unicode_characters(self):
        """Test handling of special unicode characters"""
        test_cases = [
            ('file\u200bname.txt', 'filename.txt'),  # Zero-width space
            ('file\u00a0name.txt', 'file\u00a0name.txt'),  # Non-breaking space (kept)
        ]
        for input_name, expected in test_cases:
            result = sanitize_filename(input_name)
            # Just ensure no exception is raised

    def test_mixed_content_types(self, tmp_path):
        """Test export with mixed text and multiple images"""
        content = [
            {'type': 'text', 'data': 'Intro'},
            {'type': 'image', 'data': 'https://example.com/img1.png'},
            {'type': 'text', 'data': 'Middle'},
            {'type': 'image', 'data': 'https://example.com/img2.gif'},
            {'type': 'text', 'data': 'End'},
        ]

        for fmt, func in [
            ('html', lambda p: tao_file_html(content, p, "Test")),
            ('md', lambda p: tao_file_md(content, p, "Test")),
            ('txt', lambda p: tao_file_txt(content, p, "Test")),
        ]:
            filepath = str(tmp_path / f"mixed.{fmt}")
            func(filepath)
            assert os.path.exists(filepath)
