import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json                                                                                                                                                                                                         

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

async def get_chapter_tree_folder(url: str, output_file: str):
    print("Đang tạo thư mục...")
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
async def get_chapter_tree_list(url: str, output_file: str = "chapter_list.json"):
    print("Đang tạo sơ đồ cây...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url, wait_until='networkidle')
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
                    chapter_link = chapter.find('a', class_='chapter-title-link')['href']
                    if chapter_link:
                        chapter_title = chapter_link
                        chapters_list.append(chapter_title)
            else:
                chapters_list.append("[Không có chương nào trong tập này]")

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
        print(f"Đã xảy ra lỗi: {e}")
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
#asyncio.run(get_chapter_tree_list("https://valvrareteam.net/truyen/bi-mat-cua-phu-thuy-tinh-lang-4b74a318"))