"""
General API routes — search, browse, settings, chapters, static files, health, download, websocket.
"""

import json
import os
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from loguru import logger

from ...scraper_core import lay_thong_tin_truyen
from ...session_manager import load_session
from ...tao_so_do_cay import get_chapter_tree_list
from ...utils import BASE_URL, HEADERS, get_config_path, normalize_vietnamese_url, sanitize_filename
from ..models import DownloadRequest, FreesoundCallbackRequest, Settings, load_vvr_settings, save_vvr_settings
from ..state import active_tasks, download_queue, manager

SSR_API_URL = "https://val-ssr-2kzit.ondigitalocean.app/api/novels/search"

router = APIRouter(tags=["API"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/api/search")
async def search_novels(q: str = Query(..., min_length=3)):
    """Proxies search requests to the Valvrare Team API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "User-Agent": HEADERS["User-Agent"],
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/",
                "Accept": "application/json, text/plain, */*",
            }
            url = f"{SSR_API_URL}?title={q}"
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            results = response.json()

            for item in results:
                title = item.get("title", "").strip()
                _id = item.get("_id", "")
                if title and _id:
                    item["slug"] = "truyen/" + normalize_vietnamese_url(title) + "-" + _id[-8:]
            return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


@router.get("/api/browse")
async def browse_folder():
    """Opens a native folder selection dialog on the host machine with fallbacks."""
    import subprocess

    # 1. Try zenity
    try:
        proc = subprocess.run(
            ["zenity", "--file-selection", "--directory", "--title=Chọn thư mục đầu ra"], capture_output=True, text=True
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return {"path": os.path.abspath(proc.stdout.strip())}
    except FileNotFoundError:
        pass

    # 2. Try kdialog
    try:
        proc = subprocess.run(
            ["kdialog", "--getexistingdirectory", ".", "--title", "Chọn thư mục đầu ra"], capture_output=True, text=True
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return {"path": os.path.abspath(proc.stdout.strip())}
    except FileNotFoundError:
        pass

    # 3. Try tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder_selected = filedialog.askdirectory()
        root.destroy()
        if folder_selected:
            return {"path": os.path.abspath(folder_selected)}
    except ImportError:
        logger.error("Tkinter not found.")
        return {"error": "Tính năng này yêu cầu 'python3-tk' hoặc 'zenity'."}
    except Exception as e:
        logger.error(f"Error opening folder dialog: {e}")
        return {"error": str(e)}

    return {"path": None}


@router.get("/api/chapters")
async def get_chapters(slug: str):
    story_url = f"{BASE_URL}/{slug}"
    session_state = load_session(get_config_path(".vvr_session.json"))
    chapter_data = await get_chapter_tree_list(story_url, session_state=session_state)
    return chapter_data


@router.get("/api/story_info")
async def get_story_info(slug: str):
    """Fetches detailed story information."""
    try:
        session_state = load_session(get_config_path(".vvr_session.json"))
        cookies = {}
        if session_state and "cookies" in session_state:
            for c in session_state["cookies"]:
                cookies[c["name"]] = c["value"]

        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, timeout=30.0) as client:
            story_info = await lay_thong_tin_truyen(client, slug)
            return {
                "title": story_info.title,
                "author": story_info.author,
                "description": story_info.description,
                "genres": story_info.genres,
                "total_chapters": story_info.total_chapters,
                "word_count": story_info.word_count,
                "views": story_info.views,
                "cover_url": story_info.cover_url,
                "cover_path": story_info.cover_path,
            }
    except Exception as e:
        logger.error(f"Error fetching story info: {e}")
        return {"error": str(e)}


@router.get("/api/freesound/auth")
async def freesound_auth():
    """Returns the Freesound authorization URL."""
    try:
        from ...freesound_manager import FreesoundManager

        fs_manager = FreesoundManager()
        url = fs_manager.get_auth_url()
        return {"url": url}
    except Exception as e:
        logger.error(f"Error getting Freesound auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/freesound/callback", summary="Freesound OAuth Callback")
async def freesound_callback(req: FreesoundCallbackRequest):
    """Exchanges code for token and saves it."""
    try:
        from ...freesound_manager import FreesoundManager

        fs_manager = FreesoundManager()
        await fs_manager.exchange_code(req.code)
        return {"status": "success", "message": "Freesound authentication successful."}
    except Exception as e:
        logger.error(f"Error exchanging Freesound code: {e}")
        return {"error": str(e)}, 500


@router.get("/api/settings", summary="Get Server Settings")
async def get_settings():
    return load_vvr_settings()


@router.post("/api/settings", summary="Update Server Settings")
async def update_settings(settings: Settings):
    save_vvr_settings(settings)
    await download_queue.update_workers(settings.num_workers)
    return {"status": "ok"}


@router.post("/api/download", summary="Legacy Direct Download (v1)")
async def download_novel(req: DownloadRequest):
    task_id = str(uuid.uuid4())[:8]

    if not req.output_folder:
        settings = load_vvr_settings()
        if settings.default_output_folder and settings.default_output_folder != "novels":
            req.output_folder = os.path.join(settings.default_output_folder, sanitize_filename(req.slug.split("/")[-1]))

    active_tasks[task_id] = req
    await download_queue.add_task(req, task_id)
    return {"task_id": task_id}


@router.websocket("/ws/tasks")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/api/novels/manifest", summary="Get Novel Cinematic Manifest")
async def get_novel_manifest(path: str = Query(..., description="Path relative to default output folder")):
    """Reads and returns the JSON manifest for a given novel/chapter path."""
    settings = load_vvr_settings()
    base_dir = Path(settings.default_output_folder or "novels").absolute()

    if ".." in path:
        raise HTTPException(status_code=403, detail="Invalid path: Parent directory traversal not allowed")

    rel_path = path.lstrip("/")
    target_path = (base_dir / rel_path).resolve()

    if not target_path.is_relative_to(base_dir):
        raise HTTPException(status_code=403, detail="Access denied: Path is outside the novels directory")

    manifest_file = target_path / "manifest.json"
    if not manifest_file.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")

    try:
        with open(manifest_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading manifest at {manifest_file}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# --- Static file routes ---

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")


@router.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend not found</h1>"
