"""
ValvrareteamSource — source adapter cho valvrareteam.net.

Extract từ scraper_core.py và tao_so_do_cay.py.
Logic crawl giữ nguyên hoàn toàn.
"""

import asyncio
import os
import re
import tempfile
from typing import Any, ClassVar
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import Browser

from ..models import ContentItem, StoryInfo
from ..utils import BASE_URL, HEADERS
from . import BaseSource, ChapterTreeItem, SearchResult, VolumeTreeItem


class ValvrareteamSource(BaseSource):
    base_urls: ClassVar = ["valvrareteam.net"]
    priority: ClassVar = 10
    name: ClassVar = "valvrareteam"
    requires_browser: ClassVar = True

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        browser: Browser | None = None,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True)
        self.browser = browser

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        return None

    async def get_info(self, url: str) -> StoryInfo:
        """Fetch story info từ VVR SSR endpoint."""
        ssr_url = os.getenv("VVR_SSR_URL", "val-ssr-2kzit.ondigitalocean.app")
        ssr_target = url.replace("valvrareteam.net", ssr_url)
        logger.debug(f"Fetching story info from: {ssr_target}")

        response = await self.client.get(ssr_target, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title_element = soup.select_one("h1.rd-novel-title")
        title = title_element.get_text(strip=True) if title_element else "Unknown Title"

        for status in ["+Đang tiến hành", "+Hoàn thành", "+Tạm ngưng"]:
            if status in title:
                title = title.replace(status, "").strip()

        author_elements = soup.select("span.rd-author-name")
        authors = [author.get_text(strip=True) for author in author_elements]
        author = ", ".join(authors) if authors else "Unknown Author"

        description_element = soup.select_one("div.rd-description-content")
        description = description_element.get_text(strip=True) if description_element else "No Description"

        genre_elements = soup.select(".rd-genre-tag")
        genres = [genre.get_text(strip=True) for genre in genre_elements]

        total_chapters = "Unknown"
        word_count = "Unknown"
        views = "-"

        stat_items = soup.select(".rd-stat-item")
        for item in stat_items:
            val_elem = item.select_one(".rd-stat-value")
            lab_elem = item.select_one(".rd-stat-label")
            if val_elem and lab_elem:
                val = val_elem.get_text(strip=True)
                lab = lab_elem.get_text(strip=True)
                if "Lượt xem" in lab:
                    views = val
                elif "Từ" in lab or "Số chữ" in lab:
                    word_count = val
                elif "Chương" in lab:
                    total_chapters = val

        if total_chapters == "Unknown" or word_count == "Unknown" or views == "-":
            legacy_stats = soup.select(".rd-stats-item")
            for item in legacy_stats:
                text = item.get_text(" ", strip=True)
                if "Chương" in text:
                    match = re.search(r"(\d+[\d.,]*)", text)
                    if match:
                        total_chapters = match.group(1)
                elif "Số chữ" in text or "Từ" in text:
                    match = re.search(r"(\d+[\d.,]*)", text)
                    if match:
                        word_count = match.group(1)
                elif "Lượt xem" in text:
                    match = re.search(r"(\d+[\d.,]*)", text)
                    if match:
                        views = match.group(1)

        if total_chapters == "Unknown" or word_count == "Unknown":
            for row in soup.select(".rd-info-row"):
                label_elem = row.select_one(".rd-info-label")
                value_elem = row.select_one(".rd-info-value")
                if label_elem and value_elem:
                    label_text = label_elem.get_text(strip=True)
                    value_text = value_elem.get_text(strip=True)
                    if "Số chữ" in label_text or "Từ" in label_text:
                        word_count = value_text
                    elif "Chương" in label_text:
                        total_chapters = value_text
                    elif "Lượt xem" in label_text:
                        views = value_text

        if total_chapters == "Unknown":
            chapter_count_overlay = soup.select_one(".rd-chapter-count-value")
            if chapter_count_overlay:
                total_chapters = chapter_count_overlay.get_text(strip=True)

        cover_path = None
        cover_url = None
        image_url_element = soup.select_one("img.rd-cover-image")
        if image_url_element:
            if "src" in image_url_element.attrs:
                cover_url = image_url_element["src"]
            elif "srcset" in image_url_element.attrs:
                cover_url = image_url_element["srcset"].split(",")[0].split(" ")[0]

        if cover_url:
            try:
                if cover_url.startswith("/"):
                    cover_url = f"{BASE_URL}{cover_url}"

                cover_resp = await self.client.get(cover_url, timeout=30.0)
                cover_resp.raise_for_status()

                _fd, cover_path = tempfile.mkstemp(suffix=".jpg", prefix="vvr_cover_")
                os.close(_fd)

                def save_cover(path: str, content: bytes) -> None:
                    with open(path, "wb") as f:
                        f.write(content)

                await asyncio.to_thread(save_cover, cover_path, cover_resp.content)
                logger.info(f"Đã tải ảnh bìa: {cover_path}")
            except Exception as e:
                logger.warning(f"Không thể tải ảnh bìa: {e}")
                if cover_path and os.path.exists(cover_path):
                    try:
                        os.remove(cover_path)
                    except OSError:
                        pass
                cover_path = None

        slug = url.rstrip("/").split("/")[-1]

        return StoryInfo(
            title=title,
            author=author,
            description=description,
            slug=slug,
            genres=genres,
            cover_path=cover_path,
            cover_url=cover_url,
            total_chapters=total_chapters,
            word_count=word_count,
            views=views,
        )

    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        """Get chapter list using Playwright browser."""
        if not self.browser:
            raise RuntimeError("Browser instance required for get_chapter_list()")

        context = await self.browser.new_context()
        html = ""
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            try:
                await page.wait_for_selector(".module-container", timeout=10000)
            except Exception:
                pass

            html = await page.content()
            await page.close()
        finally:
            await context.close()

        soup = BeautifulSoup(html, "html.parser")
        volumes: list[VolumeTreeItem] = []

        for container in soup.select("div.module-container"):
            volume_title_el = container.select_one("h3.module-title")
            volume_name = volume_title_el.get_text(strip=True) if volume_title_el else "Volume 1"

            chapters: list[ChapterTreeItem] = []
            for item in container.select("div.module-chapter-item.chapter-mode-published"):
                link = item.select_one("a.chapter-title-link")
                if not link:
                    continue

                title = link.get_text(strip=True)
                href = link.get("href", "")
                chapter_url = urljoin(BASE_URL, href) if href else ""
                chapters.append(ChapterTreeItem(title=title, url=chapter_url))

            if chapters:
                volumes.append(VolumeTreeItem(volume=volume_name, chapters=chapters))

        return volumes

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        """Placeholder — implement trong Task 3."""
        raise NotImplementedError("get_content() chưa implement — xem Task 3")
