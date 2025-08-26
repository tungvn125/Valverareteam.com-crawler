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
skipped_urls = []
def scrape_chapter_urls():
    sitemap_url = "https://valvrareteam.net/sitemap.xml"
    response = requests.get(sitemap_url)
    soup = BeautifulSoup(response.content, "lxml-xml")
    ten_truyen_raw = input("Nhập tên truyện bạn muốn tải: ")
    ten_truyen = ten_truyen_raw.lower().replace(" ", "-")
    output_folder = ten_truyen_raw.strip()
    os.makedirs(output_folder, exist_ok=True)
    vietnamese_map = {
        'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a', 'ă': 'a', 'ằ': 'a',
        'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a', 'â': 'a', 'ầ': 'a', 'ấ': 'a',
        'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a', 'đ': 'd', 'è': 'e', 'é': 'e', 'ẻ': 'e',
        'ẽ': 'e', 'ẹ': 'e', 'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e',
        'ệ': 'e', 'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i', 'ò': 'o',
        'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o', 'ô': 'o', 'ồ': 'o', 'ố': 'o',
        'ổ': 'o', 'ỗ': 'o', 'ộ': 'o', 'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o',
        'ỡ': 'o', 'ợ': 'o', 'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u', 'ỳ': 'y',
        'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    }
    for key, value in vietnamese_map.items():
        ten_truyen = ten_truyen.replace(key, value)
    chapter_urls = []
    for loc in soup.find_all("loc"):
        url = loc.text
        if ten_truyen in url and "/chuong/" in url:
            chapter_urls.append(url)
        if ten_truyen in url and "/chuong" not in url:
            trang_chinh = url
            

    while True:
        try:
            minh_hoa_choice = input("Bạn có muốn bỏ qua các chương minh họa không? (Y/n): ").strip().lower()
            if not minh_hoa_choice:
                print("Bạn đã chọn bỏ qua các chương minh họa.")
                chapter_urls = [url for url in chapter_urls if "minh-hoa" not in url]
                break
            if minh_hoa_choice == "y" or minh_hoa_choice == "yes":
                print("Bạn đã chọn bỏ qua các chương minh họa.")
                chapter_urls = [url for url in chapter_urls if "minh-hoa" not in url]
                break
            elif minh_hoa_choice == "n" or minh_hoa_choice == "no":
                print("Bạn đã chọn không bỏ qua các chương minh họa.")
                break
            else:
                print("Lựa chọn không hợp lệ, vui lòng chỉ nhập y hoặc n.")
        except ValueError:
            print("Vui lòng nhập lại.")
    print(f"Đã tìm thấy {len(chapter_urls)} chương truyện")

    return chapter_urls, output_folder, trang_chinh
MAX_RETRIES = 2
async def lay_chuong_voi_hinh_anh(browser, url):
    page = await browser.new_page()
    for attempt in range(MAX_RETRIES):
        try:
            #print(f"Đang truy cập URL: {url} (Lần thử {attempt + 1}/{MAX_RETRIES})")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            #print("Trang đã tải xong. Bắt đầu trích xuất nội dung...")
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
def tao_file_epub(content_list, filename, title="Chương truyện"):
    #print(f"Đang tạo file EPUB: {filename}...")
    book = epub.EpubBook()
    book.set_identifier('id123456')
    book.set_title(title)
    book.set_language('vi')
    book.add_author('Valvrare Team (Scraped)')
    html_content = f'<h1>{title}</h1>'
    image_counter = 1
    chapter = epub.EpubHtml(title=title, file_name='chap_01.xhtml', lang='vi')
    for item in content_list:
        if item['type'] == 'text':
            html_content += f'<p>{item["data"]}</p>'
        elif item['type'] == 'image':
            try:
                img_url = item["data"]
                response = requests.get(img_url)
                response.raise_for_status()
                img_content = response.content
                img_extension = img_url.split('.')[-1].lower()
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
                print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh: {item['data']}. Lỗi: {e}")
    chapter.content = html_content
    book.add_item(chapter)
    book.toc = (epub.Link('chap_01.xhtml', title, 'intro'),)
    book.spine = ['nav', chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(filename, book, {})
    #print(f"Tạo file EPUB thành công: {filename}")
def tao_file_pdf(content_list, filename, title="Chương truyện", font_name='DejaVuSans'):
    valid_fonts = ['DejaVuSans', 'NotoSerif']
    if font_name not in valid_fonts:
        print(f"[Cảnh báo] Font '{font_name}' không hợp lệ. Sử dụng font mặc định 'DejaVuSans'.")
        font_name = 'DejaVuSans'
    #print(f"Đang tạo file PDF: {filename}...")
    try:
        pdfmetrics.registerFont(TTFont(f"{font_name}", f'{font_name}.ttf'))
        style = ParagraphStyle(name='Normal_vi', fontName=font_name, fontSize=12, leading=14)
        title_style = ParagraphStyle(name='Title_vi', fontName=font_name, fontSize=18, leading=22,
                                     spaceAfter=0.2 * inch)
    except Exception:
        print(f"[Cảnh báo] Không tìm thấy font '{font_name}.ttf'. Tiếng Việt có thể hiển thị lỗi.")
        print("Vui lòng tải font tại: https://dejavu-fonts.github.io/")
        styles = getSampleStyleSheet()
        style = styles['Normal']
        title_style = styles['h1']
    doc = SimpleDocTemplate(filename)
    story = [Paragraph(title, title_style), Spacer(1, 0.2 * inch)]
    max_width = doc.width
    max_height = doc.height
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
                width_ratio = max_width / img_width
                height_ratio = max_height / img_height
                scale_ratio = min(width_ratio, height_ratio)
                if scale_ratio < 1:
                    new_width = img_width * scale_ratio
                    new_height = img_height * scale_ratio
                    img = Image(BytesIO(response.content), width=new_width, height=new_height)
                else:
                    img = Image(BytesIO(response.content), width=img_width, height=img_height)
                story.append(img)
                story.append(Spacer(1, 0.1 * inch))
            except Exception as e:
                print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh: {item['data']}. Lỗi: {e}")
    try:
        doc.build(story)
        #print(f"Tạo file PDF thành công: {filename}")
    except Exception as e:
        skipped_urls.append(filename + " (Lỗi: " + str(e) + ")" + "pdf")
        print(f"!!! LỖI NGHIÊM TRỌNG: Không thể tạo file PDF cho '{title}'. Lý do: {e}")
        print("!!! Chương này sẽ bị bỏ qua.")

#create folder base on tree map
def create_folders_from_tree(tree_file, base_folder):
    with open(tree_file, 'r', encoding='utf-8') as f:
        tree_data = f.readlines()
    for line in tree_data:
        folder_name = line.strip()
        folder_path = os.path.join(base_folder, folder_name)
        os.makedirs(folder_path, exist_ok=True)

async def main():
    chapter_urls, output_folder, trang_chinh = scrape_chapter_urls()
    tree_path = os.path.join(output_folder, "tree_map.txt")
    await get_chapter_tree_list(trang_chinh, output_file="chapter_list.json")  # Tạo file chapter_list.json
    await asyncio.sleep(2)  # Đợi 2 giây để đảm bảo file được ghi xong
    try:
        with open("chapter_list.json", "r", encoding="utf-8") as f:
            chapter_data = json.load(f)
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đọc file chapter_list.json: {e}")
        return
    #get_chapters_by_volume_index(file_path="chapter_list.json", index=0)  # Ví dụ lấy chương của tập đầu tiên
    #print(len(chapter_data))
    
    await get_chapter_tree_folder(url=trang_chinh, output_file=tree_path)  # Tạo file tree_map.txt
    create_folders_from_tree(tree_path, output_folder)
    if not chapter_urls:
        print("Không tìm thấy chương nào trong sitemap.")
        return
    print("Vui lòng chọn định dạng file bạn muốn lưu chương truyện:")
    print("1. PDF")
    print("2. EPUB")
    print("3. Cả 2 định dạng")
    choice = ''
    while choice not in ['1', '2', '3']:
        choice = input("Bạn muốn lưu file dưới dạng nào? (1,2,3): ").lower()
    file_format_choice = ''
    if choice == '1':
        file_format_choice = 'pdf'
        while True:
            try:
                print("1. Noto Serif")
                print("2. DejaVu Sans (mặc định)")
                font_choice_str = input("Bạn muốn sử dụng font nào? (Nhập 1 hoặc 2, nhấn Enter để dùng mặc định): ")
                if not font_choice_str:  
                    break
                font_choice = int(font_choice_str)
                if font_choice == 1:
                    font_name = 'NotoSerif'
                    break
                elif font_choice == 2:
                    font_name = 'DejaVuSans'
                    break
                else:
                    print("Lựa chọn không hợp lệ, vui lòng chỉ nhập 1 hoặc 2.")
            except ValueError:
                print("Đây không phải là một con số! Vui lòng nhập lại.")
    elif choice == '2':
        file_format_choice = 'epub'
    elif choice == '3':
        file_format_choice = 'both'
    
    print(f"Tất cả các file sẽ được lưu trong thư mục: '{output_folder}'")
    CONCURRENT_TASKS = input("Nhập số lượng tác vụ song song tối đa (mặc định là 5): ")
    if not CONCURRENT_TASKS.isdigit():
        CONCURRENT_TASKS = 5
    else:
        CONCURRENT_TASKS = int(CONCURRENT_TASKS)
    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)
    async def process_url(browser, url, folder, skipped_urls):
        async with semaphore:
            content = await lay_chuong_voi_hinh_anh(browser, url)
            url_ = url.replace("https://valvrareteam.net", "")
            print(url_)
            for n in range(0,len(chapter_data)):
                if url_ in get_chapters_by_volume_index(file_path="chapter_list.json", index=n):
                    folder = f"{output_folder}\{chapter_data[n]['volume']}"
                else:
                    continue
            ten_chuong = url.split("/")[-1]
            if content:
                pdf_path = os.path.join(folder, f"{ten_chuong}.pdf")
                epub_path = os.path.join(folder, f"{ten_chuong}.epub")
                if file_format_choice in ['pdf', 'both']:
                    tao_file_pdf(content, pdf_path, title=ten_chuong, font_name=font_name)
                if file_format_choice in ['epub', 'both']:
                    tao_file_epub(content, epub_path, title=ten_chuong)
            else:
                skipped_urls.append(url)
                print(f"Đã thêm {url} vào danh sách các chương bị bỏ qua.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        print(
            f"Đã khởi động trình duyệt. Sẽ tải {len(chapter_urls)} chương với tối đa {CONCURRENT_TASKS} tác vụ song song.")
        tasks = [process_url(browser, url, output_folder, skipped_urls) for url in chapter_urls]
        with alive_bar(len(tasks), title=f"Đang tải truyện", bar='filling', spinner='dots_waves') as bar:
            for future in asyncio.as_completed(tasks):
                try:
                    await future
                except Exception as e:
                    print(f"Một tác vụ đã gặp lỗi: {e}")
                bar() # Cập nhật thanh tiến trình sau mỗi chương hoàn thành
        await browser.close()
        print("Hoàn tất! Đã đóng trình duyệt.")
    if skipped_urls:
        log_file_path = os.path.join(output_folder, "cac chuong da bo qua")
        print(f"Đang ghi danh sách các chương bị lỗi vào file: {log_file_path}")
        with open(log_file_path, "w", encoding="utf-8") as f:
            for url in skipped_urls:
                f.write(f"{url}\n")
    os.remove(f"{output_folder}\tree_map.txt")
    get_chapter_tree(url=trang_chinh, output_file=f"{output_folder}\tree_map.txt")
if __name__ == "__main__":
    asyncio.run(main())
    os.remove("chapter_list.json")