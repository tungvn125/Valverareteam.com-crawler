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

def tao_file_epub(content_list, filename, title="Chương truyện"):
    """Creates an EPUB file from a list of content."""
    print(f"Đang tạo file EPUB: {filename}...")
    book = epub.EpubBook()
    book.set_identifier('id123456')
    book.set_title(title)
    book.set_language('vi')
    book.add_author('Valvrare Team (Scraped)')
    
    html_content = f'<h1>{title}</h1>'
    image_counter = 1
    chapter = epub.EpubHtml(title=title, file_name='chap_01.xhtml', lang='vi')
    
    # Create a directory for images inside the epub if it doesn't exist
    if not any(isinstance(item, epub.EpubImage) for item in book.items):
        book.add_item(epub.EpubItem(file_name="images/", media_type="application/x-dtbncx+xml"))

    for item in content_list:
        if item['type'] == 'text':
            html_content += f'<p>{item["data"]}</p>'
        elif item['type'] == 'image':
            try:
                img_url = item["data"]
                response = requests.get(img_url)
                response.raise_for_status()
                img_content = response.content
                img_extension = img_url.split('.')[-1].lower().split('?')[0] # Handle cases with URL params
                if not img_extension: img_extension = 'jpg'

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
                print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh cho EPUB: {item['data']}. Lỗi: {e}")

    chapter.content = html_content
    book.add_item(chapter)
    book.toc = (epub.Link('chap_01.xhtml', title, 'intro'),)
    book.spine = ['nav', chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(filename, book, {})
    print(f"Tạo file EPUB thành công: {filename}")


def tao_file_pdf(content_list, filename, title="Chương truyện", font_name='DejaVuSans'):
    """Creates a PDF file from a list of content."""
    print(f"Đang tạo file PDF: {filename}...")
    valid_fonts = ['DejaVuSans', 'NotoSerif']
    if font_name not in valid_fonts:
        print(f"[Cảnh báo] Font '{font_name}' không hợp lệ. Sử dụng font mặc định 'DejaVuSans'.")
        font_name = 'DejaVuSans'

    font_filename_map = {'DejaVuSans': 'DejaVuSans.ttf', 'NotoSerif': 'NotoSerif-Regular.ttf'}
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

async def main():
    sitemap_url = "https://valvrareteam.net/sitemap.xml"
    response = requests.get(sitemap_url)
    soup = BeautifulSoup(response.content, "lxml-xml")
    
    ten_truyen_raw = input("Nhập tên truyện bạn muốn tải: ")
    ten_truyen_normalized = ten_truyen_raw.lower().replace(" ", "-")
    output_folder = sanitize_filename(ten_truyen_raw.strip())
    os.makedirs(output_folder, exist_ok=True)
    
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

    trang_chinh = None
    for loc in soup.find_all("loc"):
        url = loc.text
        if ten_truyen_normalized in url and "/chuong" not in url:
            trang_chinh = url
            break
    
    if not trang_chinh:
        print(f"Không tìm thấy truyện '{ten_truyen_raw}'. Vui lòng kiểm tra lại tên truyện.")
        return

    print("Đang lấy danh sách chương từ trang chính của truyện...")
    await get_chapter_tree_list(trang_chinh, output_file="chapter_list.json")
    await asyncio.sleep(1)
    
    try:
        with open("chapter_list.json", "r", encoding="utf-8") as f:
            chapter_data = json.load(f)
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đọc file chapter_list.json: {e}")
        return

    # Lọc chương minh họa
    minh_hoa_choice = input("Bạn có muốn bỏ qua các chương minh họa không? (Y/n): ").strip().lower()
    if not minh_hoa_choice or minh_hoa_choice in ["y", "yes"]:
        print("Bạn đã chọn bỏ qua các chương minh họa.")
        for volume_data in chapter_data:
            volume_data['chapters'] = [ch for ch in volume_data['chapters'] if 'minh-hoa' not in ch]
        chapter_data = [vol for vol in chapter_data if vol['chapters']]

    if not chapter_data:
        print("Không có chương nào để tải sau khi đã lọc.")
        return

    # Menu chọn chương/tập
    main_menu_items = ["Tải xuống tất cả", "Chọn tập để tải", "Chọn chương để tải"]
    main_menu = TerminalMenu(main_menu_items, title=" Tùy chọn tải xuống ", menu_cursor_style=("fg_cyan", "bold"), menu_highlight_style=("bg_cyan", "fg_black"))
    main_menu_selection_index = main_menu.show()

    selected_chapters_relative = []
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
    
    # Menu chọn cách gộp file
    gop_menu_items = ["Xuất riêng từng chương (mặc định)", "Gộp các chương theo từng Volume", "Gộp tất cả chương đã chọn thành 1 file"]
    gop_menu = TerminalMenu(gop_menu_items, title=" Chọn cách thức xuất file ", menu_cursor_style=("fg_green", "bold"), menu_highlight_style=("bg_green", "fg_black"))
    gop_choice_index = gop_menu.show()
    
    # Menu chọn định dạng
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

                for fmt in formats_to_export:
                    if fmt == "PDF":
                        tao_file_pdf(content_list, os.path.join(current_folder, f"{ten_chuong}.pdf"), ten_chuong, font_name)
                    elif fmt == "EPUB":
                        tao_file_epub(content_list, os.path.join(current_folder, f"{ten_chuong}.epub"), ten_chuong)
                    elif fmt == "HTML":
                        tao_file_html(content_list, os.path.join(current_folder, f"{ten_chuong}.html"), ten_chuong)
                    elif fmt == "Markdown (.md)":
                        tao_file_md(content_list, os.path.join(current_folder, f"{ten_chuong}.md"), ten_chuong)
                    elif fmt == "Text (.txt)":
                        tao_file_txt(content_list, os.path.join(current_folder, f"{ten_chuong}.txt"), ten_chuong)
                        
    # 2. Gộp theo Volume
    elif gop_choice_index == 1:
        volume_contents = {}
        for url in chapter_urls:
            if url in scraped_content:
                relative_url = url.replace(base_url, "")
                volume_name = url_to_volume_map.get(relative_url, "Unknown Volume")
                if volume_name not in volume_contents:
                    volume_contents[volume_name] = []
                volume_contents[volume_name].extend(scraped_content[url])
        
        for volume_name, content_list in volume_contents.items():
            sanitized_vol_name = sanitize_filename(volume_name)
            current_folder = os.path.join(output_folder, sanitized_vol_name)
            os.makedirs(current_folder, exist_ok=True)
            
            for fmt in formats_to_export:
                if fmt == "PDF":
                    tao_file_pdf(content_list, os.path.join(current_folder, f"{sanitized_vol_name}.pdf"), volume_name, font_name)
                elif fmt == "EPUB":
                    tao_file_epub(content_list, os.path.join(current_folder, f"{sanitized_vol_name}.epub"), volume_name)
                elif fmt == "HTML":
                    tao_file_html(content_list, os.path.join(current_folder, f"{sanitized_vol_name}.html"), volume_name)
                elif fmt == "Markdown (.md)":
                    tao_file_md(content_list, os.path.join(current_folder, f"{sanitized_vol_name}.md"), volume_name)
                elif fmt == "Text (.txt)":
                    tao_file_txt(content_list, os.path.join(current_folder, f"{sanitized_vol_name}.txt"), volume_name)

    # 3. Gộp tất cả
    elif gop_choice_index == 2:
        full_content_list = []
        for url in chapter_urls: # Iterate in order
            if url in scraped_content:
                full_content_list.extend(scraped_content[url])
        
        sanitized_story_name = sanitize_filename(ten_truyen_raw)
        for fmt in formats_to_export:
            if fmt == "PDF":
                tao_file_pdf(full_content_list, os.path.join(output_folder, f"{sanitized_story_name}.pdf"), ten_truyen_raw, font_name)
            elif fmt == "EPUB":
                tao_file_epub(full_content_list, os.path.join(output_folder, f"{sanitized_story_name}.epub"), ten_truyen_raw)
            elif fmt == "HTML":
                tao_file_html(full_content_list, os.path.join(output_folder, f"{sanitized_story_name}.html"), ten_truyen_raw)
            elif fmt == "Markdown (.md)":
                tao_file_md(full_content_list, os.path.join(output_folder, f"{sanitized_story_name}.md"), ten_truyen_raw)
            elif fmt == "Text (.txt)":
                tao_file_txt(full_content_list, os.path.join(output_folder, f"{sanitized_story_name}.txt"), ten_truyen_raw)
                
    print("\n--- HOÀN TẤT ---")
    if skipped_urls:
        log_file_path = os.path.join(output_folder, "cac_chuong_da_bo_qua.txt")
        print(f"(!) Cảnh báo: {len(skipped_urls)} chương đã bị bỏ qua do lỗi.")
        print(f"Đang ghi danh sách các chương bị lỗi vào file: {log_file_path}")
        with open(log_file_path, "w", encoding="utf-8") as f:
            for url in skipped_urls:
                f.write(f"{url}\n")
    
    # Cleanup
    if os.path.exists("chapter_list.json"):
        os.remove("chapter_list.json")
    if os.path.exists(tree_path):
        os.remove(tree_path)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nChương trình bị dừng bởi người dùng.")
    finally:
        if os.path.exists("chapter_list.json"):
            os.remove("chapter_list.json")
        print("Đã dọn dẹp file tạm. Hẹn gặp lại!")
