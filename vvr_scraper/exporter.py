"""
File export functions for the web novel scraper.
"""
import os
import json
import asyncio
import urllib.parse
from io import BytesIO
from typing import List, Dict, Any, Union, cast, Optional

import httpx
from .audio_drama import OpenAIParser, VoiceManager
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


# Correct MIME types for image formats (image/jpg is NOT valid per RFC 2045)
MIME_TYPE_MAP = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'svg': 'image/svg+xml',
}


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
            media_type=MIME_TYPE_MAP.get(ext, 'image/jpeg'),
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
    """AI-Powered Audiobook generation using VieNeu with chunked processing."""
    # 1. SILENCE HEAVY WARNINGS BEFORE IMPORTING
    import os
    import warnings
    # Suppress heavy framework logs and warnings to keep the terminal clean,
    # but let PyTorch/Tensorflow decide hardware usage (CPU vs GPU) automatically.
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    warnings.filterwarnings("ignore", category=UserWarning)

    # 2. LAZY LOAD HEAVY LIBRARIES
    try:
        import numpy as np
        from vieneu import Vieneu
    except ImportError:
        logger.error("Vieneu or numpy not found. Please run 'pip install vieneu numpy' to use TTS.")
        return

    logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng VieNeu AI)")
    
    # 3. Prepare text chunks
    chunks = [title]
    for item in _normalize_content_list(content_list):
        if item.type == 'text':
            text = item.data.strip()
            if text:
                if len(text) > 2000:
                    subchunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
                    chunks.extend(subchunks)
                else:
                    chunks.append(text)

    # 4. Synthesize each chunk
    try:
        def run_tts_chunked():
            tts = Vieneu()
            voice_data = tts.get_preset_voice("Tuyen")
            audio_segments = []
            
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                logger.debug(f"Synthesizing chunk {i+1}/{total_chunks}...")
                audio = tts.infer(text=chunk, voice=voice_data)
                audio_segments.append(audio)
            
            if audio_segments:
                logger.debug("Merging audio segments...")
                merged_audio = np.concatenate(audio_segments)
                tts.save(merged_audio, filename)
            
        await asyncio.to_thread(run_tts_chunked)
        logger.info(f"Tạo file Audiobook thành công: {filename}")
    except Exception as e:
        logger.error(f"Lỗi khi tạo Audiobook: {e}")
        raise e


async def tao_file_audiodrama(
    content_list: ContentList,
    filename: str,
    story_id: str,
    db_manager: Any,
    title: str = "Chương truyện"
) -> None:
    """
    AI-Powered Audio Drama generation.
    1. Extracts text and parses into a script (dialogue/narrator) using OpenAI.
    2. Assigns voices to characters using VoiceManager.
    3. Synthesizes each segment with Vieneu and merges them.
    4. Caches the script to <filename>.script.json for persistence/debugging.
    """

    # 0. Extract text from content_list (List[ContentItem])
    normalized_content = _normalize_content_list(content_list)
    full_text = "\n".join([item.data for item in normalized_content if item.type == "text"])
    
    script_file = f"{filename}.script.json"
    script = []

    # 1. Load cached script if exists
    if os.path.exists(script_file):
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                script = json.load(f)
            logger.info(f"Loaded cached script from {script_file}")
        except Exception as e:
            logger.warning(f"Failed to load cached script: {e}")

    # 2. Parse or load cached JSON script from <filename>.script.json
    if not script:
        logger.info(f"Generating audio drama script for {title}...")
        parser = OpenAIParser()
        script = await parser.parse_chapter(full_text)
        if not script:
            logger.warning("OpenAI failed to generate script. Falling back to simple MP3.")
            await tao_file_mp3(content_list, filename, title)
            return
        
        # Save script checkpoint
        try:
            with open(script_file, 'w', encoding='utf-8') as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved script checkpoint to {script_file}")
        except Exception as e:
            logger.warning(f"Failed to save script checkpoint: {e}")

    # 3. Iterate through script, get voice via VoiceManager
    voice_manager = VoiceManager(db_manager, story_id)
    script_with_voices = []
    for segment in script:
        char_name = segment.get('role', 'narrator')
        text = segment.get('text', '').strip()
        gender = segment.get('gender', 'unknown').lower()
        if not text:
            continue
        voice_name = await voice_manager.get_voice(char_name, gender)
        script_with_voices.append({
            'voice': voice_name,
            'text': text
        })

    # 4. Call Vieneu.infer() for each segment (via asyncio.to_thread)
    import warnings
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    warnings.filterwarnings("ignore", category=UserWarning)
    
    try:
        import numpy as np
        from vieneu import Vieneu
    except ImportError:
        logger.error("Vieneu or numpy not found. Please run 'pip install vieneu numpy' to use TTS.")
        return

    logger.info(f"Synthesizing audio drama: {filename}...")
    
    try:
        def run_audio_drama_tts():
            tts = Vieneu()
            audio_segments = []
            
            total_segments = len(script_with_voices)
            for i, item in enumerate(script_with_voices):
                voice_name = item['voice']
                text = item['text']
                logger.debug(f"Synthesizing segment {i+1}/{total_segments} (Voice: {voice_name})...")
                
                voice_data = tts.get_preset_voice(voice_name)
                audio = tts.infer(text=text, voice=voice_data)
                audio_segments.append(audio)
            
            # 5. Concatenate segments with numpy
            if audio_segments:
                logger.debug("Merging audio segments...")
                merged_audio = np.concatenate(audio_segments)
                tts.save(merged_audio, filename)
            
        await asyncio.to_thread(run_audio_drama_tts)
        logger.info(f"Tạo file Audio Drama thành công: {filename}")
    except Exception as e:
        # 6. Save output, fallback to tao_file_mp3 on error
        logger.error(f"Lỗi khi tạo Audio Drama: {e}")
        logger.warning("Falling back to simple MP3.")
        await tao_file_mp3(content_list, filename, title)
