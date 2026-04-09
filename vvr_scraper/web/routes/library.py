"""
Library management routes — sync, check updates, scan, batch import.
"""

import asyncio
import json
import os
import re
import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter
from loguru import logger
from playwright.async_api import async_playwright

from ...db import DatabaseManager
from ...scraper_core import lay_thong_tin_truyen
from ...session_manager import load_session
from ...tao_so_do_cay import get_chapter_tree_list
from ...utils import BASE_URL, HEADERS, get_config_path, sanitize_filename
from ..deps import get_db
from ..models import BatchImportRequest, DownloadRequest, load_vvr_settings
from ..state import ConnectionManager, active_tasks, download_queue, manager

router = APIRouter(prefix="/api", tags=["Library"])


@router.get("/library")
async def get_library():
    """Returns all entries from the library database."""
    db = get_db()
    return await db.get_all_novels()


@router.post("/library/sync-all")
async def sync_all_novels():
    """Queues incremental downloads for all novels that have updates."""
    db = get_db()
    novels = await db.get_all_novels()
    sync_count = 0

    settings = load_vvr_settings()
    default_formats = ["EPUB"]

    session_state = load_session(get_config_path(".vvr_session.json"))

    semaphore = asyncio.Semaphore(3)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def sync_one(novel):
            nonlocal sync_count
            slug = novel["slug"]
            title = novel["title"]

            async with semaphore:
                logger.info(f"Syncing {title}...")
                try:
                    story_url = f"{BASE_URL}/{slug}"
                    temp_file = f"temp_sync_{uuid.uuid4().hex[:8]}.json"
                    chapter_data = await get_chapter_tree_list(
                        story_url, output_file=temp_file, session_state=session_state, browser=browser
                    )

                    if not chapter_data:
                        logger.warning(f"Could not fetch chapter tree for {title}")
                        return

                    all_urls = [c["url"] for v in chapter_data for c in v["chapters"]]

                    if all_urls:
                        task_id = str(uuid.uuid4())[:8]
                        formats_val = novel.get("formats")
                        formats = formats_val.split(",") if formats_val else default_formats

                        req = DownloadRequest(
                            slug=slug, selected_urls=all_urls, output_folder=novel.get("output_folder"), formats=formats
                        )
                        active_tasks[task_id] = req
                        await download_queue.add_task(req, task_id)

                        await db.update_library_metadata(slug, {"has_updates": 0})
                        sync_count += 1

                    if os.path.exists(temp_file):
                        os.remove(temp_file)

                except Exception as e:
                    logger.error(f"Error syncing {title}: {e}")

        tasks = [sync_one(novel) for novel in novels if novel.get("has_updates") == 1]
        await asyncio.gather(*tasks)
        await browser.close()

    return {"status": "ok", "queued": sync_count}


async def check_library_updates(db: DatabaseManager, mgr: ConnectionManager | None = None):
    """Background worker that checks for updates across the entire library."""
    novels = await db.get_all_novels()
    total = len(novels)
    updates_found = 0

    session_state = load_session(get_config_path(".vvr_session.json"))
    cookies = {}
    if session_state and "cookies" in session_state:
        for c in session_state["cookies"]:
            cookies[c["name"]] = c["value"]

    async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, timeout=20.0) as client:
        for i, novel in enumerate(novels):
            slug = novel["slug"]
            title = novel["title"]

            if mgr:
                await mgr.broadcast(
                    {"type": "library_check_progress", "current": i + 1, "total": total, "title": title}
                )

            try:
                info = await lay_thong_tin_truyen(client, slug)

                if info.total_chapters == "Unknown":
                    logger.warning(f"Unknown chapter count for {title} ({slug}). Skipping.")
                    continue

                server_count = 0
                match = re.search(r"(\d+[\d.,]*)", info.total_chapters)
                if match:
                    server_count = int(match.group(1).replace(".", "").replace(",", ""))

                last_synced = novel.get("last_synced_count") or 0
                has_updates = 1 if server_count > last_synced else 0
                if has_updates:
                    updates_found += 1

                await db.update_library_metadata(
                    slug,
                    {
                        "server_chapter_count": server_count,
                        "has_updates": has_updates,
                        "last_checked_at": datetime.now().isoformat(),
                    },
                )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.warning(f"Novel {title} ({slug}) not found (404). Archiving.")
                    await db.update_library_metadata(slug, {"status": "archived"})
                else:
                    logger.error(f"HTTP error {e.response.status_code} for {slug}: {e}")
            except Exception as e:
                logger.error(f"Error checking update for {slug}: {e}")

    if mgr:
        await mgr.broadcast({"type": "library_check_complete", "updates_found": updates_found})


async def auto_sync_background_task(db_manager: DatabaseManager, worker_instance):
    """Infinite loop to check for library updates and trigger crawl jobs.
    Runs every 1 hour if VVR_AUTO_SYNC=1."""
    from ...job_models import JobManifest, ScrapeJob, ScrapePayload

    while True:
        try:
            if os.getenv("VVR_AUTO_SYNC") == "1":
                logger.info("Auto-Sync: Checking library updates...")
                await check_library_updates(db_manager, manager)

                novels = await db_manager.get_all_novels()
                updated_novels = [n for n in novels if n.get("has_updates") == 1]

                for novel in updated_novels:
                    slug = novel["slug"]
                    formats_str = novel.get("formats") or "epub,pdf"
                    formats = [f.strip() for f in formats_str.split(",")]

                    payload = ScrapePayload(slug=slug, formats=formats)
                    job_data = ScrapeJob(payload=payload, priority=2)
                    job_obj = JobManifest(root=job_data)

                    job_id = await db_manager.create_job(
                        task_type="crawl", payload=job_obj.model_dump_json(), priority=2
                    )

                    await worker_instance.enqueue_job(job_id, job_obj)
                    logger.info(f"Auto-Sync: Triggered crawl job for {novel['title']} ({slug})")
            else:
                logger.debug("Auto-Sync is disabled (VVR_AUTO_SYNC != 1)")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in auto_sync_background_task: {e}")

        await asyncio.sleep(3600)


@router.get("/library/check-updates")
async def trigger_library_check_updates():
    """Trigger library update check in the background."""
    db = get_db()
    asyncio.create_task(check_library_updates(db, manager))
    return {"status": "started"}


@router.post("/library/check")
async def trigger_library_check():
    """Trigger library update check (now uses background worker)."""
    db = get_db()
    asyncio.create_task(check_library_updates(db, manager))
    return {"status": "started"}


@router.post("/library/scan")
async def scan_library():
    """Scans for existing download folders containing .vvr_checkpoint.json."""
    db = get_db()
    settings = load_vvr_settings()
    scan_path = settings.default_output_folder or "."
    if not os.path.exists(scan_path):
        return {"error": f"Scan path {scan_path} does not exist"}

    found_count = 0
    EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "node_modules", "bgm", "tests", "dist", "build"}
    for root, dirs, files in os.walk(scan_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        if ".vvr_checkpoint.json" in files:
            checkpoint_path = os.path.join(root, ".vvr_checkpoint.json")
            try:
                with open(checkpoint_path, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "slug" in data and "title" in data:
                        chapter_count = len(data.get("scraped", {}))
                        await db.upsert_novel(
                            {
                                "title": data["title"],
                                "slug": data["slug"],
                                "last_chapter_count": chapter_count,
                                "output_folder": root,
                                "status": "synced",
                                "cover_url": data.get("cover_url"),
                            }
                        )
                        found_count += 1
            except Exception as e:
                logger.error(f"Error reading checkpoint at {checkpoint_path}: {e}")

    return {"status": "ok", "added": found_count, "updated": 0}


@router.post("/batch-import")
async def batch_import(req: BatchImportRequest):
    """Accepts a list of URLs/slugs and adds them to the download queue."""
    added_count = 0
    settings = load_vvr_settings()
    for url in req.items:
        slug = url.replace(BASE_URL + "/", "").strip("/")
        if not slug:
            continue

        task_id = str(uuid.uuid4())[:8]
        req_download = DownloadRequest(slug=slug)

        if settings.default_output_folder:
            folder_name = sanitize_filename(slug.split("/")[-1])
            req_download.output_folder = os.path.join(settings.default_output_folder, folder_name)

        active_tasks[task_id] = req_download
        await download_queue.add_task(req_download, task_id)
        added_count += 1

    return {"status": "ok", "count": added_count}
