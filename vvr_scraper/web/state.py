"""
Shared state and services for the web server.
Global singletons that are accessed across route modules.
"""

import asyncio
from typing import TYPE_CHECKING

from fastapi import WebSocket
from loguru import logger

if TYPE_CHECKING:
    from ..job_worker import JobWorker


class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

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


class DownloadManager:
    """Manages the download task queue and worker pool."""

    def __init__(self, num_workers: int = 1):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.num_workers = num_workers

    async def start_workers(self):
        from .routes.download import run_scrape_task

        logger.info(f"Starting {self.num_workers} download workers...")
        for _ in range(self.num_workers):
            worker = asyncio.create_task(self._worker_loop(run_scrape_task))
            self.workers.append(worker)

    async def stop_workers(self):
        logger.info("Stopping download workers...")
        for w in self.workers:
            w.cancel()
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

    async def _worker_loop(self, task_fn):
        while True:
            try:
                req, task_id = await self.queue.get()
                with logger.contextualize(task_id=task_id):
                    await task_fn(req, task_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker encountered error: {e}")
            finally:
                self.queue.task_done()

    async def add_task(self, req, task_id: str):
        await manager.broadcast({"type": "status", "task_id": task_id, "status": "In Queue..."})
        await self.queue.put((req, task_id))


# --- Global Singletons ---

manager = ConnectionManager()
download_queue = DownloadManager(num_workers=1)
worker: "JobWorker | None" = None

# Task tracking
active_tasks: dict = {}
active_tasks_futures: dict[str, asyncio.Task] = {}
task_log_buffers: dict[str, list[dict]] = {}

# Event loop reference for websocket sink
_event_loop: asyncio.AbstractEventLoop | None = None


def websocket_sink(message):
    """Loguru sink that broadcasts logs via WebSocket and buffers them."""
    record = message.record
    task_id = record["extra"].get("task_id", "system")
    log_msg = {
        "type": "log",
        "task_id": task_id,
        "level": record["level"].name,
        "message": record["message"],
        "time": record["time"].strftime("%H:%M:%S"),
    }

    # Buffer logs
    if task_id != "system":
        if task_id not in task_log_buffers:
            task_log_buffers[task_id] = []
        task_log_buffers[task_id].append(log_msg)
        if len(task_log_buffers[task_id]) > 1000:
            task_log_buffers[task_id].pop(0)

    try:
        if _event_loop and _event_loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(log_msg), _event_loop)
    except Exception as e:
        print(f"Failed to broadcast log via WebSocket: {e}")
