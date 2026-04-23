"""
Core scraping functions for the web novel scraper.
"""

import asyncio
import os
import tempfile
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import Browser

from .models import ContentItem, StoryInfo
from .sources import REGISTRY, get_source
from .utils import HEADERS

MAX_RETRIES = 2


async def lay_thong_tin_truyen(
    client: httpx.AsyncClient,
    ten_truyen: str,
    verbose: bool = False,
    browser: Browser | None = None,
) -> StoryInfo:
    """
    Scrapes basic information about the story from its main page.
    Supports multiple sources including valvrareteam.net and others in .sources module.
    """
    # Check if it's a full URL or just a slug
    if ten_truyen.startswith("http"):
        url = ten_truyen
    else:
        url = f"https://valvrareteam.net/{ten_truyen}"

    source = REGISTRY.get(url, client=client, browser=browser)
    if source:
        info = await source.get_info(url)
        # Tải cover nếu source trả cover_url nhưng chưa set cover_path
        if info.cover_url and not info.cover_path:
            cover_bytes = await source.fetch_cover(info.cover_url)
            if cover_bytes:
                _fd, cover_path = tempfile.mkstemp(suffix=".jpg", prefix="vvr_cover_")
                os.close(_fd)
                try:

                    def _save(path: str, content: bytes) -> None:
                        with open(path, "wb") as f:
                            f.write(content)

                    await asyncio.to_thread(_save, cover_path, cover_bytes)
                    info.cover_path = cover_path
                    logger.info(f"Đã tải ảnh bìa: {cover_path}")
                except Exception as e:
                    logger.warning(f"Không thể lưu ảnh bìa: {e}")
                    if cover_path and os.path.exists(cover_path):
                        try:
                            os.remove(cover_path)
                        except OSError:
                            pass
        return info

    logger.warning(f"Không tìm thấy source cho: {url}")
    raise ValueError(f"Không có source hỗ trợ URL: {url}")


async def lay_chuong_httpx(
    client: httpx.AsyncClient, url: str, verbose: bool = False, token: str | None = None, browser: Browser | None = None
) -> list[ContentItem] | None:
    """
    Scrapes a single chapter page using httpx (Fast Mode).
    Supports custom sources for non-VVR domains.
    """
    if "valvrareteam.net" not in url:
        source = get_source(url, client=client, browser=browser)
        if source:
            try:
                # If it's Hako, it might need browser even in 'Fast' mode (though not really fast)
                # But BaseSource.get_content handles its own logic
                return await source.get_content(url)
            except Exception as e:
                logger.error(f"Custom source scrape failed for {url}: {e}")
                raise

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
    # Reduce concurrency for custom sources — they often rate-limit
    has_custom_urls = any("valvrareteam.net" not in url for url in urls)
    effective_concurrency = max(1, concurrent_tasks // 2) if has_custom_urls else concurrent_tasks
    if effective_concurrency != concurrent_tasks:
        logger.info(f"Custom source detected — reducing concurrency: {concurrent_tasks} → {effective_concurrency}")

    semaphore = asyncio.Semaphore(effective_concurrency)
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
                # Now also supports custom sources which might need browser
                content = await lay_chuong_httpx(client, url, verbose=verbose, token=token, browser=browser)

                # 2. Try Reliable Mode (Playwright) — only for VVR URLs
                # Playwright fallback uses VVR-specific selectors, not suitable for custom sources
                if not content and "valvrareteam.net" in url:
                    logger.debug(f"Fast-scrape failed for {url}. Falling back to Playwright (VVR only)...")
                    content = await lay_chuong_voi_hinh_anh(browser, url, session_state=session_state, verbose=verbose)
                elif not content:
                    logger.warning(f"Custom source returned no content for: {url} — no Playwright fallback for non-VVR URLs")

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
