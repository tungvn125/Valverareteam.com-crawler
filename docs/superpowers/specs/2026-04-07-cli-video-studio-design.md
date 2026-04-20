# Spec: CLI Autonomous Video Studio (VVR-Cinema Renderer)

## 1. Overview
Biến trình phát Cinema (Web-based) thành một công cụ render video MP4 tự động thông qua CLI. Cho phép người dùng tạo ra các video cinematic từ web novel mà không cần thao tác trên giao diện web.

## 2. Architecture

### 2.1. CLI & Interactive Interface
- **Command Line Arguments:** `vvrt <novel-slug> [chapter-range] --render`
    - `--format`: `landscape` (16:9) hoặc `portrait` (9:16, tối ưu TikTok/Shorts).
    - `--fps`: Số khung hình trên giây (mặc định 30).
    - `--output`: Đường dẫn lưu file video (mặc định `./exports/`).
- **Interactive Menu (sử dụng `simple_term_menu`):**
    Khi chạy `vvrt` ở chế độ tương tác (không truyền đủ tham số format trên CLI):
    1. Trong menu chọn định dạng file ("Chọn định dạng file"), bổ sung tùy chọn **"MP4 (Cinematic Video)"**.
    2. Nếu người dùng chọn MP4, hiển thị thêm các menu cấu hình kỹ thuật liên tiếp:
       - **Chọn tỷ lệ khung hình:**
         - "Landscape (16:9 - YouTube/PC)"
         - "Portrait (9:16 - TikTok/Shorts/Reels)"
       - **Chọn FPS (Tốc độ khung hình):**
         - "30 FPS (Mượt mà, render nhanh)"
         - "60 FPS (Rất mượt, render lâu hơn)"
    3. Tùy chọn sẽ được lưu vào `export_config` để truyền xuống engine render.

### 2.2. Components
1. **Content Bundle Provider**: 
   - Sử dụng `exporter.py` để tạo ra `manifest.json`, audio files, và background images.
   - Lưu vào một thư mục tạm (`temp/`).
2. **Headless Web Server**:
   - Một `FastAPI` server mini (hoặc `http.server`) chạy tạm thời để phục vụ các tài nguyên từ thư mục tạm.
3. **Playwright Capture Engine**:
   - Mở trình duyệt Chromium ẩn danh.
   - Tải trang `cinema.html`.
   - Điều khiển playback qua `window.cinemaPlayer`.
   - Chụp ảnh màn hình (screenshot) theo chu kỳ FPS.
4. **FFmpeg Muxer**:
   - Nhận luồng ảnh (image stream) qua stdin.
   - Nhận file audio đã mix từ `MixingEngine`.
   - Mã hóa thành video H.264 (MP4).

## 3. Implementation Plan

### Phase 1: Preparation
- [ ] Cài đặt các thư viện bổ sung (nếu cần): `ffmpeg-python`.
- [ ] Tạo template `cinema_headless.html` tối ưu cho việc chụp ảnh (loại bỏ thanh điều khiển, hiển thị toàn màn hình).

### Phase 2: Frame Capture
- [ ] Viết module `video_renderer.py`.
- [ ] Logic đồng bộ hóa: Đảm bảo Playwright chụp ảnh khớp với mốc thời gian của Audio.
- [ ] Trick: Sử dụng `requestAnimationFrame` ảo hoặc điều khiển tốc độ audio cực chậm để đảm bảo không bị drop frame khi render.

### Phase 3: CLI Integration
- [ ] Thêm flag `--render` vào `cli.py`.
- [ ] Hiển thị thanh tiến trình (Progress Bar) cho quá trình render.

## 4. Testing Strategy
- Kiểm tra tính đồng bộ (lipsync, vfx timing).
- Thử nghiệm render với nhiều kích thước màn hình khác nhau.
- Benchmark thời gian render so với thời gian thực.
