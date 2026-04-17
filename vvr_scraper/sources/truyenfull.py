import asyncio
import re

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger

from ..models import ContentItem, StoryInfo
from ..utils import HEADERS
from . import BaseSource, ChapterTreeItem, SearchResult, VolumeTreeItem

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0


def _extract_text_segments(element: Tag) -> list[str]:
    """Split TruyenFull's single-paragraph + <br><br> markup into logical paragraphs."""
    segments: list[str] = []
    current: list[str] = []
    consecutive_breaks = 0

    for node in element.children:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                current.append(text)
                consecutive_breaks = 0
            continue

        if node.name == "br":
            consecutive_breaks += 1
            if consecutive_breaks >= 2 and current:
                segment = " ".join(current).strip()
                if segment:
                    segments.append(segment)
                current = []
            continue

        text = node.get_text(" ", strip=True)
        if text:
            current.append(text)
            consecutive_breaks = 0

    if current:
        segment = " ".join(current).strip()
        if segment:
            segments.append(segment)

    return segments


async def _request_with_retry(client: httpx.AsyncClient, url: str, params: dict | None = None) -> httpx.Response:
    """Make an HTTP GET request with exponential backoff on 429/503."""
    last_resp = None
    for attempt in range(_MAX_RETRIES):
        resp = await client.get(url, params=params, follow_redirects=True)
        if resp.status_code in (429, 503):
            delay = _RETRY_DELAY * (2**attempt)
            logger.warning(f"Rate-limited ({resp.status_code}) on {url}, retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)
            last_resp = resp
            continue
        resp.raise_for_status()
        return resp
    if last_resp is not None:
        last_resp.raise_for_status()
    raise httpx.HTTPError(f"Failed to fetch {url} after {_MAX_RETRIES} retries")


class TruyenFullSource(BaseSource):
    base_urls = ["truyenfull.vision"]

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def search(self, query: str) -> list[SearchResult]:
        url = f"https://truyenfull.vision/ajax.php?type=quick_search&str={query}"
        resp = await _request_with_retry(self.client, url)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.find_all("a", class_="list-group-item"):
            results.append(SearchResult(title=a.get("title", a.text.strip()), url=a.get("href")))
        return results

    async def get_info(self, url: str) -> StoryInfo:
        resp = await _request_with_retry(self.client, url)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        title_elem = soup.select_one("h3.title")
        title = title_elem.text.strip() if title_elem else "Unknown"

        author_elem = soup.select_one("a[itemprop='author']")
        author = author_elem.text.strip() if author_elem else "Unknown"

        description_elem = soup.select_one("div.desc-text")
        description = description_elem.text.strip() if description_elem else "No description"

        cover_elem = soup.select_one("div.book-thumb img")
        cover_url = cover_elem.get("src") if cover_elem else None

        genres = [a.text.strip() for a in soup.select("div.info a[itemprop='genre']")]

        total_chapters = "Unknown"
        stats = soup.select("div.info div")
        for stat in stats:
            if "Chương" in stat.text:
                match = re.search(r"(\d+)", stat.text)
                if match:
                    total_chapters = match.group(1)

        slug = url.rstrip("/").split("/")[-1]

        return StoryInfo(
            title=title,
            author=author,
            description=description,
            slug=slug,
            genres=genres,
            cover_url=cover_url,
            total_chapters=total_chapters,
        )

    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        resp = await _request_with_retry(self.client, url)
        html = resp.text

        truyen_id_match = re.search(r'id="truyen-id"[^>]*value="(\d+)"', html)
        total_page_match = re.search(r'id="total-page"[^>]*value="(\d+)"', html)

        if not truyen_id_match or not total_page_match:
            return []

        truyen_id = truyen_id_match.group(1)
        total_page = int(total_page_match.group(1))
        slug = url.rstrip("/").split("/")[-1]

        title_elem = BeautifulSoup(html, "html.parser").select_one("h3.title")
        title = title_elem.text.strip() if title_elem else ""

        chapters = []
        seen_urls = set()
        for page in range(1, total_page + 1):
            ajax_url = "https://truyenfull.vision/ajax.php"
            params = {
                "type": "list_chapter",
                "tid": truyen_id,
                "tascii": slug,
                "tname": title,
                "page": page,
                "totalp": total_page,
            }
            resp = await _request_with_retry(self.client, ajax_url, params=params)
            data = resp.json()
            soup = BeautifulSoup(data["chap_list"], "html.parser")
            for li in soup.find_all("li"):
                a = li.find("a")
                if a:
                    chap_url = a.get("href")
                    if chap_url and chap_url not in seen_urls:
                        seen_urls.add(chap_url)
                        chapters.append(
                            ChapterTreeItem(
                                title=a.get("title", a.text.strip()),
                                url=chap_url,
                            )
                        )
            await asyncio.sleep(0.5)

        return [VolumeTreeItem(volume="Volume 1", chapters=chapters)]

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        resp = await _request_with_retry(self.client, chapter_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        content_div = soup.find("div", id="chapter-c")
        if not content_div:
            return []

        for ad in content_div.find_all("div", class_=lambda x: x and "ads" in x.lower()):
            ad.decompose()

        extracted_content = []
        for element in content_div.find_all(["p", "img"]):
            if element.name == "img":
                img_src = element.get("src") or element.get("data-src")
                if img_src:
                    extracted_content.append(ContentItem(type="image", data=img_src))
            elif element.name == "p":
                text_segments = _extract_text_segments(element)
                for text in text_segments:
                    extracted_content.append(ContentItem(type="text", data=text))

        if not extracted_content:
            text_lines = content_div.get_text(separator="\n").split("\n")
            for line in text_lines:
                clean_line = line.strip()
                if clean_line:
                    extracted_content.append(ContentItem(type="text", data=clean_line))

        return extracted_content
