# Valvrare Team Web Novel Scraper (VVR-Scraper)

Hệ thống tự động hóa khai thác và chuyển đổi nội dung từ Valvrare Team sang các định dạng đa phương tiện (Ebook, Audiobook, Cinematic Video).

## 🚀 Tính năng chính

- **Hybrid Scraping**: Kết hợp HTTPX (Fast mode via SSR Proxy) và Playwright (Reliable mode) để vượt rào cản kỹ thuật và trích xuất nội dung chính xác.
- **Đa định dạng xuất bản**:
    - **Ebooks**: EPUB (với cấu trúc Volume/Chapter), PDF, HTML, Markdown, TXT.
    - **Audiobook**: Chuyển đổi văn bản thành giọng nói (TTS) chất lượng cao sử dụng ElevenLabs.
    - **Audio Drama (v2.5)**: Tự động phân tích kịch bản bằng OpenAI, gán giọng nhân vật, chèn nhạc nền (BGM) và hiệu ứng âm thanh (SFX) từ Freesound.
    - **Cinematic Video (MP4)**: Kết xuất video với hiệu ứng chuyển cảnh, Ken Burns, VFX và đồng bộ phụ đề Karaoke chính xác từng mili giây.
- **Cinema Player**: Trình phát web tích hợp cho phép trải nghiệm nội dung Cinematic ngay trên trình duyệt.
- **Personal OPDS Server**: Cung cấp feed sách chuẩn OPDS 1.1 để kết nối trực tiếp với các ứng dụng đọc sách (Moon+ Reader, KyBook, v.v.).
- **Job Orchestrator**: Hệ thống hàng đợi (Queue) và Task Runner mạnh mẽ, hỗ trợ tự động hóa việc theo dõi và tải chương mới.

## 🛠 Yêu cầu hệ thống

- **Python**: 3.10+
- **Công cụ bổ trợ**: 
    - [FFmpeg](https://ffmpeg.org/): Bắt buộc để xử lý âm thanh và kết xuất video.
    - [Playwright](https://playwright.dev/): Cần thiết cho chế độ Reliable Scraping và Video Rendering.
- **API Keys**:
    - `OPENAI_API_KEY`: Dùng cho AI Director (phân tích kịch bản và sinh ảnh).
    - `ELEVENLABS_API_KEY`: Dùng cho giọng đọc AI chất lượng cao.
    - `FREESOUND_API_KEY`: Dùng để tìm kiếm nhạc nền và hiệu ứng.

## 📦 Cài đặt

Cách đơn giản nhất là cài đặt trực tiếp từ PyPI:

```bash
# Sử dụng uv (Khuyến nghị)
uv pip install vvr-scraper

# Hoặc sử dụng pip truyền thống
pip install vvr-scraper

# Cài đặt Playwright browsers (Bắt buộc cho chế độ Reliable mode và Video Render)
playwright install chromium
```

### Cài đặt từ mã nguồn (Dành cho nhà phát triển)

Nếu bạn muốn đóng góp hoặc sử dụng phiên bản mới nhất từ Git:

```bash
git clone https://github.com/your-repo/valvrareteam-net-crawler.git
cd valvrareteam-net-crawler
uv pip install -e .
playwright install chromium
```

## ⚙️ Cấu hình

Tạo file `.env` hoặc thiết lập biến môi trường:

```env
# API Keys
OPENAI_API_KEY=your_openai_key
ELEVENLABS_API_KEY=your_elevenlabs_key
FREESOUND_CLIENT_ID=your_id
FREESOUND_CLIENT_SECRET=your_secret

# Tùy chọn (Optional)
VVR_SSR_URL=val-ssr-2kzit.ondigitalocean.app
VVR_OPDS_USER=admin
VVR_OPDS_PASS=password
```

## 📖 Hướng dẫn sử dụng

### CLI (Command Line Interface)

Sử dụng lệnh `vvrt` để thực hiện các tác vụ:

```bash
# Lấy sơ đồ cây của một truyện
vvrt tree https://valvrareteam.net/truyen/ten-truyen

# Tải và xuất định dạng EPUB
vvrt ten-truyen-slug -f EPUB

# Tạo Audio Drama cho một chương
vvrt ten-truyen-slug -f AD-MP3

# Render video Cinematic
vvrt ten-truyen-slug -f MP4
```

### Web UI & OPDS

Khởi chạy máy chủ web:

```bash
vvrt web --port 8000
```

- **Giao diện quản lý**: `http://localhost:8000`
- **OPDS Feed**: `http://localhost:8000/opds/v1/root`
- **Cinema Player**: Truy cập qua API hoặc giao diện web.

### Job Runner

Chạy các tác vụ hàng loạt qua manifest JSON:

```bash
vvrt run manifest.json
```

## 🏗 Kiến trúc dự án

- `vvr_scraper/scraper_core.py`: Lõi xử lý trích xuất dữ liệu.
- `vvr_scraper/exporter.py`: Chuyển đổi dữ liệu sang các định dạng đích.
- `vvr_scraper/audio_drama.py`: Logic AI Director và quản lý âm thanh.
- `vvr_scraper/video_renderer.py`: Kết xuất MP4 sử dụng Playwright và FFmpeg.
- `vvr_scraper/db.py`: Quản lý SQLite với cơ chế an toàn async.
- `vvr_scraper/web.py`: API Server (FastAPI) và OPDS.

## 🛡 Bảo mật và Quy định

Dự án này được tạo ra cho mục đích học tập và lưu trữ cá nhân. Vui lòng tôn trọng bản quyền của dịch giả và tác giả. Không sử dụng công cụ này để thực hiện các hành vi gây hại đến máy chủ của Valvrare Team.

---
© 2024 VVR-Scraper Team.
