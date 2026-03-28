"""
File export functions for the web novel scraper.
"""
import os
import asyncio
import urllib.parse
from io import BytesIO
from typing import List, Dict, Any, Union, cast, Optional

import httpx
# Heavy AI libraries (numpy, vieneu) are lazy-loaded inside tao_file_mp3 
# to ensure a fast cold start for the CLI and Web UI.
from ebooklib import epub
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
from loguru import logger
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .utils import HEADERS
from .models import StoryInfo, ContentItem, Chapter, Volume


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


async def _download_images_bulk(urls: List[str], max_concurrent: int = 10) -> Dict[str, bytes]:
    """Downloads multiple images concurrently with a limit on parallelism and a progress bar."""
    if not urls:
        return {}

    unique_urls = list(set(urls))
    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}

    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Đang tải ảnh minh họa...", total=len(unique_urls))
            
            async def download(url: str):
                async with semaphore:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        progress.update(task, advance=1)
                        return url, response.content
                    except Exception as e:
                        logger.warning(f"Lỗi khi tải ảnh {url}: {e}")
                        progress.update(task, advance=1)
                        return url, None

            tasks = [download(url) for url in unique_urls]
            downloaded = await asyncio.gather(*tasks)
            for url, content in downloaded:
                if content:
                    results[url] = content
    return results


def _get_image_extension(url: str, content_type: Optional[str] = None) -> str:
    """Detects image extension from URL or Content-Type header."""
    if content_type:
        if 'jpeg' in content_type: return 'jpg'
        if 'png' in content_type: return 'png'
        if 'gif' in content_type: return 'gif'
        if 'svg' in content_type: return 'svg'
    
    parsed_url = urllib.parse.urlparse(url)
    ext = parsed_url.path.split('.')[-1].lower()
    return ext if ext in ['jpg', 'jpeg', 'png', 'gif', 'svg'] else 'jpg'


async def tao_file_epub(
    filename: str,
    book_title: str,
    author: str,
    chapters_data: ChaptersData,
    description: str = "",
    cover_path: Union[str, None] = None,
    genres: List[str] = None
) -> None:
    """Creates an EPUB file with pre-fetched images for high performance."""
    logger.info(f"Đang tạo file EPUB: {filename}")
    
    # 1. Extract all image URLs
    all_image_urls = []
    for item in chapters_data:
        chaps = item.get('chapters', []) if 'chapters' in item else [item]
        for chap in chaps:
            for ci in chap.get('content', []):
                norm = _normalize_content_item(ci)
                if norm.type == 'image': all_image_urls.append(norm.data)
    
    # 2. Pre-download all images concurrently
    image_cache = await _download_images_bulk(all_image_urls)

    # 3. Build EPUB
    book = epub.EpubBook()
    book.set_identifier(f'urn:uuid:{os.path.basename(filename)}')
    book.set_title(book_title)
    book.set_language('vi')
    book.add_author(author)
    book.add_metadata('DC', 'description', description)
    if genres:
        for g in genres: book.add_metadata('DC', 'subject', g)

    if cover_path and os.path.exists(cover_path):
        try:
            with open(cover_path, 'rb') as cf:
                book.set_cover("cover.jpg", cf.read())
        except Exception:
            pass

    toc = []
    spine = ['nav']
    url_to_internal_path = {}
    image_counter = 1

    # Map pre-downloaded images to EPUB items
    for url, content in image_cache.items():
        ext = _get_image_extension(url)
        img_name = f'image_{image_counter}.{ext}'
        img_item = epub.EpubImage(
            uid=f'img_{image_counter}',
            file_name=f'images/{img_name}',
            media_type=f'image/{ext}',
            content=content
        )
        book.add_item(img_item)
        url_to_internal_path[url] = f'images/{img_name}'
        image_counter += 1

    def process_chapter(chap_data: ChapterData, chap_idx: int) -> epub.EpubHtml:
        title = chap_data.get('title', f"Chương {chap_idx}")
        chapter_obj = epub.EpubHtml(title=title, file_name=f'chap_{chap_idx}.xhtml', lang='vi')
        html = f'<h1>{title}</h1>'
        for item in chap_data.get('content', []):
            norm = _normalize_content_item(item)
            if norm.type == 'text':
                html += f'<p>{norm.data}</p>'
            elif norm.type == 'image' and norm.data in url_to_internal_path:
                html += f'<img src="{url_to_internal_path[norm.data]}" alt="Minh họa"/>'
        chapter_obj.content = html
        return chapter_obj

    # Assemble structure
    chapter_index = 1
    for item in chapters_data:
        if 'volume' in item:
            vol_title = item['volume']
            vol_chaps = []
            for c_data in item.get('chapters', []):
                chap_obj = process_chapter(c_data, chapter_index)
                book.add_item(chap_obj)
                spine.append(chap_obj)
                vol_chaps.append(epub.Link(chap_obj.file_name, chap_obj.title, f'ch_{chapter_index}'))
                chapter_index += 1
            toc.append((epub.Section(vol_title), tuple(vol_chaps)))
        else:
            chap_obj = process_chapter(item, chapter_index)
            book.add_item(chap_obj)
            spine.append(chap_obj)
            toc.append(epub.Link(chap_obj.file_name, chap_obj.title, f'ch_{chapter_index}'))
            chapter_index += 1

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(filename, book, {})
    logger.info(f"Tạo file EPUB thành công: {filename}")


async def tao_file_pdf(
    content_list: ContentList,
    filename: str,
    title: str = "Chương truyện",
    font_name: str = 'DejaVuSans'
) -> None:
    """Creates a PDF with optimized image fetching."""
    logger.info(f"Đang tạo file PDF: {filename}")
    
    # 1. Prepare Font
    font_path = f"{font_name}.ttf"
    if not os.path.exists(font_path):
        font_urls = {
            'DejaVuSans': 'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf',
            'NotoSerif': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notoserif/NotoSerif-Regular.ttf'
        }
        if font_name in font_urls:
            async with httpx.AsyncClient() as client:
                resp = await client.get(font_urls[font_name])
                with open(font_path, 'wb') as f: f.write(resp.content)

    # 2. Pre-download images
    normalized_items = _normalize_content_list(content_list)
    img_urls = [i.data for i in normalized_items if i.type == 'image']
    image_cache = await _download_images_bulk(img_urls)

    # 3. Build PDF
    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        style = ParagraphStyle(name='Normal_vi', fontName=font_name, fontSize=12, leading=14)
        title_style = ParagraphStyle(name='Title_vi', fontName=font_name, fontSize=18, leading=22, spaceAfter=0.2 * inch)
    except:
        styles = getSampleStyleSheet()
        style, title_style = styles['Normal'], styles['h1']

    doc = SimpleDocTemplate(filename)
    story = [Paragraph(title, title_style), Spacer(1, 0.2 * inch)]
    max_w, max_h = doc.width, doc.height

    for item in normalized_items:
        if item.type == 'text':
            story.append(Paragraph(item.data, style))
            story.append(Spacer(1, 0.1 * inch))
        elif item.type == 'image' and item.data in image_cache:
            try:
                img_data = BytesIO(image_cache[item.data])
                pil_img = PILImage.open(img_data)
                w, h = pil_img.size
                ratio = min(max_w/w, max_h/h, 1)
                story.append(Image(img_data, width=w*ratio, height=h*ratio))
                story.append(Spacer(1, 0.1 * inch))
            except: pass

    doc.build(story)
    logger.info(f"Tạo file PDF thành công: {filename}")


async def tao_file_html(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """HTML export (Async for API consistency)."""
    logger.info(f"Đang tạo file HTML: {filename}")
    html = f"<!DOCTYPE html><html lang='vi'><head><meta charset='UTF-8'><title>{title}</title></head><body><h1>{title}</h1>"
    for item in _normalize_content_list(content_list):
        if item.type == 'text': html += f"<p>{item.data}</p>"
        elif item.type == 'image': html += f"<img src='{item.data}' style='max-width:100%'/>"
    html += "</body></html>"
    with open(filename, 'w', encoding='utf-8') as f: f.write(html)
    logger.info(f"Tạo file HTML thành công: {filename}")

async def tao_file_md(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """Markdown export (Async for API consistency)."""
    logger.info(f"Đang tạo file Markdown: {filename}")
    md = f"# {title}\n\n"
    for item in _normalize_content_list(content_list):
        if item.type == 'text': md += f"{item.data}\n\n"
        elif item.type == 'image': md += f"![Minh họa]({item.data})\n\n"
    with open(filename, 'w', encoding='utf-8') as f: f.write(md)
    logger.info(f"Tạo file Markdown thành công: {filename}")

async def tao_file_txt(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """Text export (Async for API consistency)."""
    logger.info(f"Đang tạo file Text: {filename}")
    txt = f"{title}\n\n"
    for item in _normalize_content_list(content_list):
        if item.type == 'text': txt += f"{item.data}\n\n"
        elif item.type == 'image': txt += f"[Ảnh: {item.data}]\n\n"
    with open(filename, 'w', encoding='utf-8') as f: f.write(txt)
    logger.info(f"Tạo file Text thành công: {filename}")


async def tao_file_mp3(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """AI-Powered Audiobook generation with support for multiple TTS methods."""
    # 1. Config selection via environment variables
    tts_method = os.getenv("VVR_TTS_METHOD", "edge-tts").lower()
    voice = os.getenv("VVR_VOICE")
    
    # 2. SILENCE HEAVY WARNINGS (for Vieneu/OpenCV/TF)
    import warnings
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    warnings.filterwarnings("ignore", category=UserWarning)

    # 3. Prepare text content
    full_text = f"{title}. "
    for item in _normalize_content_list(content_list):
        if item.type == 'text':
            text = item.data.strip()
            if text:
                full_text += f"{text} "

    # 4. Synthesize based on method
    try:
        if tts_method == "edge-tts":
            import edge_tts
            logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng Edge TTS)")
            # Default voice for edge-tts if not provided
            voice = voice or "vi-VN-HoaiMyNeural"
            communicate = edge_tts.Communicate(full_text, voice)
            await communicate.save(filename)

        elif tts_method == "gtts":
            from gtts import gTTS
            logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng Google TTS)")
            # gTTS is simpler, usually just needs lang
            lang = os.getenv("VVR_LANG", "vi")
            def run_gtts():
                tts = gTTS(text=full_text, lang=lang)
                tts.save(filename)
            await asyncio.to_thread(run_gtts)

        elif tts_method == "vieneu":
            # Vieneu is heavy, keep its chunked logic if needed, 
            # but for consistency we use full_text here or chunk it
            try:
                import numpy as np
                from vieneu import Vieneu
            except ImportError:
                logger.error("Vieneu or numpy not found. Please run 'pip install vieneu numpy' to use Vieneu TTS.")
                return

            logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng VieNeu AI)")
            
            # Chunking for Vieneu specifically as it might have limits
            chunks = [full_text[i:i+2000] for i in range(0, len(full_text), 2000)]
            
            def run_tts_vieneu():
                tts = Vieneu()
                # Default voice for vieneu
                v_data = tts.get_preset_voice(voice or "Tuyen")
                audio_segments = []
                for chunk in chunks:
                    if chunk.strip():
                        audio = tts.infer(text=chunk, voice=v_data)
                        audio_segments.append(audio)
                if audio_segments:
                    merged_audio = np.concatenate(audio_segments)
                    tts.save(merged_audio, filename)
            
            await asyncio.to_thread(run_tts_vieneu)

        else:
            logger.error(f"TTS method unknown: {tts_method}")
            return

        logger.info(f"Tạo file Audiobook thành công: {filename}")
    except Exception as e:
        logger.error(f"Lỗi khi tạo Audiobook ({tts_method}): {e}")
        raise e

