"""
FastAPI web server for the Valvrare Team Scraper.
"""
import asyncio
import os
from typing import List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from loguru import logger
import json

from .utils import HEADERS, normalize_vietnamese_url

app = FastAPI(title="Valvrare Team Scraper Web UI")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
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
    # We need to run this in the app's event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(log_msg), loop)
    except Exception:
        pass

# Add sink to loguru
logger.add(websocket_sink, level="DEBUG")

@app.websocket("/ws/tasks")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/health")
SSR_API_URL = "https://val-ssr-2kzit.ondigitalocean.app/api/novels/search"

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
            
            # Add slug to results for the UI
            for item in results:
                title = item.get('title', '').strip()
                _id = item.get('_id', '')
                if title and _id:
                    item['slug'] = normalize_vietnamese_url(title) + "-" + _id[-8:]
            
            return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

def run_web_server(host: str = "127.0.0.1", port: int = 8000):
    """Starts the Uvicorn server."""
    logger.info(f"Starting web server at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
