import asyncio
import json
import os
import time
import requests
from io import BytesIO
from playwright.async_api import async_playwright
from ebooklib import epub
from bs4 import BeautifulSoup
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
from tao_so_do_cay import get_chapter_tree, get_chapter_tree_list, get_chapters_by_volume_index , get_chapter_tree_folder
from alive_progress import alive_bar
from simple_term_menu import TerminalMenu
import re

def sanitize_filename(name):
    """
    Sanitizes a string to be used as a valid filename or directory name.
    It removes illegal characters for most OSes.
    """
    if not name:
        return ""
    sanitized_name = re.sub(r'[\\/*?:\"<>|]',"", name)
    sanitized_name = sanitized_name.strip(' .')
    sanitized_name = re.sub(r'\s+', ' ', sanitized_name).strip()
    return sanitized_name

skipped_urls = []
MAX_RETRIES = 2

async def lay_thong_tin_truyen(browser, ten_truyen):
    """
    Scrapes basic information about the story from its main page. Such as title, author, description and cover image.
    """
    page = await browser.new_page()
    url = f"https://valvrareteam.net/{ten_truyen}"
    await page.goto(url, wait_until='domcontentloaded')
    title = await page.locator("h1.rd-novel-title").inner_text()
    # load 2 authors 
    author_elements = page.locator("span.rd-author-name")
    authors = []
    for i in range(await author_elements.count()):
        author_name = await author_elements.nth(i).inner_text()
        authors.append(author_name.strip())
    author = ", ".join(authors)
    description = await page.locator("div.rd-description-content").inner_text()
    # download cover image 
    
    image_url = await page.locator("img.rd-cover-image").get_attribute("src")
    if image_url:
        response = requests.get(image_url)
        if response.status_code == 200:
            cover_path = "cover.jpg"
            print(f"Đang tải ảnh bìa về: {cover_path}")
            with open(cover_path, "wb") as f:
                f.write(response.content)
    await page.close()
    return {"title": title.strip(), "author": author.strip(), "description": description.strip(), cover_path: cover_path
    }

async def lay_chuong_voi_hinh_anh(browser, url):
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
            extracted_content = []
            for i in range(await elements.count()):
                element = elements.nth(i)
                tag_name = await element.evaluate('el => el.tagName')
                if tag_name == 'IMG':
                    image_url = await element.get_attribute('src')
                    if image_url:
                        extracted_content.append({'type': 'image', 'data': image_url})
                elif tag_name == 'P':
                    text = await element.inner_text()
                    if text.strip():
                        extracted_content.append({'type': 'text', 'data': text.strip()})
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

# --- CÁC HÀM XUẤT FILE ---

def tao_file_epub(filename, book_title, author, chapters_data, description="", cover_path=None):
    """
    Creates a structured EPUB file from a list of chapters, potentially grouped by volumes.
    - chapters_data: A list that can contain:
        - Chapter dictionaries: {'title': str, 'content': list}
        - Volume dictionaries: {'volume': str, 'chapters': [list of chapter dictionaries]}
    """
    print(f"Đang tạo file EPUB: {filename}...")
    book = epub.EpubBook()

    # --- Set Metadata ---
    book.set_identifier(f'urn:uuid:{os.path.basename(filename)}')
    book.set_title(book_title)
    book.set_language('vi')
    book.add_author(author)
    book.add_metadata('DC', 'description', description)
    try:
        book.set_cover("cover.jpg", open('cover.jpg', 'rb').read())
    except Exception:
        print("  [Cảnh báo] Không thể thêm ảnh bìa vào EPUB.")
    # --- Process Chapters and Volumes ---
    toc = []
    spine = ['nav']
    image_counter = 1

    def process_chapter(chap_data, chap_idx):
        nonlocal image_counter
        chap_title = chap_data.get('title', f"Chương {chap_idx}")
        chap_filename = f'chap_{chap_idx}.xhtml'
        chapter_obj = epub.EpubHtml(title=chap_title, file_name=chap_filename, lang='vi')

        html_content = f'<h1>{chap_title}</h1>'
        for item in chap_data.get('content', []):
            if item['type'] == 'text':
                html_content += f'<p>{item["data"]}</p>'
            elif item['type'] == 'image':
                try:
                    img_url = item["data"]
                    # Basic check for valid image URL
                    if not img_url.startswith(('http://', 'https://')):
                        raise ValueError("Invalid image URL")

                    response = requests.get(img_url)
                    response.raise_for_status()
                    img_content = response.content
                    
                    # Determine image extension
                    img_extension = 'jpg' # default
                    parsed_url = requests.utils.urlparse(img_url)
                    path_parts = parsed_url.path.split('.')
                    if len(path_parts) > 1:
                        img_extension = path_parts[-1].lower()
                    
                    # Ensure extension is valid for epub
                    if img_extension not in ['jpg', 'jpeg', 'png', 'gif', 'svg']:
                        # Attempt to get mimetype and decide extension
                        try:
                            content_type = response.headers['Content-Type']
                            if 'jpeg' in content_type: img_extension = 'jpg'
                            elif 'png' in content_type: img_extension = 'png'
                            #... add other mimetypes if needed
                        except (KeyError, IndexError):
                             img_extension = 'jpg' # fallback

                    img_filename = f'image_{image_counter}.{img_extension}'
                    image_counter += 1

                    img_item = epub.EpubImage(
                        uid=os.path.splitext(img_filename)[0],
                        file_name=f'images/{img_filename}',
                        media_type=f'image/{img_extension}',
                        content=img_content
                    )
                    book.add_item(img_item)
                    html_content += f'<img src="images/{img_filename}" alt="Hình minh họa"/>'
                except Exception as e:
                    print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh cho EPUB: {item.get('data', 'N/A')}. Lỗi: {e}")

        chapter_obj.content = html_content
        return chapter_obj

    chapter_index = 1
    for item in chapters_data:
        if 'volume' in item: # It's a volume
            volume_title = item['volume']
            volume_chapters = item.get('chapters', [])
            if not volume_chapters:
                continue

            toc_volume_chapters = []
            for chap_data in volume_chapters:
                epub_chapter = process_chapter(chap_data, chapter_index)
                book.add_item(epub_chapter)
                spine.append(epub_chapter)
                toc_volume_chapters.append(epub.Link(epub_chapter.file_name, epub_chapter.title, f'chap_{chapter_index}'))
                chapter_index += 1
            toc.append((epub.Section(volume_title), tuple(toc_volume_chapters)))
        
        elif 'title' in item: # It's a standalone chapter
            epub_chapter = process_chapter(item, chapter_index)
            book.add_item(epub_chapter)
            spine.append(epub_chapter)
            toc.append(epub.Link(epub_chapter.file_name, epub_chapter.title, f'chap_{chapter_index}'))
            chapter_index += 1

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Create image directory placeholder if needed
    if image_counter > 1 and not any(item.file_name == 'images/' for item in book.items):
         book.add_item(epub.EpubItem(file_name="images/", media_type="application/x-dtbncx+xml"))

    epub.write_epub(filename, book, {})
    print(f"Tạo file EPUB thành công: {filename}")


def tao_file_pdf(content_list, filename, title="Chương truyện", font_name='DejaVuSans'):
    """Creates a PDF file from a list of content."""
    print(f"Đang tạo file PDF: {filename}...")
    valid_fonts = ['DejaVuSans', 'NotoSerif']
    if font_name not in valid_fonts:
        print(f"[Cảnh báo] Font '{font_name}' không hợp lệ. Sử dụng font mặc định 'DejaVuSans'.")
        font_name = 'DejaVuSans'

    font_filename_map = {'DejaVuSans': 'DejaVuSans.ttf', 'NotoSerifF': 'NotoSerif-Regular.ttf'}
    font_path = font_filename_map.get(font_name, 'DejaVuSans.ttf')

    if not os.path.exists(font_path):
        print(f"Font '{font_path}' not found. Attempting to download...")
        font_urls = {
            'DejaVuSans': 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf',
            'NotoSerif': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notoserif/NotoSerif-Regular.ttf'
        }
        url = font_urls.get(font_name)
        if url:
            try:
                print(f"Downloading from {url}...")
                response = requests.get(url, stream=True)
                response.raise_for_status()
                with open(font_path, 'wb') as f: 
                    for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
                print(f"Font '{font_path}' downloaded successfully.")
            except Exception as e:
                print(f"!!! LỖI: Không thể tải font '{font_name}'. Lý do: {e}")
        else:
            print(f"Không có URL tải xuống cho font '{font_name}'.")

    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        style = ParagraphStyle(name='Normal_vi', fontName=font_name, fontSize=12, leading=14)
        title_style = ParagraphStyle(name='Title_vi', fontName=font_name, fontSize=18, leading=22, spaceAfter=0.2 * inch)
    except Exception:
        print(f"[Cảnh báo] Không thể đăng ký font '{font_path}'. Tiếng Việt có thể hiển thị lỗi.")
        styles = getSampleStyleSheet()
        style = styles['Normal']
        title_style = styles['h1']

    doc = SimpleDocTemplate(filename)
    story = [Paragraph(title, title_style), Spacer(1, 0.2 * inch)]
    max_width, max_height = doc.width, doc.height
    
    for item in content_list:
        if item['type'] == 'text':
            p = Paragraph(item['data'], style)
            story.append(p)
            story.append(Spacer(1, 0.1 * inch))
        elif item['type'] == 'image':
            try:
                response = requests.get(item['data'])
                response.raise_for_status()
                pil_img = PILImage.open(BytesIO(response.content))
                img_width, img_height = pil_img.size
                scale_ratio = min(max_width / img_width, max_height / img_height, 1)
                new_width = img_width * scale_ratio
                new_height = img_height * scale_ratio
                img = Image(BytesIO(response.content), width=new_width, height=new_height)
                story.append(img)
                story.append(Spacer(1, 0.1 * inch))
            except Exception as e:
                print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh cho PDF: {item['data']}. Lỗi: {e}")

    try:
        doc.build(story)
        print(f"Tạo file PDF thành công: {filename}")
    except Exception as e:
        skipped_urls.append(filename + f" (Lỗi PDF: {e})")
        print(f"!!! LỖI NGHIÊM TRỌNG: Không thể tạo file PDF '{filename}'. Lý do: {e}")

def tao_file_html(content_list, filename, title="Chương truyện"):
    """Creates an HTML file from a list of content."""
    print(f"Đang tạo file HTML: {filename}...")
    html_content = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: sans-serif; line-height: 1.6; padding: 2em; max-width: 800px; margin: auto; }}
        h1 {{ text-align: center; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 1em 0; }}
        p {{ margin: 1em 0; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
"""
    for item in content_list:
        if item['type'] == 'text':
            html_content += f'    <p>{item["data"]}</p>\n'
        elif item['type'] == 'image':
            html_content += f'    <img src="{item["data"]}" alt="Hình minh họa"/>\n'
    
    html_content += "</body>\n</html>"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Tạo file HTML thành công: {filename}")
    except Exception as e:
        print(f"!!! LỖI: Không thể tạo file HTML '{filename}'. Lý do: {e}")

def tao_file_md(content_list, filename, title="Chương truyện"):
    """Creates a Markdown file from a list of content."""
    print(f"Đang tạo file Markdown: {filename}...")
    md_content = f"# {title}\n\n"
    for item in content_list:
        if item['type'] == 'text':
            md_content += f'{item["data"]}\n\n'
        elif item['type'] == 'image':
            md_content += f'![Hình minh họa]({item["data"]})\n\n'
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"Tạo file Markdown thành công: {filename}")
    except Exception as e:
        print(f"!!! LỖI: Không thể tạo file MD '{filename}'. Lý do: {e}")

def tao_file_txt(content_list, filename, title="Chương truyện"):
    """Creates a plain text file from a list of content."""
    print(f"Đang tạo file Text: {filename}...")
    txt_content = f"{title}\n\n"
    for item in content_list:
        if item['type'] == 'text':
            txt_content += f'{item["data"]}\n\n'
        elif item['type'] == 'image':
            txt_content += f'[Hình minh họa: {item["data"]}]\n\n'
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        print(f"Tạo file Text thành công: {filename}")
    except Exception as e:
        print(f"!!! LỖI: Không thể tạo file TXT '{filename}'. Lý do: {e}")

# --- LOGIC CHÍNH ---

def create_folders_from_tree(tree_file, base_folder):
    """Creates directory structure based on a tree map file."""
    try:
        with open(tree_file, 'r', encoding='utf-8') as f:
            tree_data = f.readlines()
        for line in tree_data:
            folder_name = sanitize_filename(line.strip())
            if folder_name:
                folder_path = os.path.join(base_folder, folder_name)
                os.makedirs(folder_path, exist_ok=True)
    except FileNotFoundError:
        print(f"Lưu ý: file tree_map.txt không tồn tại, sẽ tạo thư mục gốc.")
        os.makedirs(base_folder, exist_ok=True)

import argparse
import sys

# (Các import khác giữ nguyên)
# ...

async def main():
    parser = argparse.ArgumentParser(
        description="Tải truyện từ Valvrare Team dưới dạng PDF, EPUB, và các định dạng khác.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # Nếu có đối số dòng lệnh, dùng chế độ CLI, ngược lại, dùng chế độ tương tác
    is_cli_mode = len(sys.argv) > 1

    # --- Định nghĩa các đối số cho CLI ---
    parser.add_argument(
        'ten_truyen', 
        nargs='?' if not is_cli_mode else None, 
        help="Tên truyện cần tải (bắt buộc ở chế độ CLI)."
    )
    parser.add_argument(
        '-o', '--output', 
        dest='output_folder', 
        help="Thư mục đầu ra để lưu file. Mặc định là tên truyện."
    )
    parser.add_argument(
        '-f', '--format', 
        nargs='+', 
        default=['EPUB'], 
        choices=['PDF', 'EPUB', 'HTML', 'MD', 'TXT'],
        help="Định dạng file đầu ra. Có thể chọn nhiều. Mặc định: EPUB."
    )
    parser.add_argument(
        '-g', '--gop', 
        default='rieng', 
        choices=['rieng', 'volume', 'tatca'],
        help="Cách gộp file:\n"
             "rieng: Mỗi chương một file (mặc định).\n"
             "volume: Gộp các chương theo từng tập.\n"
             "tatca: Gộp tất cả thành một file duy nhất."
    )
    parser.add_argument(
        '--khong-minh-hoa', 
        action='store_true',
        help="Bỏ qua các chương/tập minh họa."
    )
    parser.add_argument(
        '--font', 
        default='DejaVuSans', 
        choices=['NotoSerif', 'DejaVuSans'],
        help="Font chữ cho file PDF. Mặc định: DejaVuSans."
    )
    parser.add_argument(
        '-t', '--tasks', 
        type=int, 
        default=5,
        help="Số lượng tác vụ tải song song. Mặc định: 5."
    )
    
    selection_group = parser.add_mutually_exclusive_group()
    selection_group.add_argument(
        '--all', 
        action='store_true',
        help="Tải tất cả các chương (mặc định)."
    )
    selection_group.add_argument(
        '--volumes', 
        nargs='+', 
        type=int,
        help="Tải các tập cụ thể theo số thứ tự (ví dụ: --volumes 1 3 5)."
    )
    selection_group.add_argument(
        '--chapters', 
        nargs='+', 
        type=int,
        help="Tải các chương cụ thể theo số thứ tự tuyệt đối (ví dụ: --chapters 1 10 15)."
    )

    args = parser.parse_args()

    # --- Logic chính ---
    if is_cli_mode:
        ten_truyen_raw = args.ten_truyen
        if not ten_truyen_raw:
            parser.error("Tên truyện là bắt buộc ở chế độ CLI.")
    else:
        ten_truyen_raw = input("Nhập tên truyện bạn muốn tải: ")

    sitemap_url = "https://valvrareteam.net/sitemap.xml"
    response = requests.get(sitemap_url)
    soup = BeautifulSoup(response.content, "lxml-xml")
    
    ten_truyen_normalized = ten_truyen_raw.lower().replace(" ", "-")
    output_folder = args.output_folder if is_cli_mode and args.output_folder else sanitize_filename(ten_truyen_raw.strip())
    os.makedirs(output_folder, exist_ok=True)
    
    # ... (phần xử lý vietnamese_map giữ nguyên)
    vietnamese_map = {
        'à':'a', 'á':'a', 'ả':'a', 'ã':'a', 'ạ':'a', 'ă':'a', 'ằ':'a', 'ắ':'a', 'ẳ':'a', 'ẵ':'a', 'ặ':'a',
        'â':'a', 'ầ':'a', 'ấ':'a', 'ẩ':'a', 'ẫ':'a', 'ậ':'a', 'đ':'d', 'è':'e', 'é':'e', 'ẻ':'e', 'ẽ':'e',
        'ẹ':'e', 'ê':'e', 'ề':'e', 'ế':'e', 'ể':'e', 'ễ':'e', 'ệ':'e', 'ì':'i', 'í':'i', 'ỉ':'i', 'ĩ':'i',
        'ị':'i', 'ò':'o', 'ó':'o', 'ỏ':'o', 'õ':'o', 'ọ':'o', 'ô':'o', 'ồ':'o', 'ố':'o', 'ổ':'o', 'ỗ':'o',
        'ộ':'o', 'ơ':'o', 'ờ':'o', 'ớ':'o', 'ở':'o', 'ỡ':'o', 'ợ':'o', 'ù':'u', 'ú':'u', 'ủ':'u', 'ũ':'u',
        'ụ':'u', 'ư':'u', 'ừ':'u', 'ứ':'u', 'ử':'u', 'ữ':'u', 'ự':'u', 'ỳ':'y', 'ý':'y', 'ỷ':'y', 'ỹ':'y', 'ỵ':'y'
    }
    for key, value in vietnamese_map.items():
        ten_truyen_normalized = ten_truyen_normalized.replace(key, value)
    # ...
    trang_chinh = None
    #... (phần tìm trang_chinh giữ nguyên)
    for loc in soup.find_all("loc"):
        url = loc.text
        if ten_truyen_normalized in url and "/chuong" not in url:
            trang_chinh = url
            break
    
    if not trang_chinh:
        print(f"Không tìm thấy truyện '{ten_truyen_raw}'. Vui lòng kiểm tra lại tên truyện.")
        return

    # ... (phần lay_thong_tin_truyen và get_chapter_tree_list giữ nguyên)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        story_info = await lay_thong_tin_truyen(browser, trang_chinh.split("https://valvrareteam.net/")[-1])
        await browser.close()
    print("Đang lấy danh sách chương từ trang chính của truyện...")
    await get_chapter_tree_list(trang_chinh, output_file="chapter_list.json")
    await asyncio.sleep(1)
    
    try:
        with open("chapter_list.json", "r", encoding="utf-8") as f:
            chapter_data = json.load(f)
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đọc file chapter_list.json: {e}")
        return

    # --- Xử lý lựa chọn của người dùng (CLI hoặc tương tác) ---

    # Lọc chương minh họa
    if is_cli_mode:
        minh_hoa_choice = 'y' if args.khong_minh_hoa else 'n'
    else:
        minh_hoa_choice = input("Bạn có muốn bỏ qua các chương minh họa không? (Y/n): ").strip().lower()

    if not minh_hoa_choice or minh_hoa_choice in ["y", "yes"]:
        print("Bạn đã chọn bỏ qua các chương minh họa.")
        for volume_data in chapter_data:
            volume_data['chapters'] = [ch for ch in volume_data['chapters'] if 'minh-hoa' not in ch]
        chapter_data = [vol for vol in chapter_data if vol['chapters']]

    if not chapter_data:
        print("Không có chương nào để tải sau khi đã lọc.")
        return

    # Chọn chương/tập để tải
    selected_chapters_relative = []
    if is_cli_mode:
        if args.volumes:
            selected_indices = [int(i) - 1 for i in args.volumes]
            for index in selected_indices:
                if 0 <= index < len(chapter_data):
                    selected_chapters_relative.extend(chapter_data[index]['chapters'])
                else:
                    print(f"[Cảnh báo] Bỏ qua chỉ số tập không hợp lệ: {index + 1}")
        elif args.chapters:
            all_chapters_flat = [chap_url for vol in chapter_data for chap_url in vol['chapters']]
            selected_indices = [int(i) - 1 for i in args.chapters]
            for index in selected_indices:
                if 0 <= index < len(all_chapters_flat):
                    selected_chapters_relative.append(all_chapters_flat[index])
                else:
                    print(f"[Cảnh báo] Bỏ qua chỉ số chương không hợp lệ: {index + 1}")
        else: # Mặc định là tải tất cả
            selected_chapters_relative.extend(chap for vol in chapter_data for chap in vol['chapters'])
    else:
        # Menu chọn chương/tập (chế độ tương tác)
        main_menu_items = ["Tải xuống tất cả", "Chọn tập để tải", "Chọn chương để tải"]
        main_menu = TerminalMenu(main_menu_items, title=" Tùy chọn tải xuống ", menu_cursor_style=("fg_cyan", "bold"), menu_highlight_style=("bg_cyan", "fg_black"))
        main_menu_selection_index = main_menu.show()

        if main_menu_selection_index == 0: # Tải tất cả
            for volume in chapter_data:
                selected_chapters_relative.extend(volume['chapters'])
        elif main_menu_selection_index == 1: # Chọn tập
            volume_titles = [volume['volume'] for volume in chapter_data]
            volume_menu = TerminalMenu(volume_titles, title=" Chọn tập (Space để chọn, Enter để xác nhận) ", multi_select=True, show_multi_select_hint=True, multi_select_cursor_style=("fg_yellow", "bold"))
            selected_volume_indices = volume_menu.show()
            if selected_volume_indices:
                for index in selected_volume_indices:
                    selected_chapters_relative.extend(chapter_data[index]['chapters'])
        elif main_menu_selection_index == 2: # Chọn chương
            all_chapters_for_menu = [(f"{vol['volume']}: {ch.split('/')[-1]}", ch) for vol in chapter_data for ch in vol['chapters']]
            chapter_menu_items = [item[0] for item in all_chapters_for_menu]
            chapter_menu = TerminalMenu(chapter_menu_items, title=" Chọn chương (Space để chọn, Enter để xác nhận) ", multi_select=True, show_multi_select_hint=True, multi_select_cursor_style=("fg_yellow", "bold"))
            selected_chapter_indices = chapter_menu.show()
            if selected_chapter_indices:
                for index in selected_chapter_indices:
                    selected_chapters_relative.append(all_chapters_for_menu[index][1])

    if not selected_chapters_relative:
        print("Không có chương nào được chọn. Đang thoát.")
        return
        
    base_url = "https://valvrareteam.net"
    chapter_urls = [base_url + rel_url for rel_url in selected_chapters_relative]
    
    # Chọn cách gộp và định dạng file
    if is_cli_mode:
        gop_map = {'rieng': 0, 'volume': 1, 'tatca': 2}
        gop_choice_index = gop_map[args.gop]
        formats_to_export = [f.upper() for f in args.format]
        font_name = args.font
        CONCURRENT_TASKS = args.tasks
    else:
        gop_menu_items = ["Xuất riêng từng chương (mặc định)", "Gộp các chương theo từng Volume", "Gộp tất cả chương đã chọn thành 1 file"]
        gop_menu = TerminalMenu(gop_menu_items, title=" Chọn cách thức xuất file ", menu_cursor_style=("fg_green", "bold"), menu_highlight_style=("bg_green", "fg_black"))
        gop_choice_index = gop_menu.show()
        
        format_items = ["PDF", "EPUB", "HTML", "Markdown (.md)", "Text (.txt)"]
        format_menu = TerminalMenu(format_items, title=" Chọn định dạng file (Space để chọn, Enter để xác nhận) ", multi_select=True, show_multi_select_hint=True, multi_select_cursor_style=("fg_yellow", "bold"))
        selected_format_indices = format_menu.show()
        if not selected_format_indices:
            print("Không có định dạng nào được chọn. Đang thoát.")
            return
        formats_to_export = [format_items[i] for i in selected_format_indices]
        
        font_name = 'DejaVuSans'
        if "PDF" in formats_to_export:
            font_choice = input("Chọn font cho PDF:\n1. Noto Serif\n2. DejaVu Sans (mặc định)\nLựa chọn của bạn (1/2, Enter để dùng mặc định): ").strip()
            if font_choice == '1':
                font_name = 'NotoSerif'

        CONCURRENT_TASKS_str = input("Nhập số lượng tác vụ song song tối đa (mặc định là 5): ")
        CONCURRENT_TASKS = int(CONCURRENT_TASKS_str) if CONCURRENT_TASKS_str.isdigit() and int(CONCURRENT_TASKS_str) > 0 else 5

    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)
    # ... (phần còn lại của logic tải và xử lý file giữ nguyên)
    
    print(f"Chuẩn bị tải {len(chapter_urls)} chương với tối đa {CONCURRENT_TASKS} tác vụ song song...")

    # Tạo cấu trúc thư mục trước
    tree_path = os.path.join(output_folder, "tree_map.txt")
    await get_chapter_tree_folder(url=trang_chinh, output_file=tree_path)
    create_folders_from_tree(tree_path, output_folder)
    
    # Dictionary để lưu content đã scrape
    scraped_content = {}
    
    async def process_url(browser, url):
        async with semaphore:
            content = await lay_chuong_voi_hinh_anh(browser, url)
            if content:
                scraped_content[url] = content
            else:
                skipped_urls.append(url)
                print(f"Đã thêm {url} vào danh sách các chương bị bỏ qua.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        tasks = [process_url(browser, url) for url in chapter_urls]
        with alive_bar(len(tasks), title=f"Đang tải nội dung", bar='filling', spinner='dots_waves') as bar:
            for future in asyncio.as_completed(tasks):
                await future
                bar()
        await browser.close()
    
    print("Đã tải xong nội dung. Bắt đầu tạo file...")
    
    # --- Xử lý tạo file sau khi đã scrape ---
    
    # Build a map from relative url to volume name
    url_to_volume_map = {}
    for vol_info in chapter_data:
        for chap_url in vol_info['chapters']:
            url_to_volume_map[chap_url] = vol_info['volume']

    # 1. Xuất riêng từng chương
    if gop_choice_index == 0:
        for url in chapter_urls:
            if url in scraped_content:
                relative_url = url.replace(base_url, "")
                volume_name = url_to_volume_map.get(relative_url, "Unknown Volume")
                current_folder = os.path.join(output_folder, sanitize_filename(volume_name))
                os.makedirs(current_folder, exist_ok=True)
                
                ten_chuong = url.split("/")[-1]
                content_list = scraped_content[url]
                author = story_info.get("author", "Valvrare Team (Scraped)")
                description = story_info.get("description", "")
                cover_path = story_info.get("cover_path", None)

                for fmt in formats_to_export:
                    file_path = os.path.join(current_folder, f"{ten_chuong}.{fmt.lower().split(' ')[0].replace('(.md)', '.md').replace('(.txt)', '.txt')}")
                    if fmt == "PDF":
                        tao_file_pdf(content_list, file_path, ten_chuong, font_name)
                    elif fmt == "EPUB":
                        chapters_data = [{'title': ten_chuong, 'content': content_list}]
                        tao_file_epub(file_path, ten_chuong, author, chapters_data, description, cover_path)
                    elif fmt == "HTML":
                        tao_file_html(content_list, file_path, ten_chuong)
                    elif fmt == "Markdown (.md)":
                        tao_file_md(content_list, file_path, ten_chuong)
                    elif fmt == "Text (.txt)":
                        tao_file_txt(content_list, file_path, ten_chuong)
                        
    # 2. Gộp theo Volume
    elif gop_choice_index == 1:
        volume_contents = {}
        for url in chapter_urls:
            if url in scraped_content:
                relative_url = url.replace(base_url, "")
                volume_name = url_to_volume_map.get(relative_url, "Unknown Volume")
                if volume_name not in volume_contents:
                    volume_contents[volume_name] = []
                
                ten_chuong = url.split("/")[-1]
                volume_contents[volume_name].append({
                    'title': ten_chuong,
                    'content': scraped_content[url]
                })

        author = story_info.get("author", "Valvrare Team (Scraped)")
        description = story_info.get("description", "")
        cover_path = story_info.get("cover_path", None)

        for volume_name, chapters_list in volume_contents.items():
            sanitized_vol_name = sanitize_filename(volume_name)
            # Volume folder is not strictly needed when merging, but let's keep it clean
            current_folder = os.path.join(output_folder, sanitized_vol_name)
            os.makedirs(current_folder, exist_ok=True)
            
            # Use the full content of the volume for PDF and other simple formats
            full_volume_content = []
            for chap in chapters_list:
                full_volume_content.extend(chap['content'])

            for fmt in formats_to_export:
                file_path = os.path.join(current_folder, f"{sanitized_vol_name}.{fmt.lower().split(' ')[0].replace('(.md)', '.md').replace('(.txt)', '.txt')}")
                if fmt == "PDF":
                    tao_file_pdf(full_volume_content, file_path, volume_name, font_name)
                elif fmt == "EPUB":
                    tao_file_epub(file_path, volume_name, author, chapters_list, description, cover_path)
                elif fmt == "HTML":
                    tao_file_html(full_volume_content, file_path, volume_name)
                elif fmt == "Markdown (.md)":
                    tao_file_md(full_volume_content, file_path, volume_name)
                elif fmt == "Text (.txt)":
                    tao_file_txt(full_volume_content, file_path, volume_name)

    # 3. Gộp tất cả
    elif gop_choice_index == 2:
        full_story_structure = []
        full_content_list_simple = []
        
        # Preserve the original volume and chapter order from chapter_data
        for volume_info in chapter_data:
            volume_title = volume_info['volume']
            chapters_in_volume = []
            
            # Filter for selected chapters only
            for relative_url in volume_info['chapters']:
                full_url = base_url + relative_url
                if full_url in scraped_content:
                    chapter_title = relative_url.split('/')[-1]
                    content = scraped_content[full_url]
                    chapters_in_volume.append({'title': chapter_title, 'content': content})
                    full_content_list_simple.extend(content)
            
            if chapters_in_volume:
                full_story_structure.append({'volume': volume_title, 'chapters': chapters_in_volume})

        sanitized_story_name = sanitize_filename(ten_truyen_raw)
        author = story_info.get("author", "Valvrare Team (Scraped)")
        description = story_info.get("description", "")
        cover_path = story_info.get("cover_path", None)

        for fmt in formats_to_export:
            file_path = os.path.join(output_folder, f"{sanitized_story_name}.{fmt.lower().split(' ')[0].replace('(.md)', '.md').replace('(.txt)', '.txt')}")
            if fmt == "PDF":
                tao_file_pdf(full_content_list_simple, file_path, ten_truyen_raw, font_name)
            elif fmt == "EPUB":
                tao_file_epub(file_path, ten_truyen_raw, author, full_story_structure, description, cover_path)
            elif fmt == "HTML":
                tao_file_html(full_content_list_simple, file_path, ten_truyen_raw)
            elif fmt == "Markdown (.md)":
                tao_file_md(full_content_list_simple, file_path, ten_truyen_raw)
            elif fmt == "Text (.txt)":
                tao_file_txt(full_content_list_simple, file_path, ten_truyen_raw)
                
    print("\n--- HOÀN TẤT ---")
    if skipped_urls:
        log_file_path = os.path.join(output_folder, "cac_chuong_da_bo_qua.txt")
        print(f"(!) Cảnh báo: {len(skipped_urls)} chương đã bị bỏ qua do lỗi.")
        print(f"Đang ghi danh sách các chương bị lỗi vào file: {log_file_path}")
        with open(log_file_path, "w", encoding="utf-8") as f:
            for url in skipped_urls:
                f.write(f"{url}\n")
    

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nChương trình bị dừng bởi người dùng.")
    finally:
        if os.path.exists("chapter_list.json"):
            os.remove("chapter_list.json")
        print("Đã dọn dẹp file tạm. Hẹn gặp lại!")
