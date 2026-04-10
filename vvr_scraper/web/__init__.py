"""
FastAPI web server for the Valvrare Team Scraper.
Refactored from monolithic web.py into modular routes.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger

from ..db import DatabaseManager
from ..job_worker import JobWorker
from ..utils import get_config_path
from .deps import get_current_user  # noqa: F401

# Re-export for backward compatibility
from .models import (  # noqa: F401
    BatchImportRequest,
    DownloadRequest,
    FreesoundCallbackRequest,
    Settings,
    load_vvr_settings,
    save_vvr_settings,
)
from .routes.download import run_scrape_task  # noqa: F401
from .routes.library import (  # noqa: F401
    auto_sync_background_task,
    check_library_updates,
    sync_all_novels,  # noqa: F401 — route function
)
from .state import (  # noqa: F401  # noqa: F401
    ConnectionManager,
    DownloadManager,
    _event_loop,
    active_tasks,
    active_tasks_futures,
    download_queue,
    manager,
    task_log_buffers,
    websocket_sink,
    worker,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import vvr_scraper.web.state as state

    # Startup
    state._event_loop = asyncio.get_running_loop()
    if not hasattr(app.state, "db") or app.state.db is None:
        app.state.db = DatabaseManager(db_path=get_config_path("vvr_library.db"))
        await app.state.db.init_db()

    # Universal Task Runner: Start JobWorker
    state.worker = JobWorker(app.state.db)
    await state.worker.start()

    # Start Auto-Sync Background Task

    asyncio.create_task(auto_sync_background_task(app.state.db, state.worker))

    await download_queue.start_workers()
    logger.warning("OPDS Server active. Tránh di chuyển thư mục truyện thủ công để không làm hỏng liên kết thư viện.")
    yield
    # Shutdown
    if state.worker:
        await state.worker.stop()
    await download_queue.stop_workers()
    if hasattr(app.state, "db") and app.state.db:
        await app.state.db.close()


app = FastAPI(
    title="Valvrare Team Scraper Web UI",
    version="1.9.1",
    description="API for managing scraper tasks, job queues, library syncing, and OPDS feeds.",
    lifespan=lifespan,
)

# Setup Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass

# Add loguru sink
logger.add(websocket_sink, level="DEBUG")

# Register routers
from .routes.api import router as api_router  # noqa: E402
from .routes.jobs import router as jobs_router  # noqa: E402
from .routes.library import router as library_router  # noqa: E402
from .routes.opds import opds_download_router  # noqa: E402
from .routes.opds import router as opds_router  # noqa: E402

app.include_router(api_router)
app.include_router(jobs_router)
app.include_router(library_router)
app.include_router(opds_router)
app.include_router(opds_download_router)

# Mount novel assets
vvr_settings_for_mount = load_vvr_settings()
novels_mount_dir = os.path.abspath(vvr_settings_for_mount.default_output_folder or "novels")
os.makedirs(novels_mount_dir, exist_ok=True)
app.mount("/novels", StaticFiles(directory=novels_mount_dir), name="novels")

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


async def run_web_server(host: str = "127.0.0.1", port: int = 8000, num_workers: int | None = None):
    """Starts the Uvicorn server in the current event loop."""
    if num_workers is None:
        settings = load_vvr_settings()
        num_workers = settings.num_workers

    download_queue.num_workers = num_workers
    logger.info(f"Starting web server at http://{host}:{port} with {num_workers} workers")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
