# Valvrare Team Web Novel Scraper

[![PyPI version](https://badge.fury.io/py/vvr-scraper.svg)](https://badge.fury.io/py/vvr-scraper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Mô tả dự án
**Valvrare Team Web Novel Scraper** là một công cụ mạnh mẽ được tối ưu hóa để tải web novel từ [Valvrare Team](https://valvrareteam.net). Công cụ hỗ trợ xuất bản ra nhiều định dạng như **EPUB, PDF, HTML, Markdown, và TXT** với hiệu suất vượt trội nhờ kiến trúc bất đồng bộ (Asynchronous) và giao diện Web hiện đại.

## Tính năng nổi bật
- **Giao diện Web Dashboard (`vvrt web`):** Trải nghiệm hiện đại với bảng điều khiển trực quan, cho phép tìm kiếm và quản lý tải xuống ngay trên trình duyệt.
- **Hiệu suất vượt trội:** Tải nội dung chương và hình ảnh minh họa song song (Bulk Download), giảm 80% thời gian chờ.
- **Giao diện CLI chuyên nghiệp:** Tích hợp `Rich` mang lại giao diện bảng biểu và thanh tiến trình trực quan ngay tại terminal.
- **Tìm kiếm thông minh:** Live Search với gợi ý thời gian thực cả trên Web và CLI.
- **Chọn thư mục bản địa:** Hỗ trợ mở hộp thoại chọn thư mục (File Explorer) trực tiếp từ giao diện Web để chọn nơi lưu truyện.
- **Vượt rào cản nâng cao:** Hỗ trợ lấy session thủ công (Dynamic Session Capture) để vượt qua Cloudflare hoặc nội dung yêu cầu đăng nhập.
- **Metadata chuyên sâu:** Tự động nhúng thể loại, tác giả, mô tả và ảnh bìa vào file EPUB.
- **Logging thời gian thực:** Theo dõi quá trình tải xuống qua WebSockets trên Web hoặc `Loguru` trên CLI.

## Cài đặt

Cách đơn giản nhất là cài đặt trực tiếp từ **PyPI**:

```bash
pip install vvr-scraper
```

Sau khi cài đặt, bạn cần cài đặt trình duyệt cho Playwright:
```bash
playwright install chromium-headless-shell
```

**Yêu cầu:** Python 3.8 trở lên.

**Khả năng tương thích:**
- **Linux:** Đã test hoạt động tốt (KDE/openSUSE).
- **Windows:** Chưa test trực tiếp (nhưng có khả năng hoạt động tốt).
- **macOS:** Chưa test trực tiếp (nhưng sẽ hoạt động tốt vì Playwright hỗ trợ chính thức).
- **Termux (Android):** Không hoạt động (do Playwright không hỗ trợ).
- **iOS:** Không hoạt động (giống Android, do giới hạn môi trường không thể chạy Playwright).

## Cách sử dụng

### 1. Chế độ Web (Mới & Khuyên dùng)
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

## Xử lý Cloudflare và Đăng nhập

Dự án hỗ trợ chế độ **Session Capture**:

1. Chạy lệnh với cờ `--login`.
2. Một trình duyệt thực sẽ mở ra, bạn thực hiện đăng nhập hoặc giải Cloudflare.
3. Khi thấy nội dung truyện hiện ra, quay lại terminal và nhấn **Enter**.
4. Session sẽ được lưu vào `.vvr_session.json` và tự động sử dụng cho cả Web và CLI.

## Lưu ý
- **Font chữ:** Font hỗ trợ tiếng Việt (DejaVuSans, NotoSerif) sẽ được tự động tải xuống khi xuất file PDF.
- **Folder Picker:** Trên Linux, tính năng "Browse" thư mục yêu cầu `zenity` (mặc định trên GNOME) hoặc `kdialog` (mặc định trên KDE).

## Giấy phép
Dự án được phát hành dưới [Giấy phép MIT](LICENSE).

## Liên hệ
- **Email:** notthanhtung@gmail.com
- **Issue:** [GitHub repository issues](https://github.com/tungvn125/Valvrareteam.net-crawler/issues)
