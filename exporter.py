"""
File export functions for the web novel scraper.
"""
import os
import urllib.parse
from io import BytesIO
from typing import List, Dict, Any, Union, cast

import httpx
from ebooklib import epub
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

from utils import HEADERS
from models import StoryInfo, ContentItem, Chapter, Volume


ContentItemLike = Union[ContentItem, Dict[str, str]]
ContentList = List[ContentItemLike]
ChapterData = Dict[str, Any]  # {'title': str, 'content': ContentList}
VolumeData = Dict[str, Any]   # {'volume': str, 'chapters': List[ChapterData]}
ChaptersData = List[Union[ChapterData, VolumeData]]


def _normalize_content_item(item: ContentItemLike) -> ContentItem:
    """Convert dict to ContentItem if needed."""
    if isinstance(item, ContentItem):
        return item
    return ContentItem(type=cast(str, item['type']), data=cast(str, item['data']))


def _normalize_content_list(items: ContentList) -> List[ContentItem]:
    """Convert list of dicts to list of ContentItems."""
    return [_normalize_content_item(item) for item in items]


def tao_file_epub(
    filename: str,
    book_title: str,
    author: str,
    chapters_data: ChaptersData,
    description: str = "",
    cover_path: Union[str, None] = None
) -> None:
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

    def process_chapter(chap_data: ChapterData, chap_idx: int) -> epub.EpubHtml:
        nonlocal image_counter
        chap_title = chap_data.get('title', f"Chương {chap_idx}")
        chap_filename = f'chap_{chap_idx}.xhtml'
        chapter_obj = epub.EpubHtml(title=chap_title, file_name=chap_filename, lang='vi')

        html_content = f'<h1>{chap_title}</h1>'
        for item in chap_data.get('content', []):
            normalized_item = _normalize_content_item(item)
            if normalized_item.type == 'text':
                html_content += f'<p>{normalized_item.data}</p>'
            elif normalized_item.type == 'image':
                try:
                    img_url = normalized_item.data
                    # Basic check for valid image URL
                    if not img_url.startswith(('http://', 'https://')):
                        raise ValueError("Invalid image URL")

                    with httpx.Client(headers=HEADERS, timeout=30.0) as img_client:
                        response = img_client.get(img_url)
                    response.raise_for_status()
                    img_content = response.content

                    # Determine image extension
                    img_extension = 'jpg'  # default
                    parsed_url = urllib.parse.urlparse(img_url)
                    path_parts = parsed_url.path.split('.')
                    if len(path_parts) > 1:
                        img_extension = path_parts[-1].lower()

                    # Ensure extension is valid for epub
                    if img_extension not in ['jpg', 'jpeg', 'png', 'gif', 'svg']:
                        # Attempt to get mimetype and decide extension
                        try:
                            content_type = response.headers['Content-Type']
                            if 'jpeg' in content_type:
                                img_extension = 'jpg'
                            elif 'png' in content_type:
                                img_extension = 'png'
                            # ... add other mimetypes if needed
                        except (KeyError, IndexError):
                            img_extension = 'jpg'  # fallback

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
                    print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh cho EPUB: {normalized_item.data}. Lỗi: {e}")

        chapter_obj.content = html_content
        return chapter_obj

    chapter_index = 1
    for item in chapters_data:
        if 'volume' in item:  # It's a volume
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

        elif 'title' in item:  # It's a standalone chapter
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


def tao_file_pdf(
    content_list: ContentList,
    filename: str,
    title: str = "Chương truyện",
    font_name: str = 'DejaVuSans'
) -> None:
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
                with httpx.Client(headers=HEADERS, timeout=30.0) as font_client:
                    response = font_client.get(url, stream=True)
                response.raise_for_status()
                with open(font_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
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

    normalized_items = _normalize_content_list(content_list)
    for item in normalized_items:
        if item.type == 'text':
            p = Paragraph(item.data, style)
            story.append(p)
            story.append(Spacer(1, 0.1 * inch))
        elif item.type == 'image':
            try:
                with httpx.Client(headers=HEADERS, timeout=30.0) as img_client:
                    response = img_client.get(item.data)
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
                print(f"  [Cảnh báo] Không thể tải hoặc xử lý ảnh cho PDF: {item.data}. Lỗi: {e}")

    try:
        doc.build(story)
        print(f"Tạo file PDF thành công: {filename}")
    except Exception as e:
        # Note: skipped_urls is handled elsewhere
        print(f"!!! LỖI NGHIÊM TRỌNG: Không thể tạo file PDF '{filename}'. Lý do: {e}")


def tao_file_html(
    content_list: ContentList,
    filename: str,
    title: str = "Chương truyện"
) -> None:
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
    normalized_items = _normalize_content_list(content_list)
    for item in normalized_items:
        if item.type == 'text':
            html_content += f'    <p>{item.data}</p>\n'
        elif item.type == 'image':
            html_content += f'    <img src="{item.data}" alt="Hình minh họa"/>\n'

    html_content += "</body>\n</html>"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Tạo file HTML thành công: {filename}")
    except Exception as e:
        print(f"!!! LỖI: Không thể tạo file HTML '{filename}'. Lý do: {e}")


def tao_file_md(
    content_list: ContentList,
    filename: str,
    title: str = "Chương truyện"
) -> None:
    """Creates a Markdown file from a list of content."""
    print(f"Đang tạo file Markdown: {filename}...")
    md_content = f"# {title}\n\n"
    normalized_items = _normalize_content_list(content_list)
    for item in normalized_items:
        if item.type == 'text':
            md_content += f'{item.data}\n\n'
        elif item.type == 'image':
            md_content += f'![Hình minh họa]({item.data})\n\n'

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"Tạo file Markdown thành công: {filename}")
    except Exception as e:
        print(f"!!! LỖI: Không thể tạo file MD '{filename}'. Lý do: {e}")


def tao_file_txt(
    content_list: ContentList,
    filename: str,
    title: str = "Chương truyện"
) -> None:
    """Creates a plain text file from a list of content."""
    print(f"Đang tạo file Text: {filename}...")
    txt_content = f"{title}\n\n"
    normalized_items = _normalize_content_list(content_list)
    for item in normalized_items:
        if item.type == 'text':
            txt_content += f'{item.data}\n\n'
        elif item.type == 'image':
            txt_content += f'[Hình minh họa: {item.data}]\n\n'

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        print(f"Tạo file Text thành công: {filename}")
    except Exception as e:
        print(f"!!! LỖI: Không thể tạo file TXT '{filename}'. Lý do: {e}")