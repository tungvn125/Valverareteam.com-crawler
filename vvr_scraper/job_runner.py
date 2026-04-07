import asyncio
import json
import os
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright

from vvr_scraper.job_models import JobManifest, ScrapePayload, RenderPayload, ServerPayload
from vvr_scraper.db import DatabaseManager
from vvr_scraper.scraper_core import scrape_chapters, lay_thong_tin_truyen
from vvr_scraper.video_renderer import VideoRenderer
from vvr_scraper.web import run_web_server
from vvr_scraper.utils import (
    normalize_vietnamese_url, BASE_URL, HEADERS, 
    sanitize_filename, get_token_from_state, get_config_path
)
from vvr_scraper.session_manager import load_session
from vvr_scraper.exporter import (
    tao_file_epub, tao_file_pdf, tao_file_html, tao_file_md, 
    tao_file_txt, tao_file_mp3, tao_file_audiodrama, tao_file_mp4
)
from vvr_scraper.tao_so_do_cay import get_chapter_tree_list

async def resolve_story_url(name_raw: str, cookies: Optional[Dict] = None) -> Optional[str]:
    """Finds the story URL from sitemap."""
    normalized = normalize_vietnamese_url(name_raw)
    sitemap_url = f"{BASE_URL}/sitemap.xml"
    
    async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
        try:
            response = await client.get(sitemap_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "lxml-xml")
            for loc in soup.find_all("loc"):
                url = loc.text
                if normalized in url and "/chuong" not in url:
                    return url
        except Exception as e:
            logger.error(f"Lỗi khi truy cập sitemap: {e}")
    return None

async def execute_crawl_job(payload: ScrapePayload, job_id: int, db: Optional[DatabaseManager]):
    """
    Executes a crawl (scrape) job: resolves story, scrapes chapters, 
    and generates requested files. Updates progress in DB.
    """
    logger.info(f"Starting crawl job {job_id} for {payload.slug}")
    
    # Setup session
    session_state = load_session()
    token = get_token_from_state(session_state)
    cookies = {}
    if session_state and 'cookies' in session_state:
        for c in session_state['cookies']:
            cookies[c['name']] = c['value']

    # 1. Resolve URL
    story_url = await resolve_story_url(payload.slug, cookies=cookies)
    if not story_url:
        raise ValueError(f"Could not resolve story URL for {payload.slug}")
    
    relative_path = story_url.split(f"{BASE_URL}/")[-1]
    output_folder = sanitize_filename(relative_path.split("/")[-1])
    os.makedirs(output_folder, exist_ok=True)

    # 2. Get Story Info
    async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
        story_info = await lay_thong_tin_truyen(client, relative_path)

    # 3. Get Chapters
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            chapter_tree = await get_chapter_tree_list(
                story_url, 
                output_file="chapter_list.json", 
                session_state=session_state,
                browser=browser
            )
            
            # Flatten chapters
            all_chaps = [c for v in chapter_tree for c in v['chapters']]
            
            # Select chapters
            if payload.chapters:
                selected_chaps = []
                for idx in payload.chapters:
                    if 1 <= idx <= len(all_chaps):
                        selected_chaps.append(all_chaps[idx-1])
            else:
                selected_chaps = all_chaps

            if not selected_chaps:
                raise ValueError("No chapters selected or found.")

            urls = [f"{BASE_URL}{c['url']}" for c in selected_chaps]
            total_urls = len(urls)

            async def on_chapter_done(url, content, idx, total):
                if db:
                    progress = (idx / total) * 90.0  # Reserve 10% for exporting
                    await db.update_job_status(job_id, "running", progress=progress)

            scraped = await scrape_chapters(
                browser, urls, 
                session_state=session_state,
                token=token,
                on_chapter_done=on_chapter_done
            )
        finally:
            await browser.close()

    # 4. Export
    if db:
        await db.update_job_status(job_id, "running", progress=90.0)
    
    # Prepare content for exporters
    full_flat = []
    full_structure = []
    for v_info in chapter_tree:
        v_chaps = []
        for c_entry in v_info['chapters']:
            f_url = f"{BASE_URL}{c_entry['url']}"
            if f_url in scraped:
                v_chaps.append({'title': c_entry['title'], 'content': scraped[f_url]})
                full_flat.extend(scraped[f_url])
        if v_chaps:
            full_structure.append({'volume': v_info['volume'], 'chapters': v_chaps})

    for fmt in payload.formats:
        fmt = fmt.upper()
        fpath = os.path.join(output_folder, sanitize_filename(story_info.title))
        
        if fmt == "EPUB": await tao_file_epub(full_flat, fpath, story_info.title, story_info)
        elif fmt == "PDF": await tao_file_pdf(full_flat, fpath, story_info.title, story_info)
        elif fmt == "HTML": await tao_file_html(full_flat, fpath, story_info.title)
        elif fmt == "MD": await tao_file_md(full_flat, fpath, story_info.title)
        elif fmt == "TXT": await tao_file_txt(full_flat, fpath, story_info.title)
        elif fmt == "MP3": await tao_file_mp3(full_flat, fpath, story_info.title)
        elif fmt == "CINEMA" or fmt == "MP4":
            await tao_file_mp4(
                content_list=full_flat,
                filename=fpath + ".mp4",
                story_id=story_info.slug,
                db_manager=db,
                title=story_info.title
            )

    if db:
        await db.update_job_status(job_id, "success", progress=100.0)

async def execute_render_job(payload: RenderPayload, job_id: int, db: Optional[DatabaseManager]):
    """
    Executes a video rendering job using VideoRenderer.
    """
    logger.info(f"Starting render job {job_id}")
    if db:
        await db.update_job_status(job_id, "running", progress=10.0)
    
    renderer = VideoRenderer(
        manifest_path=payload.manifest_path,
        output_path=payload.output_path,
        fps=payload.fps,
        render_format=payload.render_format,
        vfx_scale=payload.vfx_scale
    )
    
    await renderer.render()
    
    # Try to mux if manifest has audio
    try:
        with open(payload.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        audio_path = manifest.get("audio_path")
        if audio_path:
            # Resolve audio_path relative to manifest or absolute
            if not os.path.isabs(audio_path):
                audio_path = os.path.join(os.path.dirname(payload.manifest_path), audio_path)
                
            if os.path.exists(audio_path):
                final_output = payload.output_path
                temp_video = payload.output_path.replace(".mp4", "_nosound.mp4")
                
                # Check if output exists from render
                if os.path.exists(final_output):
                    os.rename(final_output, temp_video)
                    await renderer.mux_audio(temp_video, audio_path, final_output)
                    if os.path.exists(temp_video):
                        os.remove(temp_video)
    except Exception as e:
        logger.warning(f"Could not mux audio: {e}")

    if db:
        await db.update_job_status(job_id, "success", progress=100.0)

async def start_server_from_job(payload: ServerPayload):
    """Starts the FastAPI web server."""
    logger.info(f"Starting server at {payload.host}:{payload.port}")
    if payload.opds_password:
        os.environ["VVR_OPDS_PASSWORD"] = payload.opds_password
        
    await run_web_server(host=payload.host, port=payload.port)

def run_manifest(file_path: str):
    """
    Reads a JSON manifest file, validates it, and executes the job.
    """
    if not os.path.exists(file_path):
        logger.error(f"Manifest file not found: {file_path}")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        manifest = JobManifest.model_validate(data)
        
        # Determine how to run
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(_run_job_directly(manifest))
        except RuntimeError:
            asyncio.run(_run_job_directly(manifest))
            
    except Exception as e:
        logger.error(f"Error running manifest: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def _run_job_directly(manifest: JobManifest):
    db_path = get_config_path("vvr_library.db")
    db = DatabaseManager(db_path)
    await db.init_db()
    
    # Create a job entry
    job_id = await db.create_job(manifest.task, manifest.payload.model_dump_json())
    
    try:
        if manifest.task == "crawl":
            await execute_crawl_job(manifest.payload, job_id, db)
        elif manifest.task == "render":
            await execute_render_job(manifest.payload, job_id, db)
        elif manifest.task == "server":
            await db.update_job_status(job_id, "running")
            await start_server_from_job(manifest.payload)
        
        logger.success(f"Job {job_id} ({manifest.task}) finished successfully.")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await db.update_job_status(job_id, "failed", error_summary=str(e))
