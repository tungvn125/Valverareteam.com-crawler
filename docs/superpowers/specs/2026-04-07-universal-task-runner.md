# Spec: Universal Task Runner & Unified Scheduler

## 1. Overview
Chuyển đổi `vvr-scraper` thành một hệ thống điều phối tác vụ (Task Orchestrator) dựa trên cấu hình khai báo (Declarative Configuration). Sử dụng một tệp JSON duy nhất để điều khiển toàn bộ các hoạt động từ quét truyện, render video đến vận hành server và lập lịch tự động.

## 2. Architecture

### 2.1. Entry Point
- Lệnh CLI mới: `vvrt run <manifest.json>`
- Chức năng: Đọc, kiểm tra tính hợp lệ (validate) và thực thi kịch bản được định nghĩa trong JSON.

### 2.2. Job Manifest Schema (Pydantic Models)
Tệp JSON sẽ được ánh xạ vào các lớp Python để đảm bảo kiểu dữ liệu:
- `task`: Loại nhiệm vụ (`server`, `crawl`, `render`).
- `payload`: Tham số thực thi cụ thể cho từng loại task.
- `automation`: Danh sách các lịch trình (`schedules`) thực thi tác vụ ngầm.

### 2.3. Unified Server & Background Worker
Khi `task == "server"`:
1. Khởi chạy ứng dụng FastAPI hiện có (WebUI + OPDS).
2. Kích hoạt một **Background Worker** chạy song song.
3. Worker sử dụng một `asyncio.Queue` để nhận các yêu cầu tác vụ.
4. Tác vụ được thực hiện theo cơ chế **FIFO (First In, First Out)** - chỉ một tác vụ nặng chạy tại một thời điểm để đảm bảo an toàn tài nguyên.

### 2.4. Database Persistence (SQLite)
Thêm bảng `jobs` vào `vvr_library.db`:
- `id`: TEXT (UUID) PRIMARY KEY
- `task_type`: TEXT
- `status`: TEXT (pending, running, success, failed)
- `payload`: TEXT (JSON string của manifest)
- `created_at`: DATETIME
- `finished_at`: DATETIME
- `error_log`: TEXT (Đường dẫn file log lỗi)

## 3. Error Handling & Logging (Production Ready)
- Mọi lỗi trong quá trình chạy ngầm đều được bắt gọn (`try...except`).
- Khi có lỗi:
    1. Tạo file log tại `error-logs/job_<id>_<timestamp>.log`.
    2. Ghi nội dung Manifest đã dùng vào đầu file log.
    3. Ghi toàn bộ Stack Trace của lỗi.
    4. Cập nhật trạng thái `failed` và đường dẫn log vào DB.

## 4. Implementation Steps

### Phase 1: Models & DB
- Định nghĩa Pydantic models cho Manifest.
- Cập nhật `DatabaseManager` để tạo và quản lý bảng `jobs`.

### Phase 2: The Orchestrator
- Viết module `job_runner.py` để xử lý logic `vvrt run`.
- Xây dựng lớp `TaskWorker` điều phối hàng đợi `asyncio.Queue`.

### Phase 3: CLI & Server Integration
- Thêm sub-command `run` vào `cli.py`.
- Tích hợp Background Worker vào vòng đời khởi động của FastAPI trong `web.py`.

## 5. Verification
- Chạy thử các file manifest mẫu cho `crawl`, `server`.
- Giả lập lỗi để kiểm tra việc ghi log vào `error-logs/`.
- Kiểm tra tính tuần tự của hàng đợi khi đẩy nhiều task cùng lúc.
