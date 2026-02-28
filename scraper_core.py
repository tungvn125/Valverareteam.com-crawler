"""
Core scraping functions for the web novel scraper.
"""
import asyncio
from typing import Dict, List, Optional, Any

import httpx
from playwright.async_api import Browser, async_playwright
from bs4 import BeautifulSoup

from utils import HEADERS
from models import StoryInfo, ContentItem


MAX_RETRIES = 2


async def lay_thong_tin_truyen(client: httpx.AsyncClient, ten_truyen: str) -> StoryInfo:
    """
    Scrapes basic information about the story from its main page using httpx and BeautifulSoup.
    """
    url = f"https://valvrareteam.net/{ten_truyen}"
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    title_element = soup.select_one("h1.rd-novel-title")
    title = title_element.get_text(strip=True) if title_element else "Unknown Title"

    author_elements = soup.select("span.rd-author-name")
    authors = [author.get_text(strip=True) for author in author_elements]
    author = ", ".join(authors) if authors else "Unknown Author"

    description_element = soup.select_one("div.rd-description-content")
    description = description_element.get_text(strip=True) if description_element else "No Description"

    cover_path = None
    image_url_element = soup.select_one("img.rd-cover-image")
    if image_url_element and 'src' in image_url_element.attrs:
        image_url = image_url_element['src']
        if image_url:
            try:
                response = await client.get(image_url, timeout=30.0)  # Added timeout
                response.raise_for_status()
                cover_path = "cover.jpg"
                print(f"Đang tải ảnh bìa về: {cover_path}")
                with open(cover_path, "wb") as f:
                    f.write(response.content)
            except httpx.HTTPStatusError as e:
                print(f"Lỗi HTTP khi tải ảnh bìa từ {image_url}: {e}")
            except Exception as e:
                print(f"Lỗi khi tải hoặc lưu ảnh bìa: {e}")  # Improved error message

    return StoryInfo(
        title=title,
        author=author,
        description=description,
        cover_path=cover_path
    )


async def lay_chuong_voi_hinh_anh(browser: Browser, url: str) -> Optional[List[ContentItem]]:
    """
    Scrapes a single chapter page for text and images using Playwright.
    Retries on failure.
    """
    page = await browser.new_page()
    for attempt in range(MAX_RETRIES):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            content_selector = ".chapter-card p, .chapter-card img"
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
            print(f"Lỗi lần {attempt + 1}/{MAX_RETRIES} khi scraping {url}: {e}")
            if attempt < MAX_RETRIES - 1:
                print("Đang thử lại sau 5 giây...")
                await asyncio.sleep(5)
            else:
                print(f"Bỏ qua URL {url} sau {MAX_RETRIES} lần thử thất bại.")

    await page.close()
    return None


async def scrape_chapters(
    browser: Browser,
    urls: List[str],
    concurrent_tasks: int = 5,
    skipped_urls: Optional[List[str]] = None
) -> Dict[str, List[ContentItem]]:
    """
    Scrape multiple chapters concurrently.
    Returns a dictionary mapping URL to content list.
    If skipped_urls list is provided, failed URLs are appended to it.
    """
    semaphore = asyncio.Semaphore(concurrent_tasks)
    scraped_content: Dict[str, List[ContentItem]] = {}
    if skipped_urls is None:
        skipped_urls_local: List[str] = []
        skipped_urls = skipped_urls_local
    else:
        skipped_urls_local = skipped_urls

    async def process_url(browser: Browser, url: str) -> None:
        async with semaphore:
            content = await lay_chuong_voi_hinh_anh(browser, url)
            if content:
                scraped_content[url] = content
            else:
                skipped_urls.append(url)
                print(f"Đã thêm {url} vào danh sách các chương bị bỏ qua.")

    tasks = [process_url(browser, url) for url in urls]
    await asyncio.gather(*tasks)
    return scraped_content