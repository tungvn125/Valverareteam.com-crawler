import asyncio
import httpx
from playwright.async_api import async_playwright, Browser
from bs4 import BeautifulSoup
import json
from typing import Optional, Dict, Any, List
from uuid import uuid4

from loguru import logger

from .utils import HEADERS


async def get_chapter_tree(url: str, output_file: str, cookies: Optional[Dict[str, str]] = None):
    """
    Sử dụng httpx để truy cập URL, sau đó dùng BeautifulSoup để
    phân tích và trích xuất sơ đồ các tập và chương truyện, rồi lưu vào file txt.

    Args:
        url (str): URL của trang truyện.
        output_file (str): Tên của file txt để lưu sơ đồ.
    """
    logger.info("Đang tạo sơ đồ cây...")
    try:
        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text

        soup = BeautifulSoup(html_content, 'html.parser')

        chapter_tree_string = ""
        volumes = soup.find_all('div', class_='module-container')

        if not volumes:
            logger.warning("Không tìm thấy container nào cho các tập truyện.")
            return

        logger.info(f"Tìm thấy {len(volumes)} tập/phần truyện. Bắt đầu trích xuất...")

        for volume in volumes:
            volume_title_element = volume.find('h3', class_='module-title')
            if volume_title_element:
                volume_title = volume_title_element.get_text(strip=True)
                chapter_tree_string += f"■ {volume_title}\n"
            else:
                chapter_tree_string += "■ [Không có tiêu đề tập]\n"

            chapters = volume.find_all('div', class_='module-chapter-item')
            if chapters:
                for chapter in chapters:
                    chapter_link = chapter.find('a', class_='chapter-title-link')
                    if chapter_link:
                        chapter_title = chapter_link.get_text(strip=True)
                        chapter_tree_string += f"  - {chapter_title}\n"
            else:
                chapter_tree_string += "  - [Không có chương nào trong tập này]\n"

            chapter_tree_string += "\n"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(chapter_tree_string)

        logger.info(f"Đã tạo thành công sơ đồ các chương và lưu vào file '{output_file}'")

    except Exception as e:
        logger.error(f"Đã xảy ra lỗi: {e}")


async def get_chapter_tree_folder(url: str, output_file: str, cookies: Optional[Dict[str, str]] = None):
    """
    Sử dụng httpx để truy cập URL, sau đó dùng BeautifulSoup để
    phân tích và trích xuất sơ đồ các tập truyện, rồi lưu vào file txt.

    Args:
        url (str): URL của trang truyện.
        output_file (str): Tên của file txt để lưu sơ đồ.
    """
    logger.info("Đang tạo thư mục...")
    try:
        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text

        soup = BeautifulSoup(html_content, 'html.parser')

        chapter_tree_string = ""
        volumes = soup.find_all('div', class_='module-container')

        if not volumes:
            logger.warning("Không tìm thấy container nào cho các tập truyện.")
            return

        logger.info(f"Tìm thấy {len(volumes)} tập/phần truyện. Bắt đầu trích xuất...")

        for volume in volumes:
            volume_title_element = volume.find('h3', class_='module-title')
            if volume_title_element:
                volume_title = volume_title_element.get_text(strip=True)
                volume_title_string = volume_title.replace(":", " -").replace("/", " -").replace("\\", " -").replace("*", " -").replace("?", " -").replace("\"", " -").replace("<", " -").replace(">", " -").replace("|", " -")
                chapter_tree_string += f" {volume_title_string}\n"
            else:
                chapter_tree_string += "[no name]\n"
            chapter_tree_string += "\n"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(chapter_tree_string)

    except Exception as e:
        logger.error(f"Đã xảy ra lỗi: {e}")


async def _fetch_chapter_page(browser: Browser, url: str, session_state: Optional[Dict[str, Any]] = None) -> str:
    """Fetches chapter page HTML content using a Playwright browser instance."""
    user_agent = HEADERS.get("User-Agent")
    context = (
        await browser.new_context(storage_state=session_state, user_agent=user_agent)
        if session_state
        else await browser.new_context(user_agent=user_agent)
    )
    page = await context.new_page()
    await page.goto(url, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(2000)
    await page.wait_for_selector('.module-chapter-item', timeout=30000)
    html_content = await page.content()
    await context.close()
    return html_content


async def get_chapter_tree_list(
    url: str,
    output_file: str = "chapter_list.json",
    session_state: Optional[Dict[str, Any]] = None,
    browser: Optional[Browser] = None,
) -> List[Dict]:
    """
    Extracts the chapter tree as a structured JSON list using Playwright.

    Args:
        url: URL of the story page.
        output_file: Path to save the JSON output.
        session_state: Playwright storage state for authenticated sessions.
        browser: Optional Playwright Browser to reuse. If None, creates its own.

    Returns:
        List of volume dicts with chapter data.
    """
    logger.info("Đang tạo sơ đồ cây (sử dụng Playwright cho nội dung động)...")

    try:
        # Get HTML content — reuse provided browser or create one
        if browser is None:
            async with async_playwright() as p:
                _browser = await p.chromium.launch()
                html_content = await _fetch_chapter_page(_browser, url, session_state)
                await _browser.close()
        else:
            html_content = await _fetch_chapter_page(browser, url, session_state)

        soup = BeautifulSoup(html_content, 'html.parser')
        volumes = soup.find_all('div', class_='module-container')

        if not volumes:
            logger.warning("Không tìm thấy container nào cho các tập truyện.")
            return []

        logger.info(f"Tìm thấy {len(volumes)} tập/phần truyện. Bắt đầu trích xuất...")

        data = []

        for volume in volumes:
            volume_title_element = volume.find('h3', class_='module-title')
            if volume_title_element:
                volume_title = volume_title_element.get_text(strip=True)
            else:
                volume_title = "[Không có tiêu đề tập]"

            chapters_list = []
            chapters = volume.find_all('div', class_='module-chapter-item')
            if chapters:
                for chapter in chapters:
                    try:
                        # Find link — try both specific class and any anchor tag
                        link_element = chapter.find('a', class_='chapter-title-link') or chapter.find('a')

                        # Check for locked status
                        classes = chapter.get('class', [])
                        is_locked = 'locked-chapter' in classes or 'chapter-mode-protected' in classes

                        if link_element and 'href' in link_element.attrs:
                            chapter_link = link_element['href']
                            chapter_title = link_element.get_text(strip=True)

                            chapters_list.append({
                                "title": chapter_title,
                                "url": chapter_link,
                                "locked": is_locked
                            })
                        else:
                            # If we still can't find it, but it's locked, we still want to show it
                            if is_locked:
                                chapters_list.append({
                                    "title": chapter.get_text(strip=True),
                                    "url": "",
                                    "locked": True
                                })
                            else:
                                logger.debug(f"Can't find link for chapter: {chapter}")
                    except Exception:
                        pass  # Silently skip malformed chapters

            data.append({
                "volume": volume_title,
                "chapters": chapters_list
            })

        # Lưu ra file JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Đã lưu sơ đồ cây vào {output_file}")
        return data

    except Exception as e:
        logger.error(f"Đã xảy ra lỗi khi dùng Playwright để lấy danh sách chương: {e}")
        return []


def get_chapters_by_volume_index(file_path: str, index: int):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if index < 0 or index >= len(data):
            logger.warning(f"Index không hợp lệ. Trong file chỉ có {len(data)} tập.")
            return []

        volume = data[index]
        return volume["chapters"]

    except Exception as e:
        logger.error(f"Đara lỗi khi đọc file: {e}")
        return []


async def get_chapter_range_urls(
    slug_or_url: str,
    start_index: int,
    end_index: int,
    session_state: Optional[Dict[str, Any]] = None,
    browser: Optional[Browser] = None
) -> List[str]:
    """
    Fetches the full chapter tree and returns a slice of chapter URLs.

    Args:
        slug_or_url: The slug (e.g. 'truyen/...') or full URL.
        start_index: 0-based start index (inclusive).
        end_index: 0-based end index (exclusive).
        session_state: Playwright storage state for authenticated sessions.
        browser: Optional Playwright Browser to reuse.

    Returns:
        List of chapter relative URLs.
    """
    from .utils import BASE_URL
    url = slug_or_url if slug_or_url.startswith("http") else f"{BASE_URL}/{slug_or_url}"

    temp_filename = f"temp_sync_{uuid4().hex[:8]}.json"
    chapter_tree = await get_chapter_tree_list(
        url,
        output_file=temp_filename,
        session_state=session_state,
        browser=browser
    )

    # Clean up temp file
    import os
    if os.path.exists(temp_filename):
        try:
            os.remove(temp_filename)
        except OSError:
            pass

    # Flatten all chapters from all volumes
    all_chapters = []
    for volume in chapter_tree:
        all_chapters.extend(volume['chapters'])

    # Slice the list
    selected_chapters = all_chapters[start_index:end_index]

    # Return only URLs
    return [chap['url'] for chap in selected_chapters]
