"""
Core scraping functions for the web novel scraper.
"""
import asyncio
from typing import Dict, List, Optional, Any

import httpx
from playwright.async_api import Browser, async_playwright
from bs4 import BeautifulSoup

from loguru import logger

from utils import HEADERS
from models import StoryInfo, ContentItem


MAX_RETRIES = 2


async def lay_thong_tin_truyen(client: httpx.AsyncClient, ten_truyen: str, verbose: bool = False) -> StoryInfo:
    """
    Scrapes basic information about the story from its main page using httpx and BeautifulSoup.
    """
    url = f"https://valvrareteam.net/{ten_truyen}"
    logger.debug(f"Fetching story info from: {url}")
    
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

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

    cover_path = None
    image_url_element = soup.select_one("img.rd-cover-image")
    if image_url_element and 'src' in image_url_element.attrs:
        image_url = image_url_element['src']
        if image_url:
            try:
                response = await client.get(image_url, timeout=30.0)
                response.raise_for_status()
                cover_path = "cover.jpg"
                logger.info(f"Đã tải ảnh bìa: {cover_path}")
                with open(cover_path, "wb") as f:
                    f.write(response.content)
            except Exception as e:
                logger.warning(f"Không thể tải ảnh bìa: {e}")

    return StoryInfo(
        title=title,
        author=author,
        description=description,
        genres=genres,
        cover_path=cover_path
    )


async def lay_chuong_httpx(client: httpx.AsyncClient, url: str, verbose: bool = False, token: Optional[str] = None) -> Optional[List[ContentItem]]:
    """
    Scrapes a single chapter page using httpx and BeautifulSoup (Fast Mode).
    Uses the DigitalOcean SSR fallback for better reliability and speed.
    """
    fallback_url = url.replace("valvrareteam.net", "val-ssr-2kzit.ondigitalocean.app")
    logger.debug(f"Fast-scraping from: {fallback_url}")
    
    try:
        headers = client.headers.copy()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        response = await client.get(fallback_url, follow_redirects=True, timeout=30.0, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        content_container = soup.select_one(".chapter-content")
        if not content_container:
            return None
            
        extracted_content: List[ContentItem] = []
        elements = content_container.select("p, img")
        
        for el in elements:
            if el.name == 'img':
                image_url = el.get('src')
                if image_url:
                    extracted_content.append(ContentItem(type='image', data=image_url))
            elif el.name == 'p':
                text = el.get_text(strip=True)
                if text:
                    extracted_content.append(ContentItem(type='text', data=text))
        
        return extracted_content if extracted_content else None
    except Exception as e:
        logger.debug(f"Fast-scrape failed for {fallback_url}: {e}")
        return None


async def lay_chuong_voi_hinh_anh(browser: Browser, url: str, session_state: Optional[Dict[str, Any]] = None, verbose: bool = False) -> Optional[List[ContentItem]]:
    """
    Scrapes a single chapter page for text and images using Playwright (Reliable Mode).
    """
    logger.debug(f"Playwright-scraping from: {url}")

    page = await browser.new_page(storage_state=session_state) if session_state else await browser.new_page()
    for attempt in range(MAX_RETRIES):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            content_selector = ".chapter-content p, .chapter-content img, .chapter-card p, .chapter-card img"
            await page.wait_for_selector(content_selector, timeout=30000)
            elements = page.locator(content_selector)
            extracted_content: List[ContentItem] = []
            for i in range(await elements.count()):
                element = elements.nth(i)
                tag_name = await element.evaluate('el => el.tagName')
                if tag_name == 'IMG':
                    image_url = await element.get_attribute('src')
                    if image_url:
                        extracted_content.append(ContentItem(type='image', data=image_url))
                elif tag_name == 'P':
                    text = await element.inner_text()
                    if text.strip():
                        extracted_content.append(ContentItem(type='text', data=text.strip()))
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
    urls: List[str],
    concurrent_tasks: int = 5,
    skipped_urls: Optional[List[str]] = None,
    session_state: Optional[Dict[str, Any]] = None,
    verbose: bool = False,
    token: Optional[str] = None
) -> Dict[str, List[ContentItem]]:
    """
    Scrape multiple chapters concurrently.
    Uses a hybrid approach:
    1. Try HTTTPX (Fast) first.
    2. Fallback to Playwright (Reliable) if HTTPX fails or returns empty.
    """
    semaphore = asyncio.Semaphore(concurrent_tasks)
    scraped_content: Dict[str, List[ContentItem]] = {}
    if skipped_urls is None:
        skipped_urls_local: List[str] = []
        skipped_urls = skipped_urls_local
    else:
        skipped_urls_local = skipped_urls

    # Convert session_state to httpx cookies
    cookies = {}
    if session_state and 'cookies' in session_state:
        for c in session_state['cookies']:
            cookies[c['name']] = c['value']

    async def process_url(browser: Browser, url: str) -> None:
        async with semaphore:
            content = None
            # 1. Try Fast Mode (HTTPX)
            async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, follow_redirects=True) as client:
                content = await lay_chuong_httpx(client, url, verbose=verbose, token=token)
            
            # 2. Try Reliable Mode (Playwright) if Fast Mode failed
            if not content:
                if verbose:
                    print(f"[*] Fast-scrape failed or empty for {url}. Falling back to Playwright...")
                content = await lay_chuong_voi_hinh_anh(browser, url, session_state=session_state, verbose=verbose)
            
            if content:
                scraped_content[url] = content
            else:
                skipped_urls.append(url)
                print(f"(!) Thất bại sau cả 2 phương thức: {url}")

    tasks = [process_url(browser, url) for url in urls]
    await asyncio.gather(*tasks)
    return scraped_content