# Design Spec: VVR-Cinema Video Renderer

## Overview
Module `VideoRenderer` cho phép chuyển đổi một chương truyện Cinematic (đã có manifest và tài nguyên) thành tệp video MP4 chất lượng cao. Nó sử dụng Playwright để render giao diện web từng frame và FFmpeg để đóng gói thành video.

## Architecture

### 1. Frontend Modifications (cinema.js & cinema.css)
Để hỗ trợ render chính xác từng frame, player cần chuyển từ mô hình "thời gian thực/sự kiện" sang mô hình "thời gian tuyệt đối/thủ công".

- **`cinema.js`**:
    - Thêm `isRendering` flag.
    - Phương thức `renderFrame(timeMs)`:
        - Nhảy đến trạng thái chính xác tại `timeMs` mà không phụ thuộc vào `audio.currentTime`.
        - Tính toán Ken Burns transform thủ công dựa trên `timeMs`.
        - Tính toán hiệu ứng VFX (opacity, transform) thủ công.
        - Xử lý background transition tức thì hoặc theo tiến trình `timeMs`.
- **`cinema.css`**:
    - Thêm class `.rendering-mode` để ẩn UI controls và vô hiệu hóa CSS `@keyframes`.

### 2. Backend Module (vvr_scraper/video_renderer.py)
- **Lớp `VideoRenderer`**:
    - Quản lý vòng đời của Playwright và FFmpeg.
    - Điều phối quá trình chụp ảnh màn hình và đẩy vào pipe.
    - Cấu hình FFmpeg tối ưu cho chất lượng (libx264, crf 18).

## Data Flow
1. `VideoRenderer` khởi tạo Playwright Browser.
2. Load `cinema.html` với tham số `path` của novel.
3. Chờ `window.player.manifest` sẵn sàng.
4. Gọi `window.player.prepareForRendering()`.
5. Vòng lặp:
   - `window.player.renderFrame(t)`
   - `page.screenshot()` -> `ffmpeg.stdin`
6. FFmpeg hoàn tất encode và lưu tệp.

## Error Handling
- Kiểm tra sự tồn tại của `ffmpeg` trong hệ thống.
- Xử lý timeout khi load manifest.
- Đảm bảo đóng Playwright và FFmpeg pipe ngay cả khi có lỗi xảy ra.

## Testing Strategy
- Unit test cho logic tính toán Ken Burns trong JS.
- Integration test chạy renderer với một manifest mẫu và kiểm tra tệp đầu ra tồn tại.
