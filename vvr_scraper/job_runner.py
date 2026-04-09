import asyncio
import json
import os
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright

from vvr_scraper.db import DatabaseManager
from vvr_scraper.exporter import (
    tao_file_epub,
    tao_file_html,
    tao_file_md,
    tao_file_mp3,
    tao_file_mp4,
    tao_file_pdf,
    tao_file_txt,
)
from vvr_scraper.job_models import JobManifest, RenderPayload, ScrapePayload, ServerPayload
from vvr_scraper.job_parser import parse_manifest
from vvr_scraper.scraper_core import lay_thong_tin_truyen, scrape_chapters
from vvr_scraper.session_manager import load_session
from vvr_scraper.tao_so_do_cay import get_chapter_tree_list
from vvr_scraper.utils import (
    BASE_URL,
    HEADERS,
    get_config_path,
    get_token_from_state,
    normalize_vietnamese_url,
    sanitize_filename,
)
from vvr_scraper.video_renderer import VideoRenderer
from vvr_scraper.web import run_web_server

# Global worker instance for submission
worker = None


async def resolve_story_url(name_raw: str, cookies: dict | None = None) -> str | None:
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


async def execute_crawl_job(payload: ScrapePayload, job_id: str, db: DatabaseManager | None):
    """
    Executes a crawl (scrape) job: resolves story, scrapes chapters,
    and generates requested files. Updates progress in DB.
    """
    logger.info(f"Starting crawl job {job_id} for {payload.slug}")

    # Setup session
    session_state = load_session(get_config_path(".vvr_session.json"))
    token = get_token_from_state(session_state)
    cookies = {}
    if session_state and "cookies" in session_state:
        for c in session_state["cookies"]:
            cookies[c["name"]] = c["value"]

    # 1. Resolve URL
    story_url = await resolve_story_url(payload.slug, cookies=cookies)
    if not story_url:
        raise ValueError(f"Could not resolve story URL for {payload.slug}")

    relative_path = story_url.split(f"{BASE_URL}/")[-1]

    # Use output_folder from payload if provided, otherwise default to slug-based name
    if payload.output_folder:
        output_folder = payload.output_folder
    else:
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
                story_url, output_file="chapter_list.json", session_state=session_state, browser=browser
            )

            # Flatten chapters
            all_chaps = [c for v in chapter_tree for c in v["chapters"]]

            # Select chapters
            if payload.chapters:
                selected_chaps = []
                for idx in payload.chapters:
                    if 1 <= idx <= len(all_chaps):
                        selected_chaps.append(all_chaps[idx - 1])
            else:
                selected_chaps = all_chaps

            if not selected_chaps:
                raise ValueError("No chapters selected or found.")

            urls = [f"{BASE_URL}{c['url']}" for c in selected_chaps]
            total_urls = len(urls)

            async def on_chapter_done(url, content, idx, total):
                if db:
                    progress = ((idx + 1) / total) * 90.0  # Reserve 10% for exporting
                    await db.update_job_status(job_id, "running", progress=progress)

            scraped = await scrape_chapters(
                browser, urls, session_state=session_state, token=token, on_chapter_done=on_chapter_done
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
        for c_entry in v_info["chapters"]:
            f_url = f"{BASE_URL}{c_entry['url']}"
            if f_url in scraped:
                v_chaps.append({"title": c_entry["title"], "content": scraped[f_url]})
                full_flat.extend(scraped[f_url])
        if v_chaps:
            full_structure.append({"volume": v_info["volume"], "chapters": v_chaps})

    for fmt in payload.formats:
        fmt = fmt.upper()
        fname = sanitize_filename(story_info.title)
        ext = fmt.lower()
        if ext == "cinema":
            ext = "mp4"
        fpath = os.path.join(output_folder, f"{fname}.{ext}")

        if fmt == "EPUB":
            await tao_file_epub(
                fpath,
                story_info.title,
                story_info.author,
                full_structure,
                story_info.description,
                getattr(story_info, "cover_path", None),
                story_info.genres,
            )
        elif fmt == "PDF":
            await tao_file_pdf(full_flat, fpath, story_info.title)
        elif fmt == "HTML":
            await tao_file_html(full_flat, fpath, story_info.title)
        elif fmt == "MD":
            await tao_file_md(full_flat, fpath, story_info.title)
        elif fmt == "TXT":
            await tao_file_txt(full_flat, fpath, story_info.title)
        elif fmt == "MP3":
            await tao_file_mp3(full_flat, fpath, story_info.title)
        elif fmt == "CINEMA" or fmt == "MP4":
            await tao_file_mp4(
                content_list=full_flat, filename=fpath, story_id=story_info.slug, db_manager=db, title=story_info.title
            )

    # 5. Update Library Database (Metadata)
    if db:
        logger.info(f"Updating library metadata for {story_info.title}")
        await db.upsert_novel(
            {
                "title": story_info.title,
                "slug": story_info.slug,
                "author": story_info.author,
                "description": story_info.description,
                "cover_url": story_info.cover_url,
                "genres": ",".join(story_info.genres) if story_info.genres else "",
                "last_chapter_count": len(all_chaps),
                "last_downloaded_at": datetime.now().isoformat(),
                "output_folder": output_folder,
                "formats": ",".join(payload.formats),
            }
        )

        # Update sync status
        await db.update_library_metadata(
            story_info.slug,
            {
                "last_synced_count": len(all_chaps),
                "server_chapter_count": len(all_chaps),
                "has_updates": 0,
                "last_checked_at": datetime.now().isoformat(),
            },
        )

    if db:
        await db.update_job_status(job_id, "success", progress=100.0)


async def execute_render_job(payload: RenderPayload, job_id: str, db: DatabaseManager | None):
    """
    Executes a video rendering job using VideoRenderer.
    """
    logger.info(f"Starting render job {job_id}")
    if db:
        await db.update_job_status(job_id, "running", progress=10.0)

    try:
        renderer = VideoRenderer(
            manifest_path=payload.manifest_path,
            output_path=payload.output_path,
            fps=payload.fps,
            render_format=payload.render_format,
            vfx_scale=payload.vfx_scale,
        )

        # Pass job context to renderer for DB updates
        if db:
            renderer.job_id = job_id
            renderer.db = db

        await renderer.render()

        # Try to mux if manifest has audio
        try:
            with open(payload.manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            audio_path = manifest.get("audio_path") or manifest.get("audio")
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

    except Exception as e:
        logger.error(f"Render job {job_id} failed: {e}")
        if db:
            await db.update_job_status(job_id, "failed", error_summary=str(e))
        raise e


async def start_server_from_job(payload: ServerPayload):
    """Starts the FastAPI web server."""
    logger.info(f"Starting server at {payload.host}:{payload.port}")
    if payload.opds_password:
        os.environ["VVR_OPDS_PASSWORD"] = payload.opds_password

    await run_web_server(host=payload.host, port=payload.port)


async def run_manifest(file_path: str):
    """
    Reads a JSON manifest file, validates it, and executes the job.
    If a local server is running, submits via API to show logs in Web UI.
    """
    if not os.path.exists(file_path):
        logger.error(f"Manifest file not found: {file_path}")
        return

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        manifest = JobManifest.model_validate(data)

        # Validation and parsing
        parse_manifest(manifest)

        # Try to submit to local server first (for Web UI logs)
        server_url = "http://127.0.0.1:8000/api/jobs"
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.post(server_url, json=data)
                if response.status_code == 200:
                    logger.success("Đã gửi Job tới Server thành công. Bạn có thể theo dõi log trên Web UI.")
                    return
            except Exception:
                # Server not running, fallback to local execution
                pass

        logger.info("Không tìm thấy Server đang chạy. Thực thi Job cục bộ...")
        # Execute directly (awaiting ensures the loop stays alive)
        await _run_job_directly(manifest)

    except Exception as e:
        logger.error(f"Error running manifest: {e}")
        import traceback

        logger.error(traceback.format_exc())


async def _run_job_directly(manifest: JobManifest):
    db_path = get_config_path("vvr_library.db")
    logger.info(f"Using database at: {db_path}")
    db = DatabaseManager(db_path)
    await db.init_db()

    # Initialize worker if needed (usually it runs in web.py, but for CLI we might need it)
    global worker
    created_worker = False
    if worker is None:
        from vvr_scraper.job_worker import JobWorker

        worker = JobWorker(db)
        await worker.start()
        created_worker = True

    try:
        jobs = parse_manifest(manifest)
        logger.info(f"Parsed {len(jobs)} jobs from manifest.")
        alias_to_uuid = {}
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for job in jobs:
            # Resolve depends_on (map alias_id to UUID)
            resolved_deps = []
            if job.depends_on:
                for dep in job.depends_on:
                    if dep in alias_to_uuid:
                        resolved_deps.append(alias_to_uuid[dep])
                    else:
                        resolved_deps.append(dep)

            # Create a job entry - SAVE FULL JOB OBJECT AS PAYLOAD
            job_id = await db.create_job(
                task_type=job.task,
                payload=job.model_dump_json(),
                alias_id=job.alias_id,
                batch_id=job.batch_id or batch_id,
                depends_on=",".join(resolved_deps) if resolved_deps else None,
                priority=job.priority,
                from_chapter=getattr(job.payload, "from_chapter", None),
                to_chapter=getattr(job.payload, "to_chapter", None),
            )
            logger.info(f"Created job in DB: {job_id} (alias: {job.alias_id})")

            if job.alias_id:
                alias_to_uuid[job.alias_id] = job_id

            logger.info(f"Submitting job {job_id} ({job.task}) to worker queue.")
            await worker.enqueue_job(job_id, JobManifest(root=job))

        # If we created a local worker, we MUST wait for the jobs to finish
        # otherwise the process exits and the worker dies.
        if created_worker:
            logger.info("Đang chờ các tác vụ hoàn thành...")
            # We wait until the queue is empty AND all tasks are processed
            while not worker.queue.empty():
                await asyncio.sleep(1)

            # Since worker_loop runs jobs in background tasks,
            # we need to be careful. For simplicity in CLI,
            # let's just wait a bit more or check a condition.
            await asyncio.sleep(5)  # Final buffer
    finally:
        if created_worker:
            await worker.stop()
            worker = None
        await db.close()
        # Ensure aiosqlite's worker thread has time to finish
        await asyncio.sleep(0.5)
