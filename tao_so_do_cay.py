import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def get_chapter_tree(url: str, output_file: str):
    print("Đang tạo sơ đồ cây...")
    """
    Sử dụng Playwright Async API để truy cập URL, sau đó dùng BeautifulSoup để
    phân tích và trích xuất sơ đồ các tập và chương truyện, rồi lưu vào file txt.
    Phiên bản này tương thích với môi trường đã có asyncio loop.

    Args:
        url (str): URL của trang truyện.
        output_file (str): Tên của file txt để lưu sơ đồ.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url, wait_until='networkidle')
            html_content = await page.content()
            await browser.close()

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
