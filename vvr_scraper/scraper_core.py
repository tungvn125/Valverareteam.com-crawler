"""
Core scraping functions for the web novel scraper.
"""

import asyncio
import os
import re
import tempfile
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import Browser

from .models import ContentItem, StoryInfo
from .utils import BASE_URL, HEADERS

MAX_RETRIES = 2


async def lay_thong_tin_truyen(client: httpx.AsyncClient, ten_truyen: str, verbose: bool = False) -> StoryInfo:
    """
    Scrapes basic information about the story from its main page using httpx and BeautifulSoup.
    """
    url = f"https://valvrareteam.net/{ten_truyen}"
    logger.debug(f"Fetching story info from: {url}")

    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title_element = soup.select_one("h1.rd-novel-title")
    title = title_element.get_text(strip=True) if title_element else "Unknown Title"

    # Clean up status suffixes from title
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

    # Extract stats (Total Chapters, Word Count, Views)
    total_chapters = "Unknown"
    word_count = "Unknown"
    views = "-"

    # Try .rd-stat-item first (modern Next.js structure)
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

    # Try .rd-stats-item (legacy fallback)
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

    # Fallback to .rd-info-row
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

    # Fallback to .rd-chapter-count-overlay
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
            # Fallback for dynamic images
            cover_url = image_url_element["srcset"].split(",")[0].split(" ")[0]

    if cover_url:
        try:
            # Prepend base URL if relative (though usually absolute with B-CDN)
            if cover_url.startswith("/"):
                cover_url = f"{BASE_URL}{cover_url}"

            response = await client.get(cover_url, timeout=30.0)
            response.raise_for_status()

            def save_cover():
                # Use a unique temp file to avoid race conditions in multi-download
                _fd, _cover_path = tempfile.mkstemp(suffix=".jpg", prefix="vvr_cover_")
                os.close(_fd)  # Close the fd immediately; fdopen will reopen it
                with open(_cover_path, "wb") as f:
                    f.write(response.content)
                return _cover_path

            cover_path = await asyncio.to_thread(save_cover)
            logger.info(f"Đã tải ảnh bìa: {cover_path}")
        except Exception as e:
            logger.warning(f"Không thể tải ảnh bìa: {e}")
            if cover_path and os.path.exists(cover_path):
                try:
                    os.remove(cover_path)
                except Exception:
                    pass
            cover_path = None

    return StoryInfo(
        title=title,
        author=author,
        description=description,
        slug=ten_truyen,
        genres=genres,
        cover_path=cover_path,
        cover_url=cover_url,
        total_chapters=total_chapters,
        word_count=word_count,
        views=views,
    )


async def lay_chuong_httpx(
    client: httpx.AsyncClient, url: str, verbose: bool = False, token: str | None = None
) -> list[ContentItem] | None:
    """
    Scrapes a single chapter page using httpx and BeautifulSoup (Fast Mode).
    Uses the DigitalOcean SSR fallback for better reliability and speed.
    """
    ssr_url = os.getenv("VVR_SSR_URL", "val-ssr-2kzit.ondigitalocean.app")
    fallback_url = url.replace("valvrareteam.net", ssr_url)
    logger.debug(f"Fast-scraping from: {fallback_url}")

    try:
        headers = client.headers.copy()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = await client.get(fallback_url, follow_redirects=True, timeout=30.0, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        content_container = soup.select_one(".chapter-content")
        if not content_container:
            return None

        extracted_content: list[ContentItem] = []
        elements = content_container.select("p, img")

        for el in elements:
            if el.name == "img":
                image_url = el.get("src")
                if image_url:
                    extracted_content.append(ContentItem(type="image", data=image_url))
            elif el.name == "p":
                text = el.get_text(strip=True)
                if text:
                    extracted_content.append(ContentItem(type="text", data=text))

        return extracted_content if extracted_content else None
    except Exception as e:
        import traceback

        if verbose:
            logger.debug(f"Fast-scrape failed for {fallback_url}: {e}\n{traceback.format_exc()}")
        else:
            logger.debug(f"Fast-scrape failed for {fallback_url}: {e}")
        return None


async def lay_chuong_voi_hinh_anh(
    browser: Browser, url: str, session_state: dict[str, Any] | None = None, verbose: bool = False
) -> list[ContentItem] | None:
    """
    Scrapes a single chapter page for text and images using Playwright (Reliable Mode).
    """
    logger.debug(f"Playwright-scraping from: {url}")

    page = await browser.new_page(storage_state=session_state) if session_state else await browser.new_page()
    for attempt in range(MAX_RETRIES):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            content_selector = ".chapter-content p, .chapter-content img, .chapter-card p, .chapter-card img"
            await page.wait_for_selector(content_selector, timeout=30000)
            elements = page.locator(content_selector)
            extracted_content: list[ContentItem] = []
            for i in range(await elements.count()):
                element = elements.nth(i)
                tag_name = await element.evaluate("el => el.tagName")
                if tag_name == "IMG":
                    image_url = await element.get_attribute("src")
                    if image_url:
                        extracted_content.append(ContentItem(type="image", data=image_url))
                elif tag_name == "P":
                    text = await element.inner_text()
                    if text.strip():
                        extracted_content.append(ContentItem(type="text", data=text.strip()))
            await page.close()
            return extracted_content
        except Exception as e:
            if verbose:
                print(f"[DEBUG] Playwright attempt {attempt + 1} failed for {url}: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2)
            else:
                if verbose:
                    print(f"[DEBUG] Playwright failed for {url} after {MAX_RETRIES} attempts.")

    await page.close()
    return None


async def scrape_chapters(
    browser: Browser,
    urls: list[str],
    concurrent_tasks: int = 5,
    skipped_urls: list[str] | None = None,
    session_state: dict[str, Any] | None = None,
    verbose: bool = False,
    token: str | None = None,
    pre_scraped: dict[str, list[ContentItem]] | None = None,
    on_chapter_done: Any | None = None,
) -> dict[str, list[ContentItem]]:
    """
    Scrape multiple chapters concurrently.
    Uses a hybrid approach:
    1. Try HTTPX (Fast) first.
    2. Fallback to Playwright (Reliable) if HTTPX fails or returns empty.

    Args:
        browser: Playwright browser instance.
        urls: List of chapter URLs to scrape.
        concurrent_tasks: Max concurrent scraping tasks.
        skipped_urls: List to append failed URLs to (mutated in-place).
        session_state: Playwright storage state for authenticated sessions.
        verbose: Enable debug logging.
        token: JWT token for authenticated API requests.
        pre_scraped: Previously scraped content to skip (e.g. from checkpoint).
        on_chapter_done: Optional async callback(url, content, index, total)
                         called after each chapter is processed (success or skip).
    """
    semaphore = asyncio.Semaphore(concurrent_tasks)
    scraped_content: dict[str, list[ContentItem]] = {}
    if skipped_urls is None:
        skipped_urls = []

    # Pre-load already scraped content (from checkpoint)
    if pre_scraped:
        for url, content in pre_scraped.items():
            if url in urls:
                scraped_content[url] = content

    # Convert session_state to httpx cookies
    cookies = {}
    if session_state and "cookies" in session_state:
        for c in session_state["cookies"]:
            cookies[c["name"]] = c["value"]

    total = len(urls)

    # Create a single shared HTTP client for connection pooling across all chapters
    async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, follow_redirects=True) as client:

        async def process_url(url: str, idx: int) -> None:
            # Skip if already scraped (from checkpoint)
            if url in scraped_content:
                if on_chapter_done:
                    await on_chapter_done(url, scraped_content[url], idx, total)
                return

            async with semaphore:
                content = None
                # 1. Try Fast Mode (HTTPX) — reuses shared client
                content = await lay_chuong_httpx(client, url, verbose=verbose, token=token)

                # 2. Try Reliable Mode (Playwright) if Fast Mode failed
                if not content:
                    logger.debug(f"Fast-scrape failed for {url}. Falling back to Playwright...")
                    content = await lay_chuong_voi_hinh_anh(browser, url, session_state=session_state, verbose=verbose)

                if content:
                    scraped_content[url] = content
                else:
                    skipped_urls.append(url)
                    logger.warning(f"Thất bại sau cả 2 phương thức: {url}")

                if on_chapter_done:
                    await on_chapter_done(url, content, idx, total)

        tasks = [process_url(url, i) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)
    return scraped_content
