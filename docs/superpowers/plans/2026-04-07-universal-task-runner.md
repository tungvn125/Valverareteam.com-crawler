# Universal Task Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng hệ thống điều phối tác vụ tập trung dựa trên file JSON (vvrt run), hỗ trợ hàng đợi an toàn, lập lịch tự động và báo cáo lỗi chi tiết cho Production.

**Architecture:**
1. **Validation:** Dùng Pydantic Discriminated Unions để kiểm tra chặt chẽ file Manifest.
2. **Concurrency:** Sử dụng `asyncio.Queue(maxsize=100)` phối hợp với `asyncio.to_thread` để không làm treo Event Loop khi chạy task nặng.
3. **Storage:** Bật SQLite WAL mode để hỗ trợ đọc/ghi đồng thời giữa Worker và WebUI.
4. **Reliability:** Cơ chế tự động capture lỗi, đính kèm Manifest vào log và lưu tiến trình vào DB.

**Tech Stack:** Pydantic v2, asyncio, aiosqlite, FastAPI, Loguru.

---

### Task 1: Định nghĩa Data Models & Cập nhật Database

**Files:**
- Create: `vvr_scraper/job_models.py`
- Modify: `vvr_scraper/db.py`

- [ ] **Step 1: Tạo `job_models.py` với Discriminated Unions.**

```python
from typing import Literal, Union, List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ScrapePayload(BaseModel):
    slug: str
    chapters: Optional[str] = "all"
    formats: List[str] = ["EPUB"]

class ServerPayload(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    opds_password: str = "password"

class JobManifest(BaseModel):
    version: str = "1.1"
    task: Literal["crawl", "server", "render"]
    payload: Union[ScrapePayload, ServerPayload, Dict[str, Any]] = Field(..., discriminator="task")
    automation: Optional[Dict[str, Any]] = None
```

- [ ] **Step 2: Cập nhật `vvr_scraper/db.py` để thêm bảng `jobs` và bật WAL mode.**

```python
        # Trong init_db()
        await db.execute("PRAGMA journal_mode=WAL") # Bật WAL mode
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                task_type TEXT,
                status TEXT,
                progress INTEGER DEFAULT 0,
                payload TEXT,
                error_summary TEXT,
                error_log_path TEXT,
                created_at DATETIME,
                finished_at DATETIME
            )
        """)
```

- [ ] **Step 3: Commit.**
`git commit -m "feat: define job models and update database schema with WAL mode"`

---

### Task 2: Xây dựng Task Worker & Queue Logic

**Files:**
- Create: `vvr_scraper/job_worker.py`

- [ ] **Step 1: Triển khai `JobWorker` với hàng đợi an toàn.**
Sử dụng `asyncio.Queue` và một vòng lặp `while True` để xử lý job.

- [ ] **Step 2: Triển khai cơ chế Error Logging chuyên nghiệp.**
Hàm `handle_failure(job_id, manifest, exception)` để tạo file trong `error-logs/` và đính kèm manifest.

- [ ] **Step 3: Commit.**
`git commit -m "feat: implement background task worker and error reporting engine"`

---

### Task 3: Triển khai Orchestrator & CLI Integration

**Files:**
- Create: `vvr_scraper/job_runner.py`
- Modify: `vvr_scraper/cli.py`

- [ ] **Step 1: Viết `job_runner.py` để parse JSON và khởi động luồng tương ứng.**

- [ ] **Step 2: Thêm subcommand `run` vào `cli.py`.**

```python
        parser_run = subparsers.add_parser('run', help='Chạy nhiệm vụ từ file JSON manifest.')
        parser_run.add_argument('manifest', help='Đường dẫn tới file manifest.json')
```

- [ ] **Step 3: Commit.**
`git commit -m "feat: add vvrt run command and orchestrator logic"`

---

### Task 4: Tích hợp Server & WebUI Monitoring

**Files:**
- Modify: `vvr_scraper/web.py`

- [ ] **Step 1: Kích hoạt Worker trong `startup` của FastAPI.**

- [ ] **Step 2: Thêm endpoint `/api/jobs` để theo dõi trạng thái từ WebUI.**

- [ ] **Step 3: Commit.**
`git commit -m "feat: integrate job worker into web server life cycle"`

---

### Task 5: Kiểm thử Toàn diện (Validation)

**Files:**
- Create: `tests/test_job_runner.py`

- [ ] **Step 1: Viết test case kiểm tra validation JSON.**
- [ ] **Step 2: Test giả lập lỗi để xác nhận log được ghi đúng chuẩn.**
- [ ] **Step 3: Commit.**
`git commit -m "test: add comprehensive tests for universal task runner"`
