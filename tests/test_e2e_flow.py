"""
End-to-end integration tests: Scrape -> Export -> Verify

These tests perform real HTTP requests and file generation,
so they are skipped on CI to avoid WAF blocks and API failures.
Run manually on dev machine with: pytest tests/test_e2e_flow.py -v
"""

import os
import zipfile

import pytest

from vvr_scraper.exporter import (
    tao_file_epub,
    tao_file_html,
    tao_file_md,
    tao_file_txt,
)
from vvr_scraper.scraper_core import lay_chuong_httpx
from vvr_scraper.utils import HEADERS

TEST_URL = (
    "https://valvrareteam.net/truyen/bi-mat-cua-phu-thuy-tinh-lang-4b74a318/chuong/mo-dau-hac-long-nui-worgan-4b74a38a"
)
TEST_TITLE = "Mở Đầu Hắc Long Nui Worgan"
TEST_STORY_SLUG = "bi-mat-cua-phu-thuy-tinh-lang-4b74a318"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("RUN_E2E") != "1",
    reason="Requires real HTTP to Valvrareteam and explicit RUN_E2E=1 opt-in",
)
class TestScrapeToExportFlow:
    """Test the full flow: scrape chapter -> export to various formats -> verify output"""

    @pytest.fixture(autouse=True)
    async def setup(self, tmp_path):
        """Scrape chapter once, use for all export tests"""
        import httpx

        self.client = httpx.AsyncClient(headers=HEADERS, timeout=60.0)
        self.content = await lay_chuong_httpx(self.client, TEST_URL)
        self.tmp_path = tmp_path
        self.chapter_title = TEST_TITLE

        yield

        await self.client.aclose()

    async def test_scraped_content_not_empty(self):
        """Verify we actually got content from the scrape"""
        assert self.content is not None, "Scraped content is None - site may be down or blocked"
        assert len(self.content) > 0, "Scraped content is empty"

        text_items = [item for item in self.content if item.type == "text"]
        assert len(text_items) > 0, "No text items found in scraped content"

        full_text = " ".join(item.data for item in text_items)
        assert len(full_text) > 100, f"Scraped text too short ({len(full_text)} chars) - parsing may have failed"

    async def test_export_to_html(self):
        """Scrape -> Export HTML -> Verify file exists and has content"""
        filepath = str(self.tmp_path / "test_chapter.html")

        await tao_file_html(self.content, filepath, self.chapter_title)

        assert os.path.exists(filepath), f"HTML file not created at {filepath}"

        with open(filepath, encoding="utf-8") as f:
            html = f.read()

        assert "<!DOCTYPE html>" in html or "<html" in html
        assert self.chapter_title in html
        assert len(html) > 500, "HTML content too short"

    async def test_export_to_md(self):
        """Scrape -> Export Markdown -> Verify file exists and has content"""
        filepath = str(self.tmp_path / "test_chapter.md")

        await tao_file_md(self.content, filepath, self.chapter_title)

        assert os.path.exists(filepath), f"MD file not created at {filepath}"

        with open(filepath, encoding="utf-8") as f:
            md = f.read()

        assert md.startswith(f"# {self.chapter_title}")
        assert len(md) > 100, "Markdown content too short"

    async def test_export_to_txt(self):
        """Scrape -> Export TXT -> Verify file exists and has content"""
        filepath = str(self.tmp_path / "test_chapter.txt")

        await tao_file_txt(self.content, filepath, self.chapter_title)

        assert os.path.exists(filepath), f"TXT file not created at {filepath}"

        with open(filepath, encoding="utf-8") as f:
            txt = f.read()

        assert txt.startswith(self.chapter_title)
        assert len(txt) > 100, "TXT content too short"

    async def test_export_to_epub(self):
        """Scrape -> Export EPUB -> Verify file exists and has valid EPUB structure"""
        chapters_data = [
            {
                "title": self.chapter_title,
                "content": self.content,
            }
        ]
        filepath = str(self.tmp_path / "test_chapter.epub")

        await tao_file_epub(
            filepath,
            " Bí Mật Của Phù Thủy Tinh Lăng",
            "Unknown Author",
            chapters_data,
            genres=["Fantasy", "Adventure"],
        )

        assert os.path.exists(filepath), f"EPUB file not created at {filepath}"
        assert os.path.getsize(filepath) > 5000, "EPUB file too small - may be corrupted"

        with zipfile.ZipFile(filepath, "r") as zip_ref:
            names = zip_ref.namelist()
            assert "mimetype" in names, "Missing mimetype in EPUB"
            assert any("chap" in n or "chapter" in n.lower() for n in names), "Missing chapter content in EPUB"

    async def test_content_integrity(self):
        """Verify exported content matches scraped content (text preserved)"""
        text_items = [item for item in self.content if item.type == "text"]

        md_path = str(self.tmp_path / "integrity.md")
        await tao_file_md(self.content, md_path, self.chapter_title)

        with open(md_path, encoding="utf-8") as f:
            md_content = f.read()

        for text_item in text_items[:3]:
            assert text_item.data in md_content, f"Text '{text_item.data[:50]}...' not found in exported MD"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("RUN_E2E") != "1",
    reason="Requires real HTTP to Valvrareteam and explicit RUN_E2E=1 opt-in",
)
class TestStoryInfoScrape:
    """Test scraping story metadata"""

    async def test_story_info_scraping(self):
        """
        Scrape story info page via Playwright-based scrape (since SSR doesn't render it).

        Note: lay_thong_tin_truyen uses direct httpx which may be blocked by WAF.
        This test verifies the function works when SSR proxy IS available for that page.
        Currently SKIPPED because SSR doesn't server-render story info page content.
        """
        pytest.skip("SSR proxy does not render story info page content, only chapter pages")
