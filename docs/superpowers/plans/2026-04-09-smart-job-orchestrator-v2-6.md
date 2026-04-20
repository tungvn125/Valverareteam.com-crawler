# Smart Job Orchestrator v2.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng cấp Job Orchestrator để hỗ trợ chuỗi tác vụ (dependency), quản lý tài nguyên thông minh (semaphores), và khôi phục sau sự cố (persistence).

**Architecture:** Sử dụng `asyncio.PriorityQueue` để thay thế Queue hiện tại, kết hợp với `asyncio.Semaphore` để giới hạn tài nguyên. Thêm logic DAG validation cho Manifest JSON.

**Tech Stack:** Python 3.10+, aiosqlite, pydantic v2, asyncio.

---

### Task 1: Update Database Schema & Models

**Files:**
- Modify: `vvr_scraper/db.py`
- Modify: `vvr_scraper/job_models.py`
- Test: `tests/test_db_jobs_v26.py`

- [ ] **Step 1: Thêm cột mới vào bảng `jobs` trong `db.py`**
    - Cột: `alias_id` (TEXT), `batch_id` (TEXT), `depends_on` (TEXT), `priority` (INTEGER), `from_chapter` (INTEGER), `to_chapter` (INTEGER).
    - Cập nhật hàm `init_db` và `create_job`, `upsert_novel`.

- [ ] **Step 2: Cập nhật Pydantic Models trong `job_models.py`**
    - `ScrapePayload`: Thêm `from_chapter`, `to_chapter`, `grouping`, `skip_illustrations`.
    - `JobManifest`: Hỗ trợ `List[Job]` và các trường `id`, `depends_on`.

- [ ] **Step 3: Viết test kiểm tra schema mới**
    - Tạo file `tests/test_db_jobs_v26.py` và chạy `pytest`.

- [ ] **Step 4: Commit**
    ```bash
    git add vvr_scraper/db.py vvr_scraper/job_models.py tests/test_db_jobs_v26.py
    git commit -m "db/models: update schema and models for v2.6"
    ```

### Task 2: Implement Manifest Parser & DAG Validation

**Files:**
- Create: `vvr_scraper/job_parser.py`
- Modify: `vvr_scraper/job_runner.py`
- Test: `tests/test_job_parser.py`

- [ ] **Step 1: Tạo `vvr_scraper/job_parser.py`**
    - Viết hàm `parse_manifest(json_data)` để xử lý mảng Job.
    - Viết logic kiểm tra vòng lặp phụ thuộc (DAG validation).
    - Map `alias_id` sang UUID thực tế.

- [ ] **Step 2: Cập nhật `job_runner.py`**
    - Sửa `run_manifest` để sử dụng parser mới và nạp chuỗi Job vào DB.

- [ ] **Step 3: Viết test cho Parser**
    - Đảm bảo phát hiện được vòng lặp (A->B, B->A) và nạp đúng metadata.

- [ ] **Step 4: Commit**
    ```bash
    git add vvr_scraper/job_parser.py vvr_scraper/job_runner.py tests/test_job_parser.py
    git commit -m "feat: add manifest parser with DAG validation"
    ```

### Task 3: Upgrade JobWorker with Smart Queue & Resource Control

**Files:**
- Modify: `vvr_scraper/job_worker.py`
- Test: `tests/test_job_worker_v26.py`

- [ ] **Step 1: Thay đổi `asyncio.Queue` thành `asyncio.PriorityQueue`**
    - Ưu tiên các Job có `priority` cao (Video/Audio).

- [ ] **Step 2: Triển khai Semaphores trong `worker_loop`**
    - `crawl_semaphore` (3), `heavy_semaphore` (1).
    - Sử dụng `try...finally` để giải phóng semaphore.

- [ ] **Step 3: Triển khai Persistence Recovery**
    - Trong `start()`, quét DB tìm `pending` jobs và `running` jobs (để đánh dấu `failed`).

- [ ] **Step 4: Triển khai Recursive Cancellation**
    - Khi một job lỗi, tự động tìm và hủy các job phụ thuộc trong DB.

- [ ] **Step 5: Commit**
    ```bash
    git add vvr_scraper/job_worker.py tests/test_job_worker_v26.py
    git commit -m "feat: smart queue with semaphores and recovery"
    ```

### Task 4: Auto-Sync Background Task

**Files:**
- Modify: `vvr_scraper/web.py`
- Test: `tests/test_auto_sync.py`

- [ ] **Step 1: Thêm background loop trong `web.py`**
    - Kiểm tra `os.getenv("VVR_AUTO_SYNC") == "1"`.
    - Gọi `check_library_updates` và tạo Job tự động.

- [ ] **Step 2: Commit**
    ```bash
    git add vvr_scraper/web.py
    git commit -m "feat: add optional auto-sync background task"
    ```
