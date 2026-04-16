# 🌌 Gemini CLI Context: Valvrare Team Web Novel Scraper (VVR-Scraper)

Hệ thống tự động hóa khai thác và chuyển đổi nội dung từ Valvrare Team sang các định dạng đa phương tiện cao cấp (Ebook, Audiobook, Cinematic Video).

## 🚀 Tổng quan dự án (Project Overview)

- **Mục tiêu**: Tự động hóa việc tải truyện, quản lý thư viện và xuất bản nội dung số từ Valvrare Team.
- **Công nghệ lõi**:
    - **Ngôn ngữ**: Python 3.12+ (Sử dụng `uv` để quản lý gói).
    - **Scraping**: Kết hợp `httpx` (SSR Proxy) và `playwright` (Headless Browser).
    - **Xử lý AI & Multimedia**: `openai` (Director/Scripting), `elevenlabs` (TTS), `freesound` (BGM/SFX), `pydub` (Audio), `ffmpeg` (Encoding).
    - **Giao diện**: CLI (`rich`, `prompt-toolkit`) và Web UI (`fastapi`, `uvicorn`).
    - **Cơ sở dữ liệu**: SQLite (`aiosqlite`) để quản lý thư viện và hàng đợi tác vụ.
- **Kiến trúc**:
    - `vvr_scraper/scraper_core.py`: Lõi trích xuất dữ liệu (Story/Chapter).
    - `vvr_scraper/exporter.py`: Xử lý xuất định dạng (EPUB, PDF, HTML, MD, TXT, MP3, MP4).
    - `vvr_scraper/audio_drama.py`: Logic AI Director điều phối Audio Drama.
    - `vvr_scraper/video_renderer.py`: Kết xuất Cinematic Video qua Playwright.
    - `vvr_scraper/web/`: Hệ thống Web API, OPDS Server và Job Orchestrator.

## 🛠 Lệnh vận hành quan trọng (Key Commands)

### Thiết lập môi trường
```bash
# Cài đặt phụ thuộc (Sử dụng uv)
uv pip install -e ".[dev]"

# Cài đặt trình duyệt Playwright (Bắt buộc cho Video/Reliable Scraping)
playwright install chromium
```

### Chạy ứng dụng (CLI)
```bash
# Lệnh chính
vvrt --help

# Xem sơ đồ chương truyện
vvrt tree <story-url-or-slug>

# Tải và xuất EPUB
vvrt <slug> -f EPUB

# Render Cinematic Video
vvrt <slug> -f MP4
```

### Web UI & OPDS
```bash
# Khởi chạy server Web
vvrt web --port 8000
```

### Kiểm thử & Chất lượng mã
```bash
# Chạy toàn bộ test
pytest

# Kiểm tra linting (Ruff)
ruff check .
```

## 📝 Quy ước phát triển (Development Conventions)

- **Ngôn ngữ lập trình**: Ưu tiên Python hiện đại (Type hints, Async/Await).
- **Xử lý bất đồng bộ (Async)**: Hầu hết các module lõi (`scraper_core`, `db`, `web`) đều sử dụng `asyncio`.
- **Ghi nhật ký (Logging)**: Sử dụng `loguru` để theo dõi tiến trình và gỡ lỗi.
- **Quản lý cấu hình**: Biến môi trường được định nghĩa trong `.env` (API Keys cho OpenAI, ElevenLabs, Freesound).
- **Cơ sở dữ liệu**: Sử dụng SQLite (`vvr_library.db` và `test_jobs.db`). Không di chuyển thư mục truyện thủ công để tránh làm hỏng liên kết trong DB.
- **Kiểm thử**: Sử dụng `pytest` với `pytest-asyncio` và `hypothesis` cho kiểm thử thuộc tính.

## 📂 Cấu trúc thư mục chính

- `vvr_scraper/`: Mã nguồn chính của gói python.
    - `web/`: Module FastAPI và Routes.
    - `prompts/`: Chứa các prompt Markdown cho AI Director.
    - `static/`: Tài nguyên frontend cho Cinema Player và Web UI.
- `tests/`: Hệ thống kiểm thử toàn diện (Unit, Integration, E2E).
- `novels/`: Thư mục mặc định chứa kết quả tải về (thường được bỏ qua trong git).
- `docs/superpowers/plans/`: Chứa các bản kế hoạch chi tiết cho các tính năng phức tạp.

## ⚠️ Lưu ý bảo mật
- KHÔNG bao giờ commit file `.env` chứa API Keys.
- Sử dụng `.env.example` làm mẫu cho các thiết lập mới.

---
*File này được tạo tự động bởi Gemini CLI để cung cấp ngữ cảnh cho các phiên làm việc tiếp theo.*
