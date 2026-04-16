"""
Download task orchestration — the main scraping + export pipeline for the Web UI.
"""

import asyncio
import json
import os
from datetime import datetime

import httpx
from loguru import logger
from playwright.async_api import async_playwright

from ...exporter import (
    tao_file_audiodrama,
    tao_file_epub,
    tao_file_html,
    tao_file_md,
    tao_file_mp3,
    tao_file_pdf,
    tao_file_txt,
)
from ...mixing_engine import TimelineConfig
from ...scraper_core import lay_thong_tin_truyen, scrape_chapters
from ...session_manager import load_session
from ...tao_so_do_cay import get_chapter_tree_list
from ...utils import BASE_URL, HEADERS, get_config_path, get_token_from_state, sanitize_filename
from ..deps import get_db
from ..models import DownloadRequest, load_vvr_settings
from ..state import active_tasks, active_tasks_futures, manager, task_log_buffers


async def run_scrape_task(req: DownloadRequest, task_id: str):
    """Orchestrates the scraping task and sends progress via WebSocket."""
    active_tasks_futures[task_id] = asyncio.current_task()
    is_finished = False
    try:
        await manager.broadcast({"type": "status", "task_id": task_id, "status": "Resolving story..."})

        session_state = load_session(get_config_path(".vvr_session.json"))
        cookies = {}
        if session_state and "cookies" in session_state:
            for c in session_state["cookies"]:
                cookies[c["name"]] = c["value"]

        # Determine if slug is a full URL (custom source) or VVR slug
        is_custom_source = req.slug.startswith("http")

        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, timeout=30.0) as client:
            # For custom sources, pass full URL to lay_thong_tin_truyen
            story_info = await lay_thong_tin_truyen(client, req.slug)

        await manager.broadcast({"type": "info", "task_id": task_id, "title": story_info.title})

        # Ensure we have an output folder
        settings = load_vvr_settings()
        if not req.output_folder:
            base_dir = settings.default_output_folder or "novels"
            output_folder = os.path.join(base_dir, sanitize_filename(story_info.title))
        else:
            output_folder = req.output_folder

        os.makedirs(output_folder, exist_ok=True)
        checkpoint_file = os.path.join(output_folder, ".vvr_checkpoint.json")
        checkpoint = {"slug": req.slug, "title": story_info.title, "cover_url": story_info.cover_url, "scraped": {}}
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "scraped" in data and "slug" in data:
                        checkpoint = data
                    elif isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
                        checkpoint["scraped"] = data
                    else:
                        if isinstance(data, dict):
                            checkpoint["scraped"] = data
                        else:
                            logger.warning(f"Unexpected checkpoint format in {checkpoint_file}. Starting fresh.")
                            checkpoint["scraped"] = {}
                logger.info(f"Loaded checkpoint for task {task_id}. Skipping {len(checkpoint['scraped'])} chapters.")
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Corrupt checkpoint detected, starting fresh: {e}")
                try:
                    os.remove(checkpoint_file)
                except OSError:
                    pass

        # Open browser early to share between chapter tree and scraping
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            story_url = req.slug if is_custom_source else f"{BASE_URL}/{req.slug}"
            chapter_data = await get_chapter_tree_list(
                story_url, output_file=f"chapters_{task_id}.json", session_state=session_state, browser=browser
            )

            if not chapter_data:
                if os.path.exists(f"chapters_{task_id}.json"):
                    with open(f"chapters_{task_id}.json", encoding="utf-8") as f:
                        chapter_data = json.load(f)
                else:
                    raise Exception("Could not retrieve chapter list. Please check if the novel exists or try again.")

            if os.path.exists(f"chapters_{task_id}.json"):
                os.remove(f"chapters_{task_id}.json")

            all_chaps_full = [c for v in chapter_data for c in v["chapters"]]
            total_server_chapters = len(all_chaps_full)

            # Build URL list — filter by selected_urls if provided
            selected_set = None
            if req.selected_urls:
                selected_set = set(url if url.startswith("http") else f"{BASE_URL}{url}" for url in req.selected_urls)

            all_chaps = [c for v in chapter_data for c in v["chapters"]]
            if req.skip_illustrations:
                all_chaps = [c for c in all_chaps if "Minh họa" not in c["title"]]

            def chapter_full_url(chap):
                """Convert chapter URL to full URL regardless of source."""
                return chap["url"] if chap["url"].startswith("http") else f"{BASE_URL}{chap['url']}"

            if selected_set:
                urls = [chapter_full_url(c) for c in all_chaps if chapter_full_url(c) in selected_set]
            else:
                urls = [chapter_full_url(c) for c in all_chaps]

            logger.info(f"Using {len(urls)} URLs for download")

            total = len(urls)

            token = get_token_from_state(session_state)

            # Build pre-scraped dict from checkpoint
            pre_scraped = {}
            for url, content in checkpoint.get("scraped", {}).items():
                if url in urls:
                    pre_scraped[url] = content

            checkpoint_lock = asyncio.Lock()

            async def on_chapter_done(url, content, idx, total):
                if content:
                    from dataclasses import asdict

                    async with checkpoint_lock:
                        checkpoint["scraped"][url] = [
                            asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in content
                        ]
                        checkpoint["slug"] = req.slug
                        checkpoint["title"] = story_info.title
                        with open(checkpoint_file, "w", encoding="utf-8") as f:
                            json.dump(checkpoint, f, ensure_ascii=False, indent=2)

                percent = int(((idx + 1) / total) * 100)
                is_resumed = url in pre_scraped
                msg = (
                    f"Resumed {idx + 1}/{total} chapters (from checkpoint)"
                    if is_resumed
                    else f"Downloaded {idx + 1}/{total} chapters"
                )
                await manager.broadcast({"type": "progress", "task_id": task_id, "percent": percent, "msg": msg})

            scraped = await scrape_chapters(
                browser,
                urls,
                concurrent_tasks=req.tasks,
                session_state=session_state,
                token=token,
                pre_scraped=pre_scraped,
                on_chapter_done=on_chapter_done,
            )
            await browser.close()

        # Check failure rate
        failed_count = total - len(scraped)
        failure_rate = failed_count / total if total > 0 else 0
        if failure_rate > 0.3:
            error_msg = f"Quá nhiều chương tải thất bại: {failed_count}/{total} ({failure_rate:.0%}). Hủy xuất file."
            logger.error(error_msg)
            raise Exception(error_msg)

        await manager.broadcast({"type": "status", "task_id": task_id, "status": "Exporting files..."})

        # Build proper volume/chapter structure for EPUB
        full_flat = []
        full_structure = []
        urls_set = set(urls)
        for v_info in chapter_data:
            v_chaps = []
            for c_entry in v_info["chapters"]:
                f_url = c_entry["url"] if c_entry["url"].startswith("http") else f"{BASE_URL}{c_entry['url']}"
                if f_url in urls_set and f_url in scraped:
                    v_chaps.append({"title": c_entry["title"], "content": scraped[f_url]})
                    full_flat.extend(scraped[f_url])
            if v_chaps:
                full_structure.append({"volume": v_info["volume"], "chapters": v_chaps})

        db = get_db()

        for fmt in req.formats:
            ext = fmt.lower()
            if ext == "ad-mp3":
                ext = "ad.mp3"
            fpath = os.path.join(output_folder, f"{sanitize_filename(story_info.title)}.{ext}")
            if fmt == "PDF":
                await tao_file_pdf(full_flat, fpath, story_info.title)
            elif fmt == "EPUB":
                await tao_file_epub(
                    fpath,
                    story_info.title,
                    story_info.author,
                    full_structure,
                    story_info.description,
                    story_info.cover_path,
                    story_info.genres,
                )
            elif fmt == "HTML":
                await tao_file_html(full_flat, fpath, story_info.title)
            elif fmt == "MD":
                await tao_file_md(full_flat, fpath, story_info.title)
            elif fmt == "TXT":
                await tao_file_txt(full_flat, fpath, story_info.title)
            elif fmt == "MP3":
                await tao_file_mp3(full_flat, fpath, story_info.title)
            elif fmt == "AD-MP3":
                if not os.getenv("VVR_API_KEY") or not os.getenv("VVR_BASE_URL"):
                    logger.warning(
                        "VVR_API_KEY or VVR_BASE_URL not found. Audio Drama generation might fail or fallback."
                    )

                settings = load_vvr_settings()
                tl_config = TimelineConfig(
                    crossfade_default_ms=settings.crossfade_default_ms,
                    crossfade_battle_ms=settings.crossfade_battle_ms,
                    voice_overlay_offset_ms=settings.voice_overlay_offset_ms,
                    gap_between_segments_ms=settings.gap_between_segments_ms,
                    bgm_volume_db=settings.bgm_volume_db,
                )

                await tao_file_audiodrama(
                    content_list=full_flat,
                    filename=fpath,
                    story_id=req.slug,
                    db_manager=db,
                    title=story_info.title,
                    timeline_config=tl_config,
                )

        # Update library DB
        await db.upsert_novel(
            {
                "title": story_info.title,
                "slug": req.slug,
                "author": story_info.author,
                "last_chapter_count": len(urls),
                "last_downloaded_at": datetime.now().isoformat(),
                "output_folder": output_folder,
                "formats": ",".join(req.formats),
                "cover_url": story_info.cover_url,
            }
        )

        # Only update last_synced_count if we downloaded the LATEST chapter
        is_latest_included = True
        if selected_set and all_chaps_full:
            latest_url = all_chaps_full[-1]["url"]
            latest_full_url = latest_url if latest_url.startswith("http") else f"{BASE_URL}{latest_url}"
            is_latest_included = latest_full_url in selected_set

        if is_latest_included:
            await db.update_library_metadata(req.slug, {"last_synced_count": total_server_chapters, "has_updates": 0})
        else:
            logger.info(f"Partial download for {story_info.title}. NOT updating last_synced_count.")

        # Cleanup checkpoint on success
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)

        await manager.broadcast({"type": "complete", "task_id": task_id, "path": output_folder})
        logger.success(f"Task {task_id} completed: {story_info.title}")
    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was paused/cancelled.")
        await manager.broadcast({"type": "status", "task_id": task_id, "status": "Paused"})
        raise
    except Exception as e:
        import traceback

        logger.error(f"Task {task_id} failed: {e}")
        logger.error(traceback.format_exc())
        await manager.broadcast({"type": "error", "task_id": task_id, "error": str(e)})
        is_finished = True
    finally:
        if (
            "story_info" in locals()
            and story_info
            and hasattr(story_info, "cover_path")
            and story_info.cover_path
            and os.path.exists(story_info.cover_path)
        ):
            try:
                os.remove(story_info.cover_path)
            except OSError:
                pass
        if task_id in active_tasks_futures:
            del active_tasks_futures[task_id]
        if is_finished:
            if task_id in active_tasks:
                del active_tasks[task_id]
            if task_id in task_log_buffers:
                del task_log_buffers[task_id]
