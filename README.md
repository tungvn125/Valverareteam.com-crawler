# Valvrare Team Web Novel Scraper (v1.8.0)

[![PyPI version](https://badge.fury.io/py/vvr-scraper.svg)](https://badge.fury.io/py/vvr-scraper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Mô tả dự án
**Valvrare Team Web Novel Scraper** là một công cụ hiệu suất cao, đa nền tảng (CLI & Web) dùng để tải và chuyển đổi web novel từ [Valvrare Team](https://valvrareteam.net) thành các định dạng sách điện tử và trải nghiệm điện ảnh sống động.

## Tính năng nổi bật
- **Giao diện Kép:** Web Dashboard hiện đại và CLI tương tác chuyên nghiệp.
- **VVR-Cinema:** Biến truyện chữ thành trải nghiệm "Visual Novel" tự động:
    - **Karaoke Highlighting:** Chữ chạy theo nhịp đọc của AI (Word-level sync).
    - **AI Backgrounds:** Tự động sinh hình nền bối cảnh bằng DALL-E 3 phù hợp với nội dung.
    - **Dynamic VFX:** Hiệu ứng rung màn hình, mưa rơi, sương mù, chớp sáng theo tâm trạng nhân vật.
    - **Immersive Player:** Trình phát toàn màn hình với hiệu ứng Ken Burns chuyên nghiệp.
- **AudioBook (AI Powered):**
    - **AD-MP3 (Audio Drama v3.0):** Phân vai nhân vật, lồng nhạc nền (Freesound), và trích xuất kịch bản thông minh.
- **Thư viện thông minh:** Tự động kiểm tra chương mới và quản lý tập trung.
- **Xuất đa định dạng:** EPUB, PDF, HTML, Markdown, TXT, MP3.

## Cài đặt

```bash
pip install vvr-scraper
# Cài đặt trình duyệt cho Playwright:
playwright install chromium-headless-shell
```

**Yêu cầu:** Python 3.10 trở lên.

## Cách sử dụng

### 1. Chế độ Web (Khuyến nghị)
```bash
vvrt web
```
Giao diện sẽ tự động mở tại `http://127.0.0.1:8000`. Sau khi tải xong bản **AD-MP3**, nhấn nút **"Xem Cinema 🎬"** để thưởng thức.

### 2. Kết nối OPDS (Cho ứng dụng đọc sách di động) (auto start with webui)
Bạn có thể kết nối các ứng dụng như **Moon+ Reader** hoặc **KyBook** vào thư viện cá nhân của mình:
- **Địa chỉ:** `http://<your-ip>:8000/opds/v1/root`
- **Đăng nhập:** Mặc định là `admin` / `password`.
- **Cấu hình bảo mật:** Đặt `VVR_OPDS_USER` và `VVR_OPDS_PASS` trong biến môi trường để thay đổi thông tin đăng nhập.

## Cấu hình VVR-Cinema (Quan trọng)

Để sử dụng đầy đủ tính năng Cinema, bạn cần thiết lập:

```bash
# ElevenLabs (Giọng nói & Đồng bộ)
export ELEVENLABS_API_KEY="your-key"

# OpenAI (Soạn kịch bản & Sinh ảnh bối cảnh)
export OPENAI_API_KEY="your-key" # Dùng cho DALL-E 3
export VVR_API_KEY="your-key"    # Dùng cho LLM (có thể trùng OPENAI_API_KEY)
```

### Tùy chỉnh trải nghiệm
Trong phần **Settings** trên Web Dashboard, bạn có thể:
- Bật/Tắt **AI Backgrounds** (Để tiết kiệm chi phí API).
- Điều chỉnh **VFX Intensity** (Độ mạnh của hiệu ứng rung và thời tiết).

### Thư viện Nhạc nền (Local BGM)
Tạo thư mục `bgm/` với các thư mục con: `action`, `peaceful`, `mysterious`, `romantic`, `sad`, `suspense`. Hệ thống sẽ ưu tiên lấy nhạc từ đây trước khi tìm trên Freesound.

## Lưu ý kỹ thuật
- **Checkpoint:** Tiến trình được lưu tại `.vvr_checkpoint.json` trong thư mục đầu ra. Nếu lỗi, bạn có thể tải lại để tiếp tục mà không mất dữ liệu cũ.
- **Script Caching:** Audio Drama lưu kịch bản tại `.script.json`. Bạn có thể chỉnh sửa kịch bản này trước khi hệ thống bắt đầu tổng hợp âm thanh.
- **Giới hạn:** Tự động hủy xuất file nếu tỷ lệ tải chương thất bại > 30%.
- **Folder Picker:** Trên Linux, tính năng "Browse" thư mục yêu cầu `zenity`, `kdialog` hoặc `python3-tk`.

## Giấy phép
Dự án phát hành dưới [Giấy phép MIT](LICENSE).
