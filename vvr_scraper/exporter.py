"""
File export functions for the web novel scraper.
"""
import os
import json
import asyncio
import urllib.parse
import uuid
from io import BytesIO
from typing import List, Dict, Any, Union, cast, Optional

import httpx
from .audio_drama import OpenAIParser, VoiceManager, ScriptResult
from .bgm_manager import BGMManager
from .mixing_engine import MixingEngine
from .freesound_manager import FreesoundManager
from .image_gen import ImageGenerator
from .video_renderer import VideoRenderer
# Heavy AI libraries (numpy, ElevenLabs) are lazy-loaded inside tao_file_mp3 
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
    """AI-Powered Audiobook generation using ElevenLabs with chunked processing."""
    import os
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        logger.error("ELEVENLABS_API_KEY not found. Cannot generate MP3.")
        return

    try:
        from elevenlabs.client import ElevenLabs
        import pydub
        import io
    except ImportError:
        logger.error("elevenlabs or pydub not found. Please run 'uv pip install vvr-scraper[audio]'.")
        return

    logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng ElevenLabs AI)")
    
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
            from elevenlabs.client import ElevenLabs
            from elevenlabs import VoiceSettings
            
            client = ElevenLabs(api_key=api_key)
            audio_segments = []
            
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                logger.debug(f"Synthesizing chunk {i+1}/{total_chunks}...")
                # Generate speech using ElevenLabs API v3
                audio_stream = client.text_to_speech.convert(
                    voice_id="EXAVITQu4vr4xnSDxMaL", # Default voice ID (Rachel)
                    text=chunk, 
                    model_id="eleven_v3",
                    voice_settings=VoiceSettings(
                        stability=0.75, # High stability for audiobook narration
                        similarity_boost=0.75,
                        style=0.0,
                        use_speaker_boost=True
                    )
                )
                # Consume generator into bytes
                audio_bytes = b"".join(list(audio_stream))
                segment = pydub.AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                audio_segments.append(segment)
            
            if audio_segments:
                logger.debug("Merging audio segments...")
                merged_audio = audio_segments[0]
                for seg in audio_segments[1:]:
                    merged_audio += seg
                merged_audio.export(filename, format="mp3")
            
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
    3. Synthesizes each segment with ElevenLabs, mixes with BGM using MixingEngine.
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
                raw_script = json.load(f)
                script = ScriptResult(raw_script)
            logger.info(f"Loaded cached script from {script_file}")
        except Exception as e:
            logger.warning(f"Failed to load cached script: {e}")

    # 2. Parse if needed
    if not script:
        logger.info(f"Generating audio drama script for {title}...")
        parser = OpenAIParser()
        script = await parser.parse_chapter(full_text)
        if not script:
            logger.error("OpenAI failed to generate script. Aborting Audio Drama generation.")
            return
        try:
            with open(script_file, 'w', encoding='utf-8') as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved script checkpoint to {script_file}")
        except Exception as e:
            logger.warning(f"Failed to save script checkpoint: {e}")


    # 3. Prepare voice assignments and handle mood shifts
    voice_manager = VoiceManager(db_manager, story_id)
    enriched_script = ScriptResult()
    for item in script:
        if item.get('type') == 'mood_shift':
            enriched_script.append(item)
        else:
            char_name = item.get('role', 'narrator')
            text = item.get('text', '').strip()
            gender = (item.get('gender') or 'unknown').lower()
            if not text:
                continue
            voice_name = await voice_manager.get_voice(char_name, gender)
            enriched_script.append({
                'type': 'segment',
                'role': char_name,
                'voice': voice_name,
                'text': text
            })

    # 4. Synthesis and Mixing pipeline
    try:
        from pydub import AudioSegment
        import io
    except ImportError as e:
        logger.error(f"Required libraries for Audio Drama v2.5 not found: {e}")
        return

    logger.info(f"Synthesizing audio drama v2.5 (Parallel & Block-based): {filename}...")
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        logger.error("ELEVENLABS_API_KEY environment variable is required")
        return

    bgm_manager = BGMManager()
    bgm_manager.refresh()
    freesound_manager = FreesoundManager()
    mixing_engine = MixingEngine()
    
    # Initialize ImageGenerator
    output_dir = os.path.dirname(filename)
    backgrounds_dir = os.path.join(output_dir, "backgrounds")
    os.makedirs(backgrounds_dir, exist_ok=True)
    image_gen = ImageGenerator(cache_dir=backgrounds_dir)
    
    semaphore = asyncio.Semaphore(5)

    # Audio timing constants
    VOICE_OVERLAY_OFFSET_MS = 1000
    CROSSFADE_MS = 1000
    GAP_BETWEEN_SEGMENTS_MS = 500

    # Group into blocks
    blocks = enriched_script.blocks

    async def synthesize_segment(item):
        async with semaphore:
            voice_id = item['voice']
            text = item['text']
            role = item.get('role', 'narrator')
            
            # Stability: Narrator needs to be stable (0.75), Characters need to be expressive (0.35)
            stability = 0.75 if role.lower() == 'narrator' else 0.35
            
            try:
                # Use VoiceManager's synthesis to get word-level timestamps
                audio_bytes, word_alignments = await voice_manager.synthesize(
                    voice_id=voice_id,
                    text=text,
                    stability=stability
                )
                segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                return segment, word_alignments
            except Exception as e:
                logger.error(f"Error synthesizing segment: {e}")
                return AudioSegment.silent(duration=500), []

    try:
        final_audio = None
        current_block_start_ms = 0
        all_events = []
        
        for i, block in enumerate(blocks):
            mood_info = block['mood_info']
            segments = block['segments']
            tags = mood_info.get('tags', [mood_info.get('mood', 'peaceful')])
            
            logger.info(f"Processing Block {i+1}/{len(blocks)} (Tags: {tags})...")
            
            # 1. Background Generation
            visual_prompt = mood_info.get('visual_prompt')
            bg_rel_path = None
            if visual_prompt:
                try:
                    bg_full_path = await image_gen.generate(visual_prompt)
                    # Store as relative path for portability
                    bg_rel_path = os.path.join("backgrounds", os.path.basename(bg_full_path))
                except Exception as e:
                    logger.warning(f"Failed to generate background image: {e}")

            # Record background event in manifest
            if bg_rel_path:
                all_events.append({
                    "type": "background",
                    "start": current_block_start_ms,
                    "src": bg_rel_path,
                    "transition": mood_info.get('transition', 'fade')
                })
            
            # Record VFX event in manifest
            vfx_list = mood_info.get('vfx', [])
            if vfx_list:
                all_events.append({
                    "type": "vfx",
                    "start": current_block_start_ms,
                    "end": current_block_start_ms + mood_info.get('duration', 1000),
                    "effect": vfx_list[0] if isinstance(vfx_list, list) and vfx_list else str(vfx_list),
                    "intensity": mood_info.get('intensity', 0.5),
                    "duration": mood_info.get('duration', 1000)
                })

            # 2. Parallel Synthesis for the block
            synthesis_results = await asyncio.gather(*[synthesize_segment(s) for s in segments])
            voice_segments = [res[0] for res in synthesis_results]
            raw_block_alignments = [res[1] for res in synthesis_results]
            
            # Adjust word alignments and create dialogue events
            segment_offset_in_block_ms = VOICE_OVERLAY_OFFSET_MS
            for j, segment_alignments in enumerate(raw_block_alignments):
                role = segments[j].get('role', 'narrator')
                text = segments[j].get('text', '')
                
                seg_start_ms = current_block_start_ms + segment_offset_in_block_ms
                seg_duration_ms = len(voice_segments[j])
                seg_end_ms = seg_start_ms + seg_duration_ms
                
                # Create dialogue event with word-level alignment
                dialogue_event = {
                    "type": "dialogue",
                    "start": seg_start_ms,
                    "end": seg_end_ms,
                    "character": role,
                    "text": text,
                    "alignment": []
                }
                
                for word_data in segment_alignments:
                    # Create a copy to avoid modifying original and adjust to global timeline
                    w = {
                        "word": word_data["word"],
                        "start": word_data["start"] + seg_start_ms,
                        "end": word_data["end"] + seg_start_ms
                    }
                    dialogue_event["alignment"].append(w)
                
                all_events.append(dialogue_event)
                # Update offset for next segment in block
                segment_offset_in_block_ms += seg_duration_ms + GAP_BETWEEN_SEGMENTS_MS

            # 3. Find BGM (Async)
            bgm_track_path = None
            # Check local first
            for tag in tags:
                bgm_track_path = bgm_manager.get_random_track(tag)
                if bgm_track_path:
                    logger.debug(f"Found local BGM for tag '{tag}': {bgm_track_path}")
                    break

            # If not found locally, try Freesound
            if not bgm_track_path:
                logger.info(f"No local BGM for {tags}, searching Freesound...")
                try:
                    fs_results = await freesound_manager.search_bgm(tags, limit=5)
                    if fs_results:
                        sound = fs_results[0]
                        # Use a unique temp filename for downloaded BGM
                        bgm_track_path = f"temp_bgm_{uuid.uuid4().hex[:8]}_{sound.id}.wav"
                        await freesound_manager.download_and_convert(sound.id, bgm_track_path)
                        logger.debug(f"Downloaded Freesound BGM: {bgm_track_path}")
                except Exception as e:
                    logger.warning(f"Failed to fetch from Freesound: {e}")
                    bgm_track_path = None

            def process_block(v_segments, current_bgm_path, current_final_audio):
                # 2. Join voice segments with gaps
                combined_voice = AudioSegment.silent(duration=0)
                for j, vs in enumerate(v_segments):
                    combined_voice += vs
                    if j < len(v_segments) - 1:
                        combined_voice += AudioSegment.silent(duration=GAP_BETWEEN_SEGMENTS_MS)

                # 4. Mix
                if current_bgm_path and os.path.exists(current_bgm_path):
                    bgm_audio = AudioSegment.from_file(current_bgm_path)
                else:
                    # Fallback to peaceful if everything fails
                    fallback_path = bgm_manager.get_random_track("peaceful")
                    if fallback_path:
                        bgm_audio = AudioSegment.from_file(fallback_path)
                    else:
                        bgm_audio = AudioSegment.silent(duration=10000)

                # Create looped background matching combined_voice + 2s padding
                bg_duration = len(combined_voice) + 2000
                background = mixing_engine.create_looped_background(bgm_audio, bg_duration, gain_db=-20.0)

                # Overlay voice
                block_audio = mixing_engine.overlay_voice_on_background(
                    background, 
                    combined_voice.fade_in(500).fade_out(500),
                    position=VOICE_OVERLAY_OFFSET_MS
                )

                block_audio_duration = len(block_audio)

                # 5. Append to final audio with crossfade
                new_final = current_final_audio
                if new_final is None:
                    new_final = block_audio
                else:
                    new_final = new_final.append(block_audio, crossfade=CROSSFADE_MS)

                # Cleanup downloaded BGM if it was a temp file
                if current_bgm_path and "temp_bgm_" in str(current_bgm_path) and os.path.exists(current_bgm_path):
                    try: os.remove(current_bgm_path)
                    except: pass

                return new_final, block_audio_duration

            final_audio, block_duration = await asyncio.to_thread(process_block, voice_segments, bgm_track_path, final_audio)
            # Update current_block_start_ms for next block, account for crossfade overlap
            current_block_start_ms += (block_duration - CROSSFADE_MS)
        
        # Save cinematic manifest as manifest.json in the same folder as the MP3
        manifest_file = os.path.join(os.path.dirname(filename), "manifest.json")
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump({
                "title": title,
                "audio": os.path.basename(filename),
                "base_path": "",
                "events": sorted(all_events, key=lambda x: x["start"])
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved cinematic manifest to {manifest_file}")

        if final_audio:
            logger.info(f"Exporting final Audio Drama to {filename}...")
            
            def export_final():
                final_audio.export(filename, format="mp3")
            await asyncio.to_thread(export_final)
            
            # Cleanup script checkpoint if successful
            script_file = f"{filename}.script.json"
            if os.path.exists(script_file):
                try: os.remove(script_file)
                except: pass
        else:
            logger.error("Audio Drama generation failed: No audio produced.")

    except Exception as e:
        logger.error(f"Lỗi khi tạo Audio Drama v2.5: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def tao_file_mp4(
    content_list: List[ContentItem], 
    filename: str, 
    story_id: str, 
    db_manager: Any, 
    title: str,
    fps: int = 30,
    render_format: str = 'landscape'
):
    """
    Exports the cinematic novel to an MP4 video by first generating 
    an Audio Drama MP3/Manifest and then rendering it.
    """
    # 1. Generate Audio Drama MP3 and manifest.json first
    # We'll use a temporary MP3 path for the audio
    temp_mp3 = filename.replace(".mp4", ".mp3")
    await tao_file_audiodrama(
        content_list=content_list,
        filename=temp_mp3,
        story_id=story_id,
        db_manager=db_manager,
        title=title
    )
    
    # Check if manifest.json was created
    manifest_path = os.path.join(os.path.dirname(filename), "manifest.json")
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest file not found at {manifest_path}. MP4 render aborted.")
        return

    # 2. Render the video (no sound)
    temp_video_nosound = filename.replace(".mp4", "_nosound.mp4")
    renderer = VideoRenderer(
        manifest_path=manifest_path,
        output_path=temp_video_nosound,
        fps=fps,
        render_format=render_format
    )
    
    await renderer.render()
    
    # 3. Mux audio and video
    if os.path.exists(temp_video_nosound) and os.path.exists(temp_mp3):
        await renderer.mux_audio(temp_video_nosound, temp_mp3, filename)
        
        # Cleanup temporary files
        try:
            os.remove(temp_video_nosound)
            # We might want to keep the MP3 depending on user choice, 
            # but for this flow, we follow the MP4 request.
            # os.remove(temp_mp3) 
        except:
            pass
    else:
        logger.error("Failed to generate MP4: Missing temporary video or audio file.")


