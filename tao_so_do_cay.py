import asyncio
import httpx
from playwright.async_api import async_playwright # Added for dynamic content
from bs4 import BeautifulSoup
import json
import subprocess # Added for notify-send
from typing import Optional, Dict, Any

from utils import HEADERS


async def get_chapter_tree(url: str, output_file: str, cookies: Optional[Dict[str, str]] = None):
    print("Đang tạo sơ đồ cây...")
    """
    Sử dụng httpx để truy cập URL, sau đó dùng BeautifulSoup để
    phân tích và trích xuất sơ đồ các tập và chương truyện, rồi lưu vào file txt.
    Phiên bản này tương thích với môi trường đã có asyncio loop.

    Args:
        url (str): URL của trang truyện.
        output_file (str): Tên của file txt để lưu sơ đồ.
    """
    try:
        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status() # Raise an exception for 4xx or 5xx status codes
            html_content = response.text

        soup = BeautifulSoup(html_content, 'html.parser')
        
        chapter_tree_string = ""
        volumes = soup.find_all('div', class_='module-container')

        if not volumes:
            print("Không tìm thấy container nào cho các tập truyện.")
            return

        print(f"Tìm thấy {len(volumes)} tập/phần truyện. Bắt đầu trích xuất...")

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
        
        print(f"Đã tạo thành công sơ đồ các chương và lưu vào file '{output_file}'")

    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")

async def get_chapter_tree_folder(url: str, output_file: str, cookies: Optional[Dict[str, str]] = None):
    print("Đang tạo thư mục...")
    """
    Sử dụng httpx để truy cập URL, sau đó dùng BeautifulSoup để
    phân tích và trích xuất sơ đồ các tập và chương truyện, rồi lưu vào file txt.
    Phiên bản này tương thích với môi trường đã có asyncio loop.

    Args:
        url (str): URL của trang truyện.
        output_file (str): Tên của file txt để lưu sơ đồ.
    """
    try:
        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text

        soup = BeautifulSoup(html_content, 'html.parser')
        
        chapter_tree_string = ""
        volumes = soup.find_all('div', class_='module-container')

        if not volumes:
            print("Không tìm thấy container nào cho các tập truyện.")
            return

        print(f"Tìm thấy {len(volumes)} tập/phần truyện. Bắt đầu trích xuất...")

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
        
        #print(f"Đã tạo thành công sơ đồ các chương và lưu vào file '{output_file}'")

    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")
#creat list chapter
async def get_chapter_tree_list(url: str, output_file: str = "chapter_list.json", session_state: Optional[Dict[str, Any]] = None):
    print("Đang tạo sơ đồ cây (sử dụng Playwright cho nội dung động)...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            # Use consistent User-Agent
            user_agent = HEADERS.get("User-Agent")
            context = await browser.new_context(storage_state=session_state, user_agent=user_agent) if session_state else await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Wait for content to stabilize
            await page.wait_for_timeout(2000)
            await page.wait_for_selector('.module-chapter-item', timeout=30000)
            
            html_content = await page.content()
            await browser.close()

        soup = BeautifulSoup(html_content, 'html.parser')
        volumes = soup.find_all('div', class_='module-container')

        if not volumes:
            print("Không tìm thấy container nào cho các tập truyện.")
            return []

        print(f"Tìm thấy {len(volumes)} tập/phần truyện. Bắt đầu trích xuất...")

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
                        # Find link - try both specific class and any anchor tag
                        link_element = chapter.find('a', class_='chapter-title-link') or chapter.find('a')
                        
                        if link_element and 'href' in link_element.attrs:
                            chapter_link = link_element['href']
                            if "minh-hoa" not in chapter_link:
                                chapters_list.append(chapter_link)
                        else:
                            # If we still can't find it, log the classes for debug
                            classes = chapter.get('class', [])
                            if 'locked-chapter' in classes or 'chapter-mode-protected' in classes:
                                print(f"[Cảnh báo] Chương này vẫn bị khóa (locked): {chapter.get_text(strip=True)}")
                            else:
                                print(f"Cant find link for chapter: {chapter}")
                    except Exception:
                        pass # Silently skip malformed chapters

            data.append({
                "volume": volume_title,
                "chapters": chapters_list
            })

        # Lưu ra file JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Đã lưu sơ đồ cây vào {output_file}")
        return data

    except Exception as e:
        print(f"Đã xảy ra lỗi khi dùng Playwright để lấy danh sách chương: {e}")
        return []

def get_chapters_by_volume_index(file_path: str, index: int):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if index < 0 or index >= len(data):
            print("Index không hợp lệ. Trong file chỉ có", len(data), "tập.")
            return []

        volume = data[index]
        #print(f"Tên tập: {volume['volume']}")
        return volume["chapters"]

    except Exception as e:
        print("Đã xảy ra lỗi khi đọc file:", e)
        return []
