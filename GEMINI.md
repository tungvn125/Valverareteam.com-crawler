# Valvrare Team Web Novel Scraper (VVR-Scraper)

Hệ thống tự động hóa khai thác và chuyển đổi nội dung từ Valvrare Team sang các định dạng đa phương tiện nâng cao (Ebook, Audiobook, Cinematic Video).

## 🚀 Project Overview

VVR-Scraper là một công cụ mạnh mẽ được thiết kế để tải truyện từ `valvrareteam.net` và chuyển đổi chúng thành nhiều định dạng khác nhau. Dự án không chỉ dừng lại ở việc tạo Ebook mà còn tích hợp AI để tạo ra các sản phẩm truyền thông đa phương tiện như Audio Drama và Video Cinematic.

### Core Features
- **Hybrid Scraping**: Sử dụng `httpx` (Fast mode qua SSR Proxy) và `Playwright` (Reliable mode) để trích xuất nội dung chính xác.
- **Multi-format Export**: Hỗ trợ EPUB, PDF, HTML, Markdown, TXT và MP3 (Audiobook).
- **AI Audio Drama (v2.5)**: 
    - Phân tích kịch bản bằng OpenAI.
    - Gán giọng nhân vật và tổng hợp giọng nói qua ElevenLabs.
    - Chèn nhạc nền (BGM) và hiệu ứng (SFX) từ Freesound.
- **Cinematic Video (MP4)**: Kết xuất video với hiệu ứng chuyển cảnh, VFX và đồng bộ phụ đề Karaoke.
- **Web UI & OPDS Server**: Cung cấp giao diện quản lý trên trình duyệt và feed OPDS 1.1 cho các ứng dụng đọc sách (Moon+ Reader, KyBook).
- **Job Orchestrator (v2.5)**: 
    - Hệ thống `JobWorker` và `JobRunner` xử lý các tác vụ nặng (crawl, render video) bất đồng bộ.
    - Hỗ trợ chạy các tác vụ hàng loạt thông qua file manifest JSON (`vvrt run manifest.json`).
    - Lưu trữ lịch sử job và log lỗi chi tiết trong SQLite.
- **Library Management**: Quản lý thư viện truyện bằng SQLite (async), tự động kiểm tra và cập nhật chương mới.

## 🛠 Tech Stack

- **Ngôn ngữ**: Python 3.10+
- **Scraping**: `httpx`, `Playwright`, `BeautifulSoup4`, `lxml`.
- **Media**: `pydub`, `FFmpeg` (yêu cầu cài đặt hệ thống), `Pillow`, `ReportLab`.
- **AI Services**: `OpenAI API`, `ElevenLabs API`, `Freesound API`.
- **Web Framework**: `FastAPI`, `Uvicorn`, `WebSockets`.
- **Database**: `aiosqlite` (SQLite async).
- **CLI/UI**: `rich`, `prompt-toolkit`, `simple-term-menu`, `alive-progress`.

## 🏗 Project Structure

- `vvr_scraper/`: Thư mục mã nguồn chính.
    - `cli.py`: Điểm đầu vào CLI (`vvrt`).
    - `scraper_core.py`: Logic trích xuất dữ liệu (Hybrid Scraper).
    - `exporter.py`: Xử lý tạo file cho tất cả các định dạng (EPUB, PDF, MP3, ...).
    - `audio_drama.py`: Logic AI Director, phân tích kịch bản và quản lý âm thanh.
    - `video_renderer.py`: Kết xuất video MP4 bằng Playwright và FFmpeg.
    - `db.py`: Quản lý cơ sở dữ liệu SQLite và Job Queue.
    - `web.py`: API Server và giao diện quản lý Web.
    - `opds.py`: Generator feed OPDS.
    - `bgm_manager.py` & `freesound_manager.py`: Quản lý nhạc nền và hiệu ứng.
- `tests/`: Hệ thống kiểm thử toàn diện với `pytest`.
- `static/`: Tài liệu tĩnh cho Web UI (CSS, JS).
- `prompts/`: Chứa các system prompt cho AI Director.

## 📖 Building and Running

### Setup
1. **Cài đặt dependencies**:
   ```bash
   uv pip install -e .
   # Hoặc
   pip install -e .
   ```
2. **Cài đặt Playwright Browsers**:
   ```bash
   playwright install chromium
   ```
3. **Cấu hình biến môi trường** (`.env`):
   ```env
   OPENAI_API_KEY=...
   ELEVENLABS_API_KEY=...
   FREESOUND_CLIENT_ID=...
   FREESOUND_CLIENT_SECRET=...
   VVR_SSR_URL=...
   ```

### Key Commands
- **CLI Usage**:
  ```bash
  vvrt <slug_truyen> -f EPUB PDF       # Tải và xuất file
  vvrt tree <url_truyen>              # Xem sơ đồ chương
  vvrt run manifest.json              # Chạy tác vụ hàng loạt
  ```
- **Web UI & OPDS**:
  ```bash
  vvrt web --port 8000                # Khởi chạy server
  ```
- **Testing**:
  ```bash
  pytest                              # Chạy toàn bộ test suite
  ```

## 📝 Development Conventions

- **Async First**: Hầu hết các tác vụ I/O (Scraping, DB, API) đều sử dụng `asyncio`.
- **Logging**: Sử dụng `loguru` để quản lý log. Logs cũng được truyền qua WebSocket lên Web UI.
- **Database Migrations**: `db.py` chứa logic tự động cập nhật schema (Robust upgrade logic).
- **Testing Style**: Sử dụng `pytest` và `pytest-asyncio`. Các test case được chia nhỏ theo module (ví dụ: `test_scraper.py`, `test_db_audio.py`).
- **Lazy Loading**: Các thư viện nặng (như ElevenLabs, numpy) được load bên trong các hàm cụ thể để tăng tốc độ khởi động CLI/Web UI.
- **Hybrid Scraper**: Luôn ưu tiên Fast Mode (HTTPX) trước khi fallback sang Reliable Mode (Playwright) để tối ưu hiệu suất.
