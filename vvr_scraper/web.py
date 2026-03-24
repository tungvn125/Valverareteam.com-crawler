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

from .scraper_core import lay_thong_tin_truyen, scrape_chapters
from .exporter import (
    tao_file_epub, tao_file_pdf, tao_file_html, tao_file_md, tao_file_txt
)
from .utils import (
    sanitize_filename, HEADERS, normalize_vietnamese_url, get_token_from_state
)
from .session_manager import load_session, save_session
from .tao_so_do_cay import get_chapter_tree_list
from playwright.async_api import async_playwright

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
        await asyncio.gather(*self.workers, return_exceptions=True)

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
    """Loguru sink that broadcasts logs via WebSocket."""
    record = message.record
    log_msg = {
        "type": "log",
        "level": record["level"].name,
        "message": record["message"],
        "time": record["time"].strftime("%H:%M:%S")
    }
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

active_tasks = {}

async def run_scrape_task(req: DownloadRequest, task_id: str):
    """Orchestrates the scraping task and sends progress via WebSocket."""
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
            semaphore = asyncio.Semaphore(req.tasks)
            
            async def process_url(url, idx):
                async with semaphore:
                    from .scraper_core import lay_chuong_httpx, lay_chuong_voi_hinh_anh
                    content = None
                    async with httpx.AsyncClient(headers=HEADERS, cookies=cookies, follow_redirects=True) as client:
                        content = await lay_chuong_httpx(client, url, token=token)
                    if not content:
                        content = await lay_chuong_voi_hinh_anh(browser, url, session_state=session_state)
                    
                    if content:
                        scraped[url] = content
                    
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
        
        # Use provided output folder or default to sanitized title
        output_folder = req.output_folder or sanitize_filename(story_info.title)
        os.makedirs(output_folder, exist_ok=True)
        
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

        await manager.broadcast({"type": "complete", "task_id": task_id, "path": output_folder})
        logger.success(f"Task {task_id} completed: {story_info.title}")
    except Exception as e:
        import traceback
        logger.error(f"Task {task_id} failed: {e}")
        logger.error(traceback.format_exc())
        await manager.broadcast({"type": "error", "task_id": task_id, "error": str(e)})
    finally:
        if task_id in active_tasks:
            del active_tasks[task_id]

@app.get("/health")
async def health_check():
    return {"status": "ok"}

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

@app.post("/api/download")
async def download_novel(req: DownloadRequest):
    task_id = str(uuid.uuid4())[:8]
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

async def run_web_server(host: str = "127.0.0.1", port: int = 8000):
    """Starts the Uvicorn server in the current event loop."""
    logger.info(f"Starting web server at http://{host}:{port}")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
