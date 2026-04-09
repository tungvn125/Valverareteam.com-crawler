# Hướng dẫn Smart Job Orchestrator v2.6 (vvrt run)

Hệ thống cho phép bạn tự động hóa và điều phối các quy trình phức tạp (Scraping, Rendering, Chaining) thông qua một file JSON duy nhất.

## Cách chạy
```bash
vvrt run <path_to_manifest.json>
```

## Định dạng File Manifest

Kể từ phiên bản v2.6, Manifest hỗ trợ cả **Job đơn lẻ** (Object) hoặc **Danh sách Job** (Array).

### 1. Cấu trúc chung (Base Job)
Mọi loại Job đều hỗ trợ các trường định danh và điều phối sau:
*   `alias_id`: (Tùy chọn) Tên gợi nhớ để các Job khác có thể tham chiếu (ví dụ: `"job_1"`).
*   `depends_on`: (Tùy chọn) Danh sách các `alias_id` mà Job này cần chờ hoàn thành thành công mới bắt đầu chạy (ví dụ: `["job_1"]`).
*   `priority`: (Tùy chọn) Độ ưu tiên. Số nhỏ hơn sẽ chạy trước. Mặc định: Render (1), Audio (2), Crawl (3).
*   `batch_id`: (Tùy chọn) ID nhóm để theo dõi tiến độ cả đợt. Nếu không có, hệ thống tự sinh theo thời gian.

### 2. Crawl Job (Tải truyện và xuất file)
Sử dụng để tải truyện từ web và chuyển đổi sang các định dạng đa phương tiện.

```json
{
  "alias_id": "step_1",
  "task": "crawl",
  "payload": {
    "slug": "ten-truyen-slug-12345678",
    "formats": ["EPUB", "PDF", "MP4"],
    "from_chapter": 1,
    "to_chapter": 50,
    "grouping": 1,
    "skip_illustrations": true,
    "output_folder": "novels/my-story"
  }
}
```
*   `slug`: Đường dẫn định danh của truyện trên Valvrare Team.
*   `formats`: Danh sách định dạng muốn xuất. Hỗ trợ: `EPUB`, `PDF`, `HTML`, `MD`, `TXT`, `MP3`, `MP4`, `CINEMA`, `AD-MP3`.
*   `from_chapter` / `to_chapter`: (Tùy chọn) Phạm vi chương muốn tải.
*   `chapters`: (Tùy chọn) Danh sách ID chương cụ thể (ưu tiên hơn range).
*   `grouping`: (Tùy chọn) Cách gộp chương (1: Từng chương, 2: Từng Volume, 0: Tất cả vào một file).
*   `skip_illustrations`: (Tùy chọn) `true` để bỏ qua các chương minh họa.
*   `output_folder`: (Tùy chọn) Đường dẫn tới thư mục lưu trữ kết quả. Nếu bỏ trống, hệ thống tự động đặt tên theo tên truyện.

### 3. Render Job (Tạo Video Cinematic)
Sử dụng để render video từ file `manifest.json` đã có sẵn.

```json
{
  "task": "render",
  "depends_on": ["step_1"],
  "payload": {
    "manifest_path": "novels/slug/manifest.json",
    "output_path": "exports/my_video.mp4",
    "fps": 30,
    "render_format": "landscape"
  }
}
```

## Tính năng nâng cao

### Chuỗi tác vụ (Dependency Chaining)
Hệ thống sử dụng **Topological Sort** để đảm bảo các Job phụ thuộc luôn chạy đúng thứ tự, ngay cả khi bạn khai báo sai thứ tự trong file JSON. Nếu Job gốc thất bại, toàn bộ chuỗi phụ thuộc phía sau sẽ bị hủy (`cancelled`).

### Quản lý tài nguyên (Smart Semaphores)
Để tránh treo máy, hệ thống giới hạn:
*   **Crawl/Light Jobs:** Tối đa 3 Job chạy song song.
*   **Heavy Jobs (MP4/Audio):** Duy nhất 1 Job chạy tại một thời điểm.

### Tự động cập nhật (Auto-Sync)
Nếu bạn thiết lập biến môi trường `VVR_AUTO_SYNC=1`, hệ thống sẽ tự động quét thư viện mỗi giờ và tạo Job `crawl` cho các truyện có chương mới.

### Khôi phục sau sự cố (Persistence)
Khi khởi động lại Server/CLI:
*   Các Job đang `pending` hoặc `waiting` sẽ được đưa lại vào hàng đợi.
*   Các Job đang `running` bị ngắt quãng sẽ được đánh dấu là `failed` và hủy các Job phụ thuộc của chúng để đảm bảo an toàn dữ liệu.

---
**Lưu ý:** Mọi thay đổi và tiến độ đều được ghi lại trong `vvr_library.db` và có thể theo dõi qua Web UI.
