"""
FastAPI web server for the Valvrare Team Scraper.
"""
import asyncio
import os
import uuid
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger
import json
from datetime import datetime

from .scraper_core import lay_thong_tin_truyen, scrape_chapters
from .exporter import (
    tao_file_epub, tao_file_pdf, tao_file_html, tao_file_md, tao_file_txt, tao_file_mp3
)
from .utils import (
    sanitize_filename, HEADERS, normalize_vietnamese_url, get_token_from_state
)
from .session_manager import load_session, save_session
from .tao_so_do_cay import get_chapter_tree_list
from playwright.async_api import async_playwright
from .db import DatabaseManager

class DownloadManager:
    def __init__(self, num_workers: int = 1):
        self.queue = asyncio.Queue()
        self.workers = []
        self.num_workers = num_workers

    async def start_workers(self):
        logger.info(f"Starting {self.num_workers} download workers...")
        for _ in range(self.num_workers):
            worker = asyncio.create_task(self.worker_loop())
            self.workers.append(worker)

    async def stop_workers(self):
        logger.info("Stopping download workers...")
        for worker in self.workers:
            worker.cancel()
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
            self.workers = []

    async def update_workers(self, new_num: int):
        if new_num == self.num_workers:
            return
        logger.info(f"Updating download workers from {self.num_workers} to {new_num}...")
        await self.stop_workers()
        self.num_workers = new_num
        await self.start_workers()

    async def worker_loop(self):
        while True:
            try:
                req, task_id = await self.queue.get()
                # Use contextualize to bind task_id to logs in this worker
                with logger.contextualize(task_id=task_id):
                    await run_scrape_task(req, task_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker encountered error: {e}")
            finally:
                self.queue.task_done()

    async def add_task(self, req: "DownloadRequest", task_id: str):
        await manager.broadcast({"type": "status", "task_id": task_id, "status": "In Queue..."})
        await self.queue.put((req, task_id))

download_queue = DownloadManager(num_workers=1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db = DatabaseManager()
    await app.state.db.init_db()
    await download_queue.start_workers()
    yield
    # Shutdown
    await download_queue.stop_workers()

app = FastAPI(title="Valvrare Team Scraper Web UI", lifespan=lifespan)

BASE_URL = "https://valvrareteam.net"
SSR_API_URL = "https://val-ssr-2kzit.ondigitalocean.app/api/novels/search"

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

def websocket_sink(message):
    """Loguru sink that broadcasts logs via WebSocket and buffers them."""
    record = message.record
    task_id = record["extra"].get("task_id", "system")
    log_msg = {
        "type": "log",
        "task_id": task_id,
        "level": record["level"].name,
        "message": record["message"],
        "time": record["time"].strftime("%H:%M:%S")
    }
    
    # Buffer logs
    if task_id != "system":
        if task_id not in task_log_buffers:
            task_log_buffers[task_id] = []
        task_log_buffers[task_id].append(log_msg)
        if len(task_log_buffers[task_id]) > 1000:
            task_log_buffers[task_id].pop(0)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(log_msg), loop)
    except Exception:
        pass

# Add sink to loguru
logger.add(websocket_sink, level="DEBUG")

class DownloadRequest(BaseModel):
    slug: str
    formats: List[str] = ["EPUB"]
    grouping: str = "tatca"
    tasks: int = 5
    skip_illustrations: bool = False
    output_folder: Optional[str] = None
    selected_urls: Optional[List[str]] = None

class Settings(BaseModel):
    num_workers: int = 1
    default_output_folder: str = ""

SETTINGS_FILE = "vvr_settings.json"

def load_vvr_settings() -> Settings:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return Settings(**json.load(f))
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    return Settings()

def save_vvr_settings(settings: Settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings.dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")

active_tasks = {}
active_tasks_futures: Dict[str, asyncio.Task] = {}
task_log_buffers: Dict[str, List[dict]] = {}

async def run_scrape_task(req: DownloadRequest, task_id: str):
    """Orchestrates the scraping task and sends progress via WebSocket."""
    active_tasks_futures[task_id] = asyncio.current_task()
    try:
        await manager.broadcast({"type": "status", "task_id": task_id, "status": "Resolving story..."})
        
        session_state = load_session(".vvr_session.json")
        cookies = {}
        if session_state and 'cookies' in session_state:
            for c in session_state['cookies']:
                cookies[c['name']] = c['value']
        
        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
            story_info = await lay_thong_tin_truyen(client, req.slug)
            
        await manager.broadcast({"type": "info", "task_id": task_id, "title": story_info.title})
        
        output_folder = req.output_folder or sanitize_filename(story_info.title)
        os.makedirs(output_folder, exist_ok=True)
        checkpoint_file = os.path.join(output_folder, ".vvr_checkpoint.json")
        checkpoint = {"slug": req.slug, "title": story_info.title, "scraped": {}}
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "scraped" in data:
                        checkpoint = data
                    else:
                        # Migration for old checkpoints that only stored the 'scraped' dict
                        checkpoint["scraped"] = data
                logger.info(f"Loaded checkpoint for task {task_id}. Skipping {len(checkpoint['scraped'])} chapters.")
            except Exception as e:
                logger.error(f"Error loading checkpoint: {e}")

        if req.selected_urls:
            urls = req.selected_urls
            logger.info(f"Using {len(urls)} selected URLs for download")
        else:
            story_url = f"{BASE_URL}/{req.slug}"
            chapter_data = await get_chapter_tree_list(story_url, output_file=f"chapters_{task_id}.json", session_state=session_state)

            if not chapter_data:
                if os.path.exists(f"chapters_{task_id}.json"):
                    with open(f"chapters_{task_id}.json", "r", encoding="utf-8") as f:
                        chapter_data = json.load(f)
                else:
                    raise Exception("Could not retrieve chapter list. Please check if the novel exists or try again.")

            if os.path.exists(f"chapters_{task_id}.json"):
                os.remove(f"chapters_{task_id}.json")

            selected_chaps = [c for v in chapter_data for c in v['chapters']]
            if req.skip_illustrations:
                selected_chaps = [c for c in selected_chaps if "Minh họa" not in c['title']]

            urls = [f"{BASE_URL}{c['url']}" for c in selected_chaps]
        
        total = len(urls)
        
        token = get_token_from_state(session_state)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            scraped = {}
            # Pre-load from checkpoint
            for url, content in checkpoint.get("scraped", {}).items():
                if url in urls:
                    scraped[url] = content

            semaphore = asyncio.Semaphore(req.tasks)
            
            async def process_url(url, idx):
                if url in scraped:
                    percent = int(((idx + 1) / total) * 100)
                    await manager.broadcast({
                        "type": "progress", 
                        "task_id": task_id, 
                        "percent": percent,
                        "msg": f"Resumed {idx+1}/{total} chapters (from checkpoint)"
                    })
                    return

                async with semaphore:
                    from .scraper_core import lay_chuong_httpx, lay_chuong_voi_hinh_anh
                    content = None
                    async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, follow_redirects=True) as client:
                        content = await lay_chuong_httpx(client, url, token=token)
                    if not content:
                        content = await lay_chuong_voi_hinh_anh(browser, url, session_state=session_state)
                    
                    if content:
                        scraped[url] = content
                        # Update checkpoint immediately
                        checkpoint["scraped"][url] = content
                        checkpoint["slug"] = req.slug
                        checkpoint["title"] = story_info.title
                        with open(checkpoint_file, "w", encoding="utf-8") as f:
                            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                    
                    percent = int(((idx + 1) / total) * 100)
                    await manager.broadcast({
                        "type": "progress", 
                        "task_id": task_id, 
                        "percent": percent,
                        "msg": f"Downloaded {idx+1}/{total} chapters"
                    })

            tasks = [process_url(url, i) for i, url in enumerate(urls)]
            await asyncio.gather(*tasks)
            await browser.close()

        await manager.broadcast({"type": "status", "task_id": task_id, "status": "Exporting files..."})
        
        full_flat = []
        for url in urls:
            if url in scraped:
                full_flat.extend(scraped[url])
        
        for fmt in req.formats:
            fpath = os.path.join(output_folder, f"{sanitize_filename(story_info.title)}.{fmt.lower()}")
            if fmt == "PDF": await tao_file_pdf(full_flat, fpath, story_info.title)
            elif fmt == "EPUB": await tao_file_epub(fpath, story_info.title, story_info.author, [{'title': 'All Chapters', 'content': full_flat}], story_info.description, story_info.cover_path, story_info.genres)
            elif fmt == "HTML": await tao_file_html(full_flat, fpath, story_info.title)
            elif fmt == "MD": await tao_file_md(full_flat, fpath, story_info.title)
            elif fmt == "TXT": await tao_file_txt(full_flat, fpath, story_info.title)
            elif fmt == "MP3": await tao_file_mp3(full_flat, fpath, story_info.title)

        # Update library DB with latest stats
        await app.state.db.upsert_novel({
            "title": story_info.title,
            "slug": req.slug,
            "author": story_info.author,
            "last_chapter_count": len(urls),
            "last_downloaded_at": datetime.now().isoformat(),
            "output_folder": output_folder,
            "formats": ",".join(req.formats)
        })

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
    finally:
        if task_id in active_tasks_futures:
            del active_tasks_futures[task_id]

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/tasks/{task_id}/logs")
async def get_task_logs(task_id: str):
    return task_log_buffers.get(task_id, [])

@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    if task_id in active_tasks_futures:
        active_tasks_futures[task_id].cancel()
        return {"status": "pausing"}
    return {"status": "not_running"}

@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    if task_id in active_tasks:
        req = active_tasks[task_id]
        await download_queue.add_task(req, task_id)
        return {"status": "resuming"}
    return {"status": "task_not_found", "error": "Task request not found in active_tasks. Cannot resume."}

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if task_id in active_tasks_futures:
        active_tasks_futures[task_id].cancel()
    if task_id in active_tasks:
        del active_tasks[task_id]
    if task_id in task_log_buffers:
        del task_log_buffers[task_id]
    return {"status": "cancelled"}

@app.get("/api/search")
async def search_novels(q: str = Query(..., min_length=3)):
    """Proxies search requests to the Valvrare Team API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "User-Agent": HEADERS["User-Agent"],
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/",
                "Accept": "application/json, text/plain, */*"
            }
            url = f"{SSR_API_URL}?title={q}"
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            results = response.json()
            
            for item in results:
                title = item.get('title', '').strip()
                _id = item.get('_id', '')
                if title and _id:
                    item['slug'] = "truyen/" + normalize_vietnamese_url(title) + "-" + _id[-8:]
            return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

@app.get("/api/browse")
async def browse_folder():
    """Opens a native folder selection dialog on the host machine with fallbacks."""
    import os
    import subprocess

    # 1. Try zenity (common on Linux)
    try:
        proc = subprocess.run(
            ['zenity', '--file-selection', '--directory', '--title=Chọn thư mục đầu ra'],
            capture_output=True, text=True
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return {"path": os.path.abspath(proc.stdout.strip())}
    except FileNotFoundError:
        pass

    # 2. Try kdialog (KDE fallback)
    try:
        proc = subprocess.run(
            ['kdialog', '--getexistingdirectory', '.', '--title', 'Chọn thư mục đầu ra'],
            capture_output=True, text=True
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return {"path": os.path.abspath(proc.stdout.strip())}
    except FileNotFoundError:
        pass

    # 3. Try tkinter (System fallback)
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder_selected = filedialog.askdirectory()
        root.destroy()
        if folder_selected:
            return {"path": os.path.abspath(folder_selected)}
    except ImportError:
        logger.error("Tkinter not found. Please install it (e.g., sudo zypper install python3-tk)")
        return {"error": "Tính năng này yêu cầu 'python3-tk' hoặc 'zenity'. Vui lòng cài đặt qua package manager của bạn."}
    except Exception as e:
        logger.error(f"Error opening folder dialog: {e}")
        return {"error": str(e)}

    return {"path": None}

@app.get("/api/chapters")
async def get_chapters(slug: str):
    story_url = f"{BASE_URL}/{slug}"
    session_state = load_session(".vvr_session.json")
    chapter_data = await get_chapter_tree_list(story_url, session_state=session_state)
    return chapter_data

@app.get("/api/story_info")
async def get_story_info(slug: str):
    """Fetches detailed story information."""
    try:
        session_state = load_session(".vvr_session.json")
        cookies = {}
        if session_state and 'cookies' in session_state:
            for c in session_state['cookies']:
                cookies[c['name']] = c['value']
        
        async with httpx.AsyncClient(headers=HEADERS, cookies=cookies) as client:
            story_info = await lay_thong_tin_truyen(client, slug)
            return {
                "title": story_info.title,
                "author": story_info.author,
                "description": story_info.description,
                "genres": story_info.genres,
                "total_chapters": story_info.total_chapters,
                "word_count": story_info.word_count,
                "cover_path": story_info.cover_path
            }
    except Exception as e:
        logger.error(f"Error fetching story info: {e}")
        return {"error": str(e)}

@app.get("/api/settings")
async def get_settings():
    return load_vvr_settings()

@app.post("/api/settings")
async def update_settings(settings: Settings):
    save_vvr_settings(settings)
    await download_queue.update_workers(settings.num_workers)
    return {"status": "ok"}

@app.post("/api/download")
async def download_novel(req: DownloadRequest):
    task_id = str(uuid.uuid4())[:8]
    
    # Use default output folder if not provided
    if not req.output_folder:
        settings = load_vvr_settings()
        if settings.default_output_folder:
            req.output_folder = os.path.join(settings.default_output_folder, sanitize_filename(req.slug.split('/')[-1]))

    active_tasks[task_id] = req
    await download_queue.add_task(req, task_id)
    return {"task_id": task_id}

@app.websocket("/ws/tasks")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend not found</h1>"

@app.get("/style.css")
async def get_css():
    css_path = os.path.join(static_dir, "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/css")

@app.get("/app.js")
async def get_js():
    js_path = os.path.join(static_dir, "app.js")
    if os.path.exists(js_path):
        with open(js_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="application/javascript")

async def run_web_server(host: str = "127.0.0.1", port: int = 8000, num_workers: Optional[int] = None):
    """Starts the Uvicorn server in the current event loop."""
    if num_workers is None:
        settings = load_vvr_settings()
        num_workers = settings.num_workers
    
    download_queue.num_workers = num_workers
    logger.info(f"Starting web server at http://{host}:{port} with {num_workers} workers")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
