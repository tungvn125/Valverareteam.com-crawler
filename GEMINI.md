# Valvrare Team Web Novel Scraper - Technical Documentation

## Kiến trúc hệ thống
Dự án được xây dựng trên mô hình **Asynchronous Event-Driven**, chia thành các module chức năng chuyên biệt:

- **`vvr_scraper/scraper_core.py`**: Trái tim của hệ thống scraping. 
    - Sử dụng mô hình Hybrid: HTTPX qua SSR Proxy (Fast) và Playwright (Reliable).
- **`vvr_scraper/exporter.py`**: Module xuất bản tập trung.
    - Tích hợp **Pipeline VVR-Cinema**: Orchestrator kết nối LLM Director, TTS Sync và Visual Generator.
    - Xử lý tính toán **Global Timestamps**: Chuyển đổi mốc thời gian TTS tương đối sang tuyệt đối (ms) để đồng bộ toàn cục.
- **`vvr_scraper/audio_drama.py`**: 
    - `OpenAIParser`: Trích xuất kịch bản kèm `visual_prompt` (English), `vfx_triggers` và `transitions`.
    - `VoiceManager`: Sử dụng ElevenLabs `stream-with-timestamps` để lấy dữ liệu đồng bộ cấp độ từ (word-level alignment).
- **`vvr_scraper/image_gen.py` (New)**: Module sinh ảnh bối cảnh AI.
    - Tích hợp DALL-E 3 (OpenAI) với cơ chế **SHA-256 Deduplication** để tránh sinh trùng ảnh.
    - Tối ưu hóa **WebP Conversion** (Pillow) để tăng tốc độ tải và tiết kiệm dung lượng.
- **`vvr_scraper/web.py`**: FastAPI server.
    - Cung cấp API phục vụ tài nguyên tĩnh (`/novels`) và Manifest API cho trình phát Cinema.
    - **Personal OPDS Server (New):** Tích hợp chuẩn OPDS 1.1 và OpenSearch cho phép các ứng dụng đọc sách kết nối trực tiếp.
- **`vvr_scraper/opds.py` (New)**: Module sinh Atom XML Feed.
    - Xử lý logic phân trang (Pagination), tìm kiếm (Search) và ánh xạ dữ liệu novel sang chuẩn OPDS metadata.
    - Hỗ trợ đa định dạng (EPUB/PDF) và proxy ảnh bìa thông minh.
- **Giao diện Cinema Player (Frontend)**:
    - Xây dựng bằng Vanilla JS & CSS3 Animations.
    - Sử dụng `requestAnimationFrame` để đồng bộ hóa hình ảnh/VFX với âm thanh ở độ chính xác mili giây.
    - Hiệu ứng **Ken Burns** đa biến thể giúp ảnh tĩnh trở nên sống động.

## Quyết định thiết kế then chốt
1. **Cinematic Bundle:** Mọi tài nguyên (audio, backgrounds, manifest) được tạo sẵn và lưu trữ local. Điều này đảm bảo trải nghiệm xem mượt mà 60fps và không phụ thuộc internet/API khi thưởng thức.
2. **Absolute Timing:** Mốc thời gian Karaoke được tính toán ngay tại Backend (bao gồm cả padding, gap và crossfade). Frontend chỉ việc "diễn" theo script, giảm tải logic tính toán cho trình duyệt.
3. **Hardware Acceleration:** Toàn bộ VFX (Shake, Rain, Fog) và Ken Burns sử dụng thuộc tính CSS `transform` và `opacity` để tận dụng GPU.

## Quy trình Phát triển (Conventions)
- **Async First:** Sử dụng `httpx.AsyncClient` dùng chung (shared client) và giới hạn luồng qua `asyncio.Semaphore`.
- **Manifest-Driven:** File `manifest.json` là "Source of Truth" duy nhất cho mỗi chương truyện Cinematic.

## Các vấn đề cần cải thiện (Backlog)
- [ ] **Character Sprites:** Hỗ trợ hiển thị Portrait nhân vật kèm hiệu ứng chuyển động môi (lip-sync) cơ bản.
- [ ] **Interactive Choices:** Cho phép người dùng chọn nhánh rẽ câu chuyện qua LLM sinh nội dung thời gian thực.
- [x] **TTS Segment Caching:** Đã tích hợp qua cơ chế Script Result.
- [x] **Memory Optimization:** Sử dụng WebP và shared HTTP client.
