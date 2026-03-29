# Valvrare Team Web Novel Scraper

[![PyPI version](https://badge.fury.io/py/vvr-scraper.svg)](https://badge.fury.io/py/vvr-scraper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Mô tả dự án
**Valvrare Team Web Novel Scraper** là một công cụ mạnh mẽ được tối ưu hóa để tải web novel từ [Valvrare Team](https://valvrareteam.net). Công cụ hỗ trợ xuất bản ra nhiều định dạng như **EPUB, PDF, HTML, Markdown, và TXT** với hiệu suất vượt trội nhờ kiến trúc bất đồng bộ (Asynchronous) và giao diện Web hiện đại.

## Tính năng nổi bật
- **Web Dashboard & CLI:** Giao diện Web hiện đại hoặc terminal chuyên nghiệp với Rich — tùy bạn chọn.
- **Xuất đa định dạng:** EPUB (có mục lục Tập/Chương, ảnh bìa), PDF, HTML, Markdown, TXT, MP3 (AI TTS), AD-MP3 (Audio Drama đa giọng nói bằng AI).
- **Batch Import & Download Queue:** Tải hàng loạt truyện với hàng đợi đa luồng, hỗ trợ pause/resume/cancel.
- **Checkpoint & Resume:** Tự động lưu tiến trình — nếu bị gián đoạn, tiếp tục từ chương cuối đã tải.
- **Thư viện truyện:** Theo dõi lịch sử tải, kiểm tra chương mới, quét thư mục hiện có.
- **Hybrid Scraping:** Fast Mode (SSR) + Reliable Mode (Playwright), tự động dừng nếu >30% chương thất bại.
- **Session Capture:** Vượt Cloudflare và nội dung yêu cầu đăng nhập bằng phiên trình duyệt thực.

## Cài đặt

Cách đơn giản nhất là cài đặt trực tiếp từ **PyPI**:

```bash
pip install vvr-scraper
# Hoặc nếu muốn dùng tính năng AI TTS (MP3/AD-MP3):
# pip install "vvr-scraper[audio]"
```

Sau khi cài đặt, bạn cần cài đặt trình duyệt cho Playwright:
```bash
playwright install chromium-headless-shell
```

**Yêu cầu:** Python 3.10 trở lên.

**Khả năng tương thích:**
- **Linux:** Đã test hoạt động tốt (KDE/openSUSE).
- **Windows:** Chưa test trực tiếp (nhưng có khả năng hoạt động tốt).
- **macOS:** Chưa test trực tiếp (nhưng sẽ hoạt động tốt vì Playwright hỗ trợ chính thức).
- **Termux (Android):** Không hoạt động (do Playwright không hỗ trợ).
- **iOS:** Không hoạt động (giống Android, do giới hạn môi trường không thể chạy Playwright).

## Cách sử dụng

### 1. Chế độ Web (Khuyến nghị)
Khởi chạy giao diện điều khiển hiện đại trên trình duyệt:
```bash
vvrt web
```
Các tham số hỗ trợ:
- `--port`: Cổng chạy server (mặc định: 8000).
- `--host`: Host chạy server (mặc định: 127.0.0.1).
- `--no-browser`: Không tự động mở trình duyệt.
- `--workers WORKERS`: Số lượng novel tải song song (mặc định: 1).

### 2. Chế độ tương tác (CLI)
Dành cho người thích làm việc trực tiếp tại terminal:
```bash
vvrt
```

### 3. Chế độ dòng lệnh (CLI nâng cao)
```bash
# Ví dụ: Tải cùng lúc nhiều truyện với định dạng EPUB, dùng 10 luồng tải
vvrt slug-truyen-1 slug-truyen-2 -f EPUB -g tatca -t 10 --verbose
```

### 4. Batch Import (Web UI)
Trên giao diện Web Dashboard, sử dụng chức năng **Batch Import** để nhập danh sách URL hoặc slug, mỗi dòng một truyện. Tất cả sẽ được thêm vào hàng đợi và tải lần lượt.

### 5. Cấu hình Audio-Drama (AD-MP3) & Audiobook (MP3)
Tính năng `MP3` (Audiobook) và `AD-MP3` sử dụng engine TTS AI `Vieneu` chạy hoàn toàn tại local. Tính năng `AD-MP3` (v2) sử dụng thêm LLM để phân tích hội thoại và **bối cảnh (Mood)**, tự động chọn nhạc nền phù hợp và thực hiện trộn âm (Mixing) với hiệu ứng **Auto-Ducking**.

> ⚠️ **Cảnh báo phần cứng (TTS AI):** Engine `Vieneu` sử dụng các mô hình AI tiếng Việt nặng (dựa trên PyTorch). Việc tạo Audiobook và Audio Drama tiêu tốn rất nhiều tài nguyên hệ thống (RAM) và yêu cầu cấu hình máy tính từ trung bình khá trở lên.

#### Thư viện Nhạc nền (BGM)
Để sử dụng tính năng nhạc nền cho Audio Drama, bạn cần tạo thư mục `bgm` trong thư mục chạy lệnh với cấu trúc sau:
```text
bgm/
├── action/      (Nhạc chiến đấu, căng thẳng)
├── peaceful/    (Nhạc bình yên, thường nhật)
├── mysterious/  (Nhạc bí ẩn, rùng rợn)
├── romantic/    (Nhạc lãng mạn)
├── sad/         (Nhạc buồn)
└── suspense/    (Nhạc hồi hộp)
```
Hệ thống sẽ tự động chọn ngẫu nhiên một file nhạc (`.mp3`, `.wav`, `.ogg`) trong thư mục tương ứng với bối cảnh truyện.

#### Cấu hình LLM
Để cấu hình tính năng phân vai và phân tích mood của `AD-MP3`, bạn cần cung cấp API Key LLM:
```bash
export VVR_API_KEY="your-api-key"
export VVR_BASE_URL="https://api.openai.com/v1" # Sử dụng URL proxy nếu cần
export VVR_MODEL="gpt-4o-mini" # Model tùy chọn (mặc định: gpt-4o-mini)
```

## Xử lý Cloudflare và Đăng nhập

Dự án hỗ trợ chế độ **Session Capture**:

1. Chạy lệnh với cờ `--login`.
2. Một trình duyệt thực sẽ mở ra, bạn thực hiện đăng nhập hoặc giải Cloudflare.
3. Khi thấy nội dung truyện hiện ra, quay lại terminal và nhấn **Enter**.
4. Session sẽ được lưu vào `.vvr_session.json` và tự động sử dụng cho cả Web và CLI.

## Lưu ý
- **Font chữ:** Font hỗ trợ tiếng Việt (DejaVuSans, NotoSerif) sẽ được tự động tải xuống khi xuất file PDF.
- **Folder Picker:** Trên Linux, tính năng "Browse" thư mục yêu cầu `zenity` (mặc định trên GNOME) hoặc `kdialog` (mặc định trên KDE), hoặc `python3-tk`.
- **Thư viện truyện:** Dữ liệu thư viện được lưu tại `vvr_library.db` (SQLite). File này được tạo tự động khi khởi chạy Web Dashboard.

## Giấy phép
Dự án được phát hành dưới [Giấy phép MIT](LICENSE).

## Liên hệ
- **Email:** notthanhtung@gmail.com
- **Issue:** [GitHub repository issues](https://github.com/tungvn125/Valvrareteam.net-crawler/issues)
