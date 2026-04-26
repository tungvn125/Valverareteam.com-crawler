"""
File export functions for the web novel scraper.
"""

import asyncio
import html
import inspect
import io
import json
import os
import urllib.parse
import uuid
from typing import Any, cast

import httpx

# Heavy AI libraries (numpy, ElevenLabs) are lazy-loaded inside tao_file_mp3
# to ensure a fast cold start for the CLI and Web UI.
from ebooklib import epub
from loguru import logger
from PIL import Image as PILImage
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from .audio_drama import OpenAIParser, ScriptResult, VoiceManager
from .bgm_manager import BGMManager
from .freesound_manager import FreesoundManager
from .image_gen import ImageGenerator
from .mixing_engine import AudioTimeline, MixingEngine, TimelineConfig
from .models import ContentItem
from .utils import HEADERS, get_config_path
from .video_renderer import VideoRenderer
from .voice_bank.db import VoiceBankDatabaseManager

ContentItemLike = ContentItem | dict[str, str]
ContentList = list[ContentItemLike]
ChapterData = dict[str, Any]  # {'title': str, 'content': ContentList}
VolumeData = dict[str, Any]  # {'volume': str, 'chapters': List[ChapterData]}
ChaptersData = list[ChapterData | VolumeData]


def _normalize_content_item(item: ContentItemLike) -> ContentItem:
    """Convert dict to ContentItem if needed."""
    if isinstance(item, ContentItem):
        return item
    return ContentItem(type=cast(str, item["type"]), data=cast(str, item["data"]))


def _normalize_content_list(items: ContentList) -> list[ContentItem]:
    """Convert list of dicts to list of ContentItems."""
    return [_normalize_content_item(item) for item in items]


def _normalize_image_url(url: str) -> str:
    """Normalize image URLs before download/export."""
    if url.startswith("//"):
        return f"https:{url}"
    return url


async def _maybe_await(value):
    """Await the value if it is awaitable, else return it directly."""
    if inspect.isawaitable(value):
        return await value
    return value


async def _invoke_select_voices_callback(callback, characters: list[dict], story_id: str, provider_name: str):
    """Invoke voice-selection callbacks with backward-compatible arity."""
    try:
        signature = inspect.signature(callback)
        positional_params = [
            p
            for p in signature.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        accepts_varargs = any(p.kind == p.VAR_POSITIONAL for p in signature.parameters.values())
        if accepts_varargs or len(positional_params) >= 3:
            return await _maybe_await(callback(characters, story_id, provider_name))
    except (TypeError, ValueError):
        # Some callables do not expose inspectable signatures; preserve legacy behavior.
        pass
    return await _maybe_await(callback(characters, story_id))


def _get_synthesis_concurrency(provider_name: str) -> int:
    """Return safe TTS synthesis concurrency for the active provider."""
    env_value = os.getenv("VVR_TTS_CONCURRENCY")
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            logger.warning(f"Invalid VVR_TTS_CONCURRENCY={env_value!r}; using provider default")

    if provider_name == "elevenlabs":
        return 3
    return 5


def _combine_voice_segments_with_overlap(
    voice_segments: list[Any], segments: list[dict], cfg: TimelineConfig
) -> tuple[Any, list[int]]:
    """Combine voice segments and return per-segment start offsets within the voice block."""
    from pydub import AudioSegment

    combined_voice = AudioSegment.silent(duration=0)
    combined_position_ms = 0
    segment_start_offsets_ms: list[int] = []

    for j, vs in enumerate(voice_segments):
        should_overlap = bool(segments[j].get("overlap_with_previous")) and j > 0
        if should_overlap:
            overlap_start = segment_start_offsets_ms[j - 1] + len(voice_segments[j - 1]) // 2
            required_duration = overlap_start + len(vs)
            if required_duration > len(combined_voice):
                combined_voice += AudioSegment.silent(duration=required_duration - len(combined_voice))
            combined_voice = combined_voice.overlay(vs, position=overlap_start)
            segment_start_offsets_ms.append(overlap_start)
            if j < len(voice_segments) - 1:
                combined_position_ms += cfg.gap_between_segments_ms
            continue

        if combined_position_ms > len(combined_voice):
            combined_voice += AudioSegment.silent(duration=combined_position_ms - len(combined_voice))
        segment_start_offsets_ms.append(combined_position_ms)
        combined_voice += vs
        combined_position_ms += len(vs)
        if j < len(voice_segments) - 1:
            combined_voice += AudioSegment.silent(duration=cfg.gap_between_segments_ms)
            combined_position_ms += cfg.gap_between_segments_ms

    return combined_voice, segment_start_offsets_ms


async def _download_images_bulk(urls: list[str], max_concurrent: int = 10) -> dict[str, bytes]:
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
            transient=True,
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
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
}


def _get_image_extension(url: str, content_type: str | None = None) -> str:
    """Detects image extension from URL or Content-Type header."""
    if content_type:
        if "jpeg" in content_type:
            return "jpg"
        if "png" in content_type:
            return "png"
        if "gif" in content_type:
            return "gif"
        if "svg" in content_type:
            return "svg"

    parsed_url = urllib.parse.urlparse(url)
    ext = parsed_url.path.split(".")[-1].lower()
    return ext if ext in ["jpg", "jpeg", "png", "gif", "svg"] else "jpg"


async def tao_file_epub(
    filename: str,
    book_title: str,
    author: str,
    chapters_data: ChaptersData,
    description: str = "",
    cover_path: str | None = None,
    genres: list[str] = None,
) -> None:
    """Creates an EPUB file with pre-fetched images for high performance."""
    logger.info(f"Đang tạo file EPUB: {filename}")

    # 1. Extract all image URLs
    all_image_urls = []
    for item in chapters_data:
        chaps = item.get("chapters", []) if "chapters" in item else [item]
        for chap in chaps:
            for ci in chap.get("content", []):
                norm = _normalize_content_item(ci)
                if norm.type == "image":
                    all_image_urls.append(_normalize_image_url(norm.data))

    # 2. Pre-download all images concurrently
    image_cache = await _download_images_bulk(all_image_urls)

    # 3. Build EPUB
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{os.path.basename(filename)}")
    book.set_title(book_title)
    book.set_language("vi")
    book.add_author(author)
    book.add_metadata("DC", "description", description)
    if genres:
        for g in genres:
            book.add_metadata("DC", "subject", g)

    if cover_path and os.path.exists(cover_path):
        try:
            with open(cover_path, "rb") as cf:
                book.set_cover("cover.jpg", cf.read())
        except Exception as e:
            logger.warning(f"Could not set EPUB cover image: {e}")

    toc = []
    spine = ["nav"]
    url_to_internal_path = {}
    image_counter = 1

    # Map pre-downloaded images to EPUB items
    for url, content in image_cache.items():
        ext = _get_image_extension(url)
        img_name = f"image_{image_counter}.{ext}"
        img_item = epub.EpubImage(
            uid=f"img_{image_counter}",
            file_name=f"images/{img_name}",
            media_type=MIME_TYPE_MAP.get(ext, "image/jpeg"),
            content=content,
        )
        book.add_item(img_item)
        url_to_internal_path[url] = f"images/{img_name}"
        image_counter += 1

    def process_chapter(chap_data: ChapterData, chap_idx: int) -> epub.EpubHtml:
        title = chap_data.get("title", f"Chương {chap_idx}")
        chapter_obj = epub.EpubHtml(title=title, file_name=f"chap_{chap_idx}.xhtml", lang="vi")
        chapter_html = f"<h1>{html.escape(title)}</h1>"
        for item in chap_data.get("content", []):
            norm = _normalize_content_item(item)
            if norm.type == "text":
                chapter_html += f"<p>{html.escape(norm.data)}</p>"
            elif norm.type == "image":
                image_url = _normalize_image_url(norm.data)
                if image_url in url_to_internal_path:
                    chapter_html += f'<img src="{url_to_internal_path[image_url]}" alt="Minh họa"/>'
        chapter_obj.content = chapter_html
        return chapter_obj

    # Assemble structure
    chapter_index = 1
    for item in chapters_data:
        if "volume" in item:
            vol_title = item["volume"]
            vol_chaps = []
            for c_data in item.get("chapters", []):
                chap_obj = process_chapter(c_data, chapter_index)
                book.add_item(chap_obj)
                spine.append(chap_obj)
                vol_chaps.append(epub.Link(chap_obj.file_name, chap_obj.title, f"ch_{chapter_index}"))
                chapter_index += 1
            toc.append((epub.Section(vol_title), tuple(vol_chaps)))
        else:
            chap_obj = process_chapter(item, chapter_index)
            book.add_item(chap_obj)
            spine.append(chap_obj)
            toc.append(epub.Link(chap_obj.file_name, chap_obj.title, f"ch_{chapter_index}"))
            chapter_index += 1

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(filename, book, {})
    logger.info(f"Tạo file EPUB thành công: {filename}")


async def tao_file_pdf(
    content_list: ContentList, filename: str, title: str = "Chương truyện", font_name: str = "DejaVuSans"
) -> None:
    """Creates a PDF with optimized image fetching."""
    logger.info(f"Đang tạo file PDF: {filename}")

    # 1. Prepare Font
    font_path = f"{font_name}.ttf"
    if not os.path.exists(font_path):
        font_urls = {
            "DejaVuSans": "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf",
            "NotoSerif": "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserif/NotoSerif-Regular.ttf",
        }
        if font_name in font_urls:
            async with httpx.AsyncClient() as client:
                resp = await client.get(font_urls[font_name])
                with open(font_path, "wb") as f:
                    f.write(resp.content)

    # 2. Pre-download images
    normalized_items = _normalize_content_list(content_list)
    img_urls = [i.data for i in normalized_items if i.type == "image"]
    image_cache = await _download_images_bulk(img_urls)

    # 3. Build PDF
    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        style = ParagraphStyle(name="Normal_vi", fontName=font_name, fontSize=12, leading=14)
        title_style = ParagraphStyle(
            name="Title_vi", fontName=font_name, fontSize=18, leading=22, spaceAfter=0.2 * inch
        )
    except Exception as e:
        logger.warning(f"Could not register font '{font_name}', falling back to default: {e}")
        styles = getSampleStyleSheet()
        style, title_style = styles["Normal"], styles["h1"]

    doc = SimpleDocTemplate(filename)
    story = [Paragraph(title, title_style), Spacer(1, 0.2 * inch)]
    max_w, max_h = doc.width, doc.height

    for item in normalized_items:
        if item.type == "text":
            story.append(Paragraph(item.data, style))
            story.append(Spacer(1, 0.1 * inch))
        elif item.type == "image" and item.data in image_cache:
            try:
                img_data = io.BytesIO(image_cache[item.data])
                pil_img = PILImage.open(img_data)
                w, h = pil_img.size
                ratio = min(max_w / w, max_h / h, 1)
                img_data.seek(0)
                story.append(Image(img_data, width=w * ratio, height=h * ratio))
                story.append(Spacer(1, 0.1 * inch))
            except Exception as e:
                logger.debug(f"Could not embed image in PDF: {e}")

    doc.build(story)
    logger.info(f"Tạo file PDF thành công: {filename}")


async def tao_file_html(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """HTML export (Async for API consistency)."""
    logger.info(f"Đang tạo file HTML: {filename}")
    safe_title = html.escape(title)
    html_content = f"<!DOCTYPE html><html lang='vi'><head><meta charset='UTF-8'><title>{safe_title}</title></head><body><h1>{safe_title}</h1>"
    for item in _normalize_content_list(content_list):
        if item.type == "text":
            html_content += f"<p>{html.escape(item.data)}</p>"
        elif item.type == "image":
            html_content += f"<img src='{html.escape(item.data)}' style='max-width:100%'/>"
    html_content += "</body></html>"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Tạo file HTML thành công: {filename}")


async def tao_file_md(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """Markdown export (Async for API consistency)."""
    logger.info(f"Đang tạo file Markdown: {filename}")
    md = f"# {title}\n\n"
    for item in _normalize_content_list(content_list):
        if item.type == "text":
            md += f"{item.data}\n\n"
        elif item.type == "image":
            md += f"![Minh họa]({item.data})\n\n"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(md)
    logger.info(f"Tạo file Markdown thành công: {filename}")


async def tao_file_txt(content_list: ContentList, filename: str, title: str = "Chương truyện") -> None:
    """Text export (Async for API consistency)."""
    logger.info(f"Đang tạo file Text: {filename}")
    txt = f"{title}\n\n"
    for item in _normalize_content_list(content_list):
        if item.type == "text":
            txt += f"{item.data}\n\n"
        elif item.type == "image":
            txt += f"[Ảnh: {item.data}]\n\n"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(txt)
    logger.info(f"Tạo file Text thành công: {filename}")


async def tao_file_mp3(
    content_list: ContentList, filename: str, title: str = "Chương truyện", tts_provider_name: str | None = None
) -> None:
    """AI-Powered Audiobook generation using TTS provider with chunked processing."""
    from . import tts
    from .tts.base import DEFAULT_ELEVENLABS_VOICE_ID, VoiceSpec

    # Instantiate provider with appropriate kwargs
    provider_name = tts_provider_name or tts.auto_detect_provider()
    provider_kwargs = {}
    if provider_name == "elevenlabs":
        provider_kwargs["api_key"] = os.getenv("ELEVENLABS_API_KEY")
    elif provider_name == "openai_tts":
        provider_kwargs["api_key"] = os.getenv("OPENAI_TTS_API_KEY")
        provider_kwargs["base_url"] = os.getenv("OPENAI_TTS_BASE_URL")
    provider = tts.get_provider(provider_name, **provider_kwargs)
    logger.info(f"Using TTS provider: {provider_name}")

    try:
        import io

        import pydub
    except ImportError:
        logger.error("pydub not found. Please run 'uv pip install vvr-scraper[audio]'.")
        return

    logger.info(f"Đang tạo file Audiobook: {filename} (Sử dụng {provider_name} AI)")

    # 3. Prepare text chunks
    chunks = [title]
    for item in _normalize_content_list(content_list):
        if item.type == "text":
            text = item.data.strip()
            if text:
                if len(text) > 2000:
                    subchunks = [text[i : i + 2000] for i in range(0, len(text), 2000)]
                    chunks.extend(subchunks)
                else:
                    chunks.append(text)

    # 4. Synthesize each chunk
    try:
        audio_segments = []
        total_chunks = len(chunks)
        # Provider-appropriate default voice
        if provider_name == "openai_tts":
            voice_spec = VoiceSpec(voice_id="alloy", settings={})
        elif provider_name == "omnivoice":
            voice_spec = VoiceSpec(voice_id=None, settings={})
        else:
            # ElevenLabs or unknown
            voice_id = os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID)
            voice_spec = VoiceSpec(
                voice_id=voice_id,
                settings={"stability": 0.75, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True},
            )

        def _load_segment(audio_bytes):
            return pydub.AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")

        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            logger.debug(f"Synthesizing chunk {i + 1}/{total_chunks}...")
            result = await provider.synthesize(text=chunk, voice=voice_spec)
            segment = await asyncio.to_thread(_load_segment, result.audio_bytes)
            audio_segments.append(segment)

        # Merge + export (blocking) in thread
        def _merge_and_export():
            if audio_segments:
                logger.debug("Merging audio segments...")
                merged_audio = audio_segments[0]
                for seg in audio_segments[1:]:
                    merged_audio += seg
                merged_audio.export(filename, format="mp3")

        await asyncio.to_thread(_merge_and_export)
        logger.info(f"Tạo file Audiobook thành công: {filename}")
    except Exception as e:
        logger.error(f"Lỗi khi tạo Audiobook: {e}")
        raise e
    finally:
        if hasattr(provider, "close") and asyncio.iscoroutinefunction(provider.close):
            await provider.close()


async def tao_file_audiodrama(
    content_list: ContentList,
    filename: str,
    story_id: str,
    db_manager: Any,
    title: str = "Chương truyện",
    timeline_config: TimelineConfig | None = None,
    tts_provider_name: str | None = None,
    fail_on_synth_error: bool = True,
    select_voices_callback: Any = None,
) -> list[dict] | None:
    """
    AI-Powered Audio Drama generation.
    1. Extracts text and parses into a script (dialogue/narrator) using OpenAI.
    2. Assigns voices to characters using VoiceManager.
    3. Synthesizes each segment with TTS provider, mixes with BGM using AudioTimeline.
    4. Caches the script to <filename>.script.json for persistence/debugging.
    """

    from . import tts
    from .tts.base import VoiceSpec, map_tags

    # Instantiate provider with appropriate kwargs
    provider_name = tts_provider_name or tts.auto_detect_provider()
    provider_kwargs = {}
    if provider_name == "elevenlabs":
        provider_kwargs["api_key"] = os.getenv("ELEVENLABS_API_KEY")
    elif provider_name == "openai_tts":
        provider_kwargs["api_key"] = os.getenv("OPENAI_TTS_API_KEY")
        provider_kwargs["base_url"] = os.getenv("OPENAI_TTS_BASE_URL")
    provider = tts.get_provider(provider_name, **provider_kwargs)
    logger.info(f"Using TTS provider: {provider_name}")

    # 0. Extract text from content_list (List[ContentItem])
    normalized_content = _normalize_content_list(content_list)
    full_text = "\n".join([item.data for item in normalized_content if item.type == "text"])

    script_file = f"{filename}.script.json"
    script = []
    detected_characters: list[dict] = []

    # 1. Initialize voice manager to get known characters for parsing context
    voice_manager = None
    image_gen = None
    bgm_manager = None
    voice_bank_db = None
    try:
        # Create shared VoiceBankDatabaseManager instance to avoid N+1 connections
        voice_bank_db = VoiceBankDatabaseManager(db_path=get_config_path("voice_bank.db"))
        await voice_bank_db.init_db()

        voice_manager = VoiceManager(db_manager, story_id, provider=provider, voice_bank_db=voice_bank_db)
        known_chars_raw = await _maybe_await(voice_manager.get_known_characters())
        known_chars = known_chars_raw if isinstance(known_chars_raw, list) else []

        bgm_manager = BGMManager()
        bgm_manager.refresh()

        # 2. Load cached script if exists
        if os.path.exists(script_file):
            try:
                with open(script_file, encoding="utf-8") as f:
                    raw_script = json.load(f)
                    script = ScriptResult(raw_script)
                logger.info(f"Loaded cached script from {script_file}")
            except Exception as e:
                logger.warning(f"Failed to load cached script: {e}")

        # 3. Parse if needed
        if not script:
            logger.info(f"Generating audio drama script for {title}...")
            parser = OpenAIParser()
            script = await parser.parse_chapter(
                full_text,
                known_characters=known_chars,
                output_prefix=filename,
                bgm_moods=bgm_manager.available_moods,
            )
            if not script:
                logger.error("OpenAI failed to generate script. Aborting Audio Drama generation.")
                return

        # 4. Resolve Aliases (NLP-based post-processing)
        resolved_script = await _maybe_await(voice_manager.resolve_aliases(script))
        if isinstance(resolved_script, list):
            script = resolved_script

        # 5. Save script checkpoint (after alias resolution)
        try:
            with open(script_file, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved script checkpoint to {script_file}")
        except Exception as e:
            logger.warning(f"Failed to save script checkpoint: {e}")

        # 5b. Extract detected characters from script for voice selection
        detected_characters: list[dict] = []
        for item in script:
            if isinstance(item, dict) and item.get("type") != "mood_shift":
                char_name = item.get("role", "narrator")
                char_gender = (item.get("gender") or "unknown").lower()
                # Deduplicate by name
                if not any(c.get("name") == char_name for c in detected_characters):
                    detected_characters.append({"name": char_name, "gender": char_gender})

        # 5c. Invoke voice selection callback if provided
        if select_voices_callback and detected_characters:
            try:
                await _invoke_select_voices_callback(
                    select_voices_callback,
                    detected_characters,
                    story_id,
                    provider_name,
                )
                await voice_manager.reload_cache()
            except Exception as e:
                logger.warning(f"Voice selection callback failed (non-fatal): {e}")

        # 6. Prepare voice assignments and handle mood shifts
        enriched_script = ScriptResult()
        for item in script:
            if item.get("type") == "mood_shift":
                enriched_script.append(item)
            else:
                char_name = item.get("role", "narrator")
                text = item.get("text", "").strip()
                gender = (item.get("gender") or "unknown").lower()
                if not text:
                    continue
                voice_name = await voice_manager.get_voice(char_name, gender)
                enriched_script.append(
                    {
                        "type": "segment",
                        "role": char_name,
                        "voice": voice_name,
                        "text": text,
                        "overlap_with_previous": bool(item.get("overlap_with_previous", False)),
                    }
                )
    except Exception as e:
        logger.error(f"Error preparing audio drama script: {e}")
        raise

    # Synthesis requires pydub — check separately
    try:
        from pydub import AudioSegment
    except ImportError as e:
        logger.error(f"pydub not found. Please run 'uv pip install vvr-scraper[audio]'. Error: {e}")
        return

    logger.info(f"Synthesizing audio drama v2.5 (Parallel & Block-based): {filename}...")

    freesound_manager = FreesoundManager()
    mixing_engine = MixingEngine()

    # Initialize ImageGenerator
    output_dir = os.path.dirname(filename)
    backgrounds_dir = os.path.join(output_dir, "backgrounds")
    os.makedirs(backgrounds_dir, exist_ok=True)
    image_gen = ImageGenerator(cache_dir=backgrounds_dir)

    synthesis_concurrency = _get_synthesis_concurrency(provider_name)
    logger.info(f"TTS synthesis concurrency: {synthesis_concurrency}")
    semaphore = asyncio.Semaphore(synthesis_concurrency)
    voice_locks: dict[str, asyncio.Lock] = {}

    # Audio timing — from TimelineConfig (or defaults)
    cfg = timeline_config or TimelineConfig()

    # Group into blocks
    blocks = enriched_script.blocks

    async def synthesize_segment(item):
        async with semaphore:
            voice_spec = item["voice"]  # VoiceSpec
            raw_text = item["text"]
            role = item.get("role", "narrator")

            # Map performance tags for the active provider
            text = map_tags(raw_text, provider_name)

            # Stability: Narrator needs to be stable (0.75), Characters need to be expressive (0.35)
            stability = 0.75 if role.lower() == "narrator" else 0.35

            try:
                # Create new settings dict to avoid mutating shared VoiceSpec
                merged_settings = {**voice_spec.settings, "stability": stability}
                voice_spec = VoiceSpec(
                    voice_id=voice_spec.voice_id,
                    ref_audio_path=voice_spec.ref_audio_path,
                    ref_text=voice_spec.ref_text,
                    instruct=voice_spec.instruct,
                    settings=merged_settings,
                )
                voice_lock_key = voice_spec.voice_id or voice_spec.ref_audio_path or voice_spec.instruct or role.lower()
                voice_lock = voice_locks.setdefault(voice_lock_key, asyncio.Lock())
                async with voice_lock:
                    result = await voice_manager.synthesize(voice=voice_spec, text=text)
                segment = AudioSegment.from_file(io.BytesIO(result.audio_bytes), format=result.format)
                alignments = (
                    [{"word": w.word, "start": w.start, "end": w.end} for w in result.word_alignments]
                    if result.word_alignments
                    else []
                )
                return segment, alignments
            except Exception as e:
                if fail_on_synth_error:
                    raise
                logger.error(f"Error synthesizing segment: {e}")
                return AudioSegment.silent(duration=500), []

    try:
        timeline = AudioTimeline(cfg)
        final_audio = None
        all_events = []
        temp_bgm_files: list[str] = []  # Track temp BGM files for cleanup (Issue #6)
        # Store per-block metadata for event creation after render() (Issue #7)
        block_metadata: list[dict] = []

        for i, block in enumerate(blocks):
            mood_info = block["mood_info"]
            segments = block["segments"]
            tags = mood_info.get("tags", [mood_info.get("mood", "peaceful")])
            current_mood = mood_info.get("mood", "peaceful")

            logger.info(f"Processing Block {i + 1}/{len(blocks)} (Tags: {tags})...")

            # 1. Background Generation
            visual_prompt = mood_info.get("visual_prompt")
            bg_rel_path = None
            if visual_prompt:
                try:
                    bg_full_path = await image_gen.generate(visual_prompt)
                    bg_rel_path = os.path.join("backgrounds", os.path.basename(bg_full_path))
                except Exception as e:
                    logger.warning(f"Failed to generate background image: {e}")

            # 2. Parallel Synthesis for the block
            synthesis_results = await asyncio.gather(*[synthesize_segment(s) for s in segments])
            voice_segments = [res[0] for res in synthesis_results]
            raw_block_alignments = [res[1] for res in synthesis_results]

            # 3. Find BGM (Async)
            bgm_track_path = None
            for tag in tags:
                bgm_track_path = bgm_manager.get_random_track(tag)
                if bgm_track_path:
                    logger.debug(f"Found local BGM for tag '{tag}': {bgm_track_path}")
                    break

            if not bgm_track_path:
                logger.info(f"No local BGM for {tags}, searching Freesound...")
                try:
                    fs_results = await freesound_manager.search_bgm(tags, limit=5)
                    if fs_results:
                        sound = fs_results[0]
                        sound_id = sound.get("id") if isinstance(sound, dict) else getattr(sound, "id", None)
                        if sound_id is None:
                            raise ValueError(f"Freesound result missing id: {sound!r}")
                        bgm_track_path = f"temp_bgm_{uuid.uuid4().hex[:8]}_{sound_id}.wav"
                        await freesound_manager.download_and_convert(sound_id, bgm_track_path)
                        temp_bgm_files.append(bgm_track_path)
                        logger.debug(f"Downloaded Freesound BGM: {bgm_track_path}")
                except Exception as e:
                    logger.warning(f"Failed to fetch from Freesound: {e}")
                    bgm_track_path = None

            # 4. Mix block using AudioTimeline (Issue #7 - use render() instead of closure)
            combined_voice, segment_start_offsets_ms = _combine_voice_segments_with_overlap(
                voice_segments,
                segments,
                cfg,
            )

            # Do NOT apply fade here — AudioTimeline.render() handles it

            # Store metadata for event creation after render()
            block_metadata.append(
                {
                    "mood_info": mood_info,
                    "segments": segments,
                    "bg_rel_path": bg_rel_path,
                    "voice_segments": voice_segments,
                    "raw_block_alignments": raw_block_alignments,
                    "segment_start_offsets_ms": segment_start_offsets_ms,
                    "bgm_track_path": bgm_track_path,
                    "combined_voice_duration": len(combined_voice),
                }
            )

            # Add block to timeline (Issue #7 - use AudioTimeline methods instead of closure)
            timeline.add_block(i, combined_voice, current_mood, bgm_track_path)

        # After all blocks, render the timeline (Issue #7)
        try:
            final_audio, block_timings = timeline.render(filename, mixing_engine)
        except Exception as e:
            logger.error(f"Error rendering timeline: {e}")
            raise

        # Create events using block_timings from render() (Issue #7)
        current_block_start_ms = 0
        for i, metadata in enumerate(block_metadata):
            mood_info = metadata["mood_info"]
            segments = metadata["segments"]
            bg_rel_path = metadata["bg_rel_path"]
            voice_segments = metadata["voice_segments"]
            raw_block_alignments = metadata["raw_block_alignments"]
            segment_start_offsets_ms = metadata["segment_start_offsets_ms"]

            # Use block timing from render() for accurate positions
            block_start_ms = block_timings[i]["start_ms"] if i < len(block_timings) else current_block_start_ms
            block_mood = mood_info.get("mood", "peaceful")

            # Background event
            if bg_rel_path:
                all_events.append(
                    {
                        "type": "background",
                        "start": block_start_ms,
                        "src": bg_rel_path,
                        "transition": mood_info.get("transition", "fade"),
                    }
                )

            # VFX event
            vfx_list = mood_info.get("vfx", [])
            if vfx_list:
                all_events.append(
                    {
                        "type": "vfx",
                        "start": block_start_ms,
                        "end": block_start_ms + mood_info.get("duration", 1000),
                        "effect": vfx_list[0] if isinstance(vfx_list, list) and vfx_list else str(vfx_list),
                        "intensity": mood_info.get("intensity", 0.5),
                        "duration": mood_info.get("duration", 1000),
                    }
                )

            # Dialogue events
            for j, segment_alignments in enumerate(raw_block_alignments):
                role = segments[j].get("role", "narrator")
                text = segments[j].get("text", "")

                seg_start_ms = block_start_ms + cfg.voice_overlay_offset_ms + segment_start_offsets_ms[j]
                seg_duration_ms = len(voice_segments[j])
                seg_end_ms = seg_start_ms + seg_duration_ms

                dialogue_event = {
                    "type": "dialogue",
                    "start": seg_start_ms,
                    "end": seg_end_ms,
                    "character": role,
                    "text": text,
                    "alignment": [],
                }

                for word_data in segment_alignments:
                    w = {
                        "word": word_data["word"],
                        "start": word_data["start"] + seg_start_ms,
                        "end": word_data["end"] + seg_start_ms,
                    }
                    dialogue_event["alignment"].append(w)

                all_events.append(dialogue_event)

            # Update current_block_start_ms for next iteration (based on render output)
            if i < len(block_timings):
                current_block_start_ms = block_timings[i]["end_ms"]

        # Only generate manifest if we have alignment data
        has_alignments = any(e.get("alignment") for e in all_events if e.get("type") == "dialogue")
        if has_alignments:
            manifest_file = os.path.join(os.path.dirname(filename), "manifest.json")
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "title": title,
                        "audio": os.path.basename(filename),
                        "base_path": "",
                        "events": sorted(all_events, key=lambda x: x["start"]),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info(f"Saved cinematic manifest to {manifest_file}")
        else:
            logger.info("No alignment data — skipping manifest generation")

        if final_audio and len(final_audio) > 0:
            logger.info(f"Exporting final Audio Drama to {filename}...")

            def export_final():
                final_audio.export(filename, format="mp3")

            await asyncio.to_thread(export_final)
        else:
            logger.error("Audio Drama generation failed: No audio produced.")

    except Exception as e:
        logger.error(f"Lỗi khi tạo Audio Drama v2.5: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise  # Re-raise so callers (execute_job) can mark job as FAILED, not SUCCESS
    finally:
        # Cleanup temp BGM files (Issue #6)
        for temp_bgm_path in temp_bgm_files:
            if temp_bgm_path and os.path.exists(temp_bgm_path):
                try:
                    os.remove(temp_bgm_path)
                except OSError:
                    pass
        if "provider" in locals() and hasattr(provider, "close"):
            await _maybe_await(provider.close())
        if "voice_manager" in locals():
            await _maybe_await(voice_manager.close())
        if "image_gen" in locals():
            await _maybe_await(image_gen.close())
        if "voice_bank_db" in locals() and voice_bank_db is not None:
            await voice_bank_db.close()

    return detected_characters


async def tao_file_mp4(
    content_list: list[ContentItem],
    filename: str,
    story_id: str,
    db_manager: Any,
    title: str,
    fps: int = 30,
    render_format: str = "landscape",
    timeline_config: TimelineConfig | None = None,
):
    """
    Exports the cinematic novel to an MP4 video by first generating
    an Audio Drama MP3/Manifest and then rendering it.
    """
    # 1. Generate Audio Drama MP3 and manifest.json first
    temp_mp3 = filename.replace(".mp4", ".mp3")
    await tao_file_audiodrama(
        content_list=content_list,
        filename=temp_mp3,
        story_id=story_id,
        db_manager=db_manager,
        title=title,
        timeline_config=timeline_config,
    )

    # Check if manifest.json was created
    manifest_path = os.path.join(os.path.dirname(filename), "manifest.json")
    if not os.path.exists(manifest_path):
        raise RuntimeError(
            f"Manifest file not found at {manifest_path}. "
            "Audio drama generation likely failed — check logs above."
        )

    # 2. Render the video (no sound)
    temp_video_nosound = filename.replace(".mp4", "_nosound.mp4")
    renderer = VideoRenderer(
        manifest_path=manifest_path, output_path=temp_video_nosound, fps=fps, render_format=render_format
    )

    try:
        await renderer.render()

        # 3. Mux audio and video
        if os.path.exists(temp_video_nosound) and os.path.exists(temp_mp3):
            await renderer.mux_audio(temp_video_nosound, temp_mp3, filename)
        else:
            missing = []
            if not os.path.exists(temp_video_nosound):
                missing.append(f"video ({temp_video_nosound})")
            if not os.path.exists(temp_mp3):
                missing.append(f"audio ({temp_mp3})")
            raise RuntimeError(f"Failed to generate MP4: missing {', '.join(missing)}")
    finally:
        # Cleanup temporary files
        try:
            if os.path.exists(temp_video_nosound):
                os.remove(temp_video_nosound)
            # We might want to keep the MP3 depending on user choice,
            # but for this flow, we follow the MP4 request.
            # os.remove(temp_mp3)
        except OSError as e:
            logger.debug(f"Could not remove temp video file: {e}")
