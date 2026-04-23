import asyncio
import re

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Browser
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..models import ContentItem, StoryInfo
from ..utils import HEADERS
from . import BaseSource, ChapterTreeItem, SearchResult, VolumeTreeItem

_HAKO_CHAPTER_RE = re.compile(r"/truyen/\d+-[^/]+/c\d+-")


class LnHakoSource(BaseSource):
    base_urls = ["ln.hako.vn"]

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        return f"https://ln.hako.vn/truyen/{slug}"

    def __init__(self, client: httpx.AsyncClient | None = None, browser: Browser | None = None):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0)
        self.browser = browser

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def search(self, query: str) -> list[SearchResult]:
        url = f"https://ln.hako.vn/tim-kiem?keywords={query}"
        resp = await self.client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for div in soup.find_all("div", class_="thumb_attr series-title"):
            a = div.find("a")
            if not a or not a.get("href"):
                continue
            href = a.get("href")
            if "/ai-dich/" in href:
                continue
            results.append(SearchResult(title=a.text.strip(), url="https://ln.hako.vn" + href))
        return results

    async def get_info(self, url: str) -> StoryInfo:
        resp = await self.client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title_elem = soup.find("span", class_="series-name") or soup.find("h1", class_="series-name")
        title = title_elem.find("a").text.strip() if title_elem else "Unknown"

        author_elem = soup.find("a", href=lambda x: x and "/tac-gia/" in x)
        author = author_elem.text.strip() if author_elem else "Unknown"

        description_elem = soup.select_one("div.summary-content")
        description = description_elem.text.strip() if description_elem else "No description"

        cover_url = None

        og_image = soup.select_one("meta[property='og:image']")
        if og_image and og_image.get("content"):
            cover_url = og_image.get("content")

        if not cover_url:
            cover_img = soup.select_one(".series-cover .content.img-in-ratio") or soup.find(
                "div", class_="series-cover"
            )
            if cover_img and cover_img.get("style"):
                url_match = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", cover_img["style"])
                cover_url = url_match.group(1) if url_match else None

        genres = [a.text.strip() for a in soup.select("div.series-gernes a")]

        # Extract stats from <div class="statistic-item"> ... <div class="statistic-value">...</div>
        total_chapters = "Unknown"
        word_count = "Unknown"
        views = "-"
        stat_items = soup.find_all("div", class_="statistic-item")
        for item in stat_items:
            name_elem = item.find("div", class_="statistic-name")
            value_elem = item.find("div", class_="statistic-value")
            if name_elem and value_elem:
                name = name_elem.text.strip()
                value = value_elem.text.strip()
                if "Số từ" in name:
                    word_count = value
                elif "Lượt xem" in name:
                    views = value

        # Total chapters from chapter link count
        chapter_links = soup.find_all("a", href=lambda x: bool(x and _HAKO_CHAPTER_RE.search(x)))
        if chapter_links:
            total_chapters = str(len(set(a.get("href") for a in chapter_links)))

        slug = url.rstrip("/").split("/")[-1]

        return StoryInfo(
            title=title,
            author=author,
            description=description,
            slug=slug,
            genres=genres,
            cover_url=cover_url,
            total_chapters=total_chapters,
            word_count=word_count,
            views=views,
        )

    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        resp = await self.client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        volumes = []
        seen_urls = set()

        # Hako has <section class="volume-list"> with chapters inside <ul class="list-chapters at-series">
        # Only the first (non-disabled) volume has chapters rendered in initial HTML.
        # Other volumes are lazy-loaded via JS.
        for vol_section in soup.find_all("section", class_="volume-list"):
            header = vol_section.find("header", class_="sect-header")
            if header:
                title_span = header.find("span", class_="sect-title")
                vol_title = title_span.text.strip() if title_span else "Volume"
            else:
                vol_title = "Volume"

            chapters = []
            chap_list = vol_section.find("ul", class_="list-chapters")
            if chap_list:
                for li in chap_list.find_all("li"):
                    a = li.find("a", href=lambda x: bool(x and _HAKO_CHAPTER_RE.search(x)))
                    if a:
                        chap_url = "https://ln.hako.vn" + a.get("href")
                        if chap_url not in seen_urls:
                            seen_urls.add(chap_url)
                            title = a.get("title") or a.text.strip()
                            chapters.append(ChapterTreeItem(title=title, url=chap_url))

            volumes.append(VolumeTreeItem(volume=vol_title, chapters=chapters))

        # Fallback: if no volume sections, gather all chapter links into one volume
        if not volumes:
            chapters = []
            for a in soup.find_all("a", href=lambda x: bool(x and _HAKO_CHAPTER_RE.search(x))):
                chap_url = "https://ln.hako.vn" + a.get("href")
                if chap_url not in seen_urls:
                    seen_urls.add(chap_url)
                    title = a.get("title") or a.text.strip()
                    chapters.append(ChapterTreeItem(title=title, url=chap_url))
            volumes.append(VolumeTreeItem(volume="Volume 1", chapters=chapters))

        return volumes

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        if not self.browser:
            raise RuntimeError("Browser instance required for LnHakoSource content extraction")

        max_attempts = 3
        backoffs = [2, 4]

        for attempt in range(max_attempts):
            page = await self.browser.new_page()
            try:
                await page.goto(chapter_url, wait_until="networkidle", timeout=60000)
                try:
                    await page.wait_for_selector("#chapter-content", timeout=30000)
                except (PlaywrightTimeoutError, TimeoutError):
                    # Some Hako chapters render the container late, but text nodes can still be queryable.
                    await page.wait_for_selector("#chapter-content p, #chapter-content img", timeout=30000)

                # Get text paragraphs
                # hako usually has content in <p> tags inside #chapter-content
                paragraphs = await page.locator("#chapter-content p").all_inner_texts()

                extracted_content = []
                for p in paragraphs:
                    if p.strip():
                        extracted_content.append(ContentItem(type="text", data=p.strip()))

                # Also get images if any
                images = await page.locator("#chapter-content img").all()
                for img in images:
                    src = await img.get_attribute("src")
                    if src:
                        extracted_content.append(ContentItem(type="image", data=src))

                return extracted_content
            except (PlaywrightTimeoutError, TimeoutError):
                if attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(backoffs[attempt])
            finally:
                await page.close()
