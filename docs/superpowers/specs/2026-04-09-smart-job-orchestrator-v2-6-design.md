# Spec: Smart Job Orchestrator v2.6 Design

**Ngày:** 2026-04-09
**Trạng thái:** Draft
**Mục tiêu:** Nâng cấp hệ thống quản lý tác vụ (Job Orchestrator) để hỗ trợ chuỗi tác vụ (Chaining), quản lý tài nguyên thông minh (Resource Management), tự động cập nhật (Auto-Sync) và khôi phục sau sự cố (Persistence).

## 1. Tổng quan (Overview)
Hệ thống Job Orchestrator v2.6 chuyển đổi từ việc xử lý các Job đơn lẻ, tuần tự sang một hệ thống điều phối thông minh hơn. Hệ thống này có khả năng hiểu các mối quan hệ phụ thuộc giữa các Job, giới hạn tài nguyên CPU/RAM dựa trên loại tác vụ và tự động hóa quy trình cập nhật thư viện truyện.

## 2. Các tính năng chính (Core Features)

### 2.1. Cải tiến Manifest & Payload
*   **Hỗ trợ mảng Job:** File Manifest JSON (`vvrt run manifest.json`) giờ đây có thể chứa một danh sách các Job (`Array[Job]`).
*   **Phụ thuộc tác vụ (Chaining):** Mỗi Job có thể có trường `depends_on` trỏ đến `id` của Job khác. Job phụ thuộc sẽ ở trạng thái `waiting` cho đến khi Job gốc thành công.
*   **Phạm vi Crawl (Range Selection):** `ScrapePayload` hỗ trợ `from_chapter` và `to_chapter` (số nguyên) để tải một khoảng chương cụ thể.
*   **Đầy đủ tùy chọn:** Hỗ trợ tất cả các tùy chọn từ CLI/WebUI: `grouping`, `skip_illustrations`, `tasks`, `font`, `fps`, `render_format`.

### 2.2. Khả năng chịu lỗi & Phục hồi (Persistence)
*   **Tự động tải lại:** Khi khởi động, `JobWorker` sẽ quét SQLite để tìm các Job có trạng thái `pending` và đưa chúng trở lại hàng đợi.
*   **Xử lý Job bị ngắt quãng:** Các Job ở trạng thái `running` khi hệ thống bị tắt sẽ được đánh dấu là `failed` với thông báo lỗi rõ ràng, cho phép người dùng `Retry`.

### 2.3. Điều phối tài nguyên thông minh (Smart Resource Management)
Sử dụng `asyncio.Semaphore` để giới hạn số lượng tác vụ chạy song song:
*   **Crawl Semaphores (Light):** Tối đa 3-5 Job (Mặc định: 3).
*   **Heavy Semaphores (Audio/Video):** Tối đa 1 Job duy nhất tại một thời điểm để tránh quá tải CPU/RAM.

### 2.4. Tự động cập nhật (Auto-Sync)
*   **Cơ chế:** Một background task chạy định kỳ (1 giờ/lần) để kiểm tra thư viện truyện.
*   **Điều kiện kích hoạt:** Chỉ hoạt động khi biến môi trường `VVR_AUTO_SYNC=1` được thiết lập.
*   **Hành động:** Tự động tạo Job `crawl` cho các truyện có chương mới (`has_updates=1`).

## 3. Kiến trúc kỹ thuật (Technical Architecture)

### 3.1. Trạng thái Job & Luồng xử lý (Job Flow)
*   `pending`: Đang nằm trong hàng đợi, sẵn sàng chạy.
*   `waiting`: Đang chờ Job gốc hoàn thành.
*   `running`: Đang thực thi.
*   `success`: Hoàn thành thành công.
*   `failed`: Thất bại do lỗi hoặc do hệ thống bị ngắt quãng.
*   `cancelled`: Bị hủy (thường do Job gốc bị thất bại).

**Cơ chế Dependency (DAG):**
*   **Validation:** Trước khi nạp Manifest, hệ thống thực hiện kiểm tra đồ thị có hướng không chu trình (Directed Acyclic Graph - DAG) để phát hiện và ngăn chặn vòng lặp phụ thuộc (Deadlock).
*   **Alias Mapping:** Hỗ trợ ánh xạ `id` người dùng đặt trong JSON (`alias_id`) sang `job_id` thực tế (UUID) trong Database.
*   **Hủy đệ quy (Recursive Cancel):** Khi một Job thất bại, trạng thái `cancelled` sẽ được lan truyền xuống tất cả các Job phụ thuộc trực tiếp và gián tiếp trong cùng một Batch.

### 3.2. Cấu trúc Database (SQLite)
*   Bảng `jobs`:
    *   `alias_id` (TEXT): ID định danh trong Manifest.
    *   `batch_id` (TEXT): ID nhóm các Job được nạp cùng lúc từ một Manifest.
    *   `depends_on` (TEXT, Nullable): ID của Job gốc cần chờ.
    *   `priority` (INTEGER): Độ ưu tiên (Render > Crawl).
*   Bảng `schedules`: Quản lý cấu hình tự động cập nhật (`VVR_AUTO_SYNC`).

### 3.3. Điều phối tài nguyên & Ưu tiên (Scheduling)
*   **Priority Queue:** `JobWorker` ưu tiên xử lý các tác vụ có `priority` cao hơn (ví dụ: Video Render) trước các tác vụ `crawl` thông thường.
*   **Resource Semaphores:** 
    *   `Crawl`: 3-5 concurrent tasks.
    *   `Heavy` (Audio Drama / MP4): Duy nhất 1 task tại một thời điểm.
    *   **Safety:** Luôn sử dụng khối `try...finally` để giải phóng Semaphore ngay cả khi Job thất bại.

### 3.4. Quản lý theo đợt (Batch Management)
*   Hệ thống cung cấp API `/api/jobs/batch/<batch_id>` để theo dõi tiến độ tổng thể của cả một chuỗi tác vụ.


## 4. Kế hoạch kiểm thử (Testing Plan)
*   **Unit Tests:** Kiểm tra việc parse Manifest JSON mới với mảng và dependency.
*   **Integration Tests:** Mô phỏng chuỗi Job A thành công -> B chạy, và A thất bại -> B bị hủy.
*   **Persistence Tests:** Giả lập tắt server khi Job đang chạy và kiểm tra trạng thái sau khi restart.
*   **Resource Tests:** Chạy nhiều Job nặng cùng lúc và đảm bảo hệ thống chỉ thực thi 1 Job tại một thời điểm.
