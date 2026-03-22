# Valvrare Team Web Novel Scraper

[![PyPI version](https://badge.fury.io/py/vvr-scraper.svg)](https://badge.fury.io/py/vvr-scraper)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Mô tả dự án
**Valvrare Team Web Novel Scraper** là một công cụ dòng lệnh (CLI) mạnh mẽ, được tối ưu hóa để tải web novel từ [Valvrare Team](https://valvrareteam.net). Công cụ hỗ trợ xuất bản ra nhiều định dạng như **EPUB, PDF, HTML, Markdown, và TXT** với hiệu suất cao nhờ kiến trúc bất đồng bộ (Asynchronous).

## Tính năng nổi bật
- **Hiệu suất vượt trội:** Tải nội dung chương và hình ảnh minh họa song song (Bulk Download), giảm 80% thời gian chờ so với các bản cũ.
- **Giao diện hiện đại:** Tích hợp `Rich` mang lại giao diện bảng biểu đẹp mắt và thanh tiến trình (progress bars) trực quan.
- **Tìm kiếm thông minh:** Tìm kiếm truyện trực tiếp với gợi ý thời gian thực (Live Search) và tự động xử lý slug chính xác.
- **Làm sạch dữ liệu tự động:** Tự động loại bỏ các hậu tố trạng thái (`+Đang tiến hành`, `+Hoàn thành`...) và chuẩn hóa tên tệp/thư mục.
- **Vượt rào cản nâng cao:** Hỗ trợ lấy session thủ công (Dynamic Session Capture) để vượt qua Cloudflare hoặc truy cập nội dung yêu cầu đăng nhập.
- **Metadata chuyên sâu:** Tự động nhúng thể loại, tác giả, mô tả và ảnh bìa vào file EPUB để quản lý dễ dàng trên Calibre.
- **Logging chuyên nghiệp:** Hệ thống log có cấu trúc với `Loguru`, hỗ trợ chế độ `--verbose` để debug chi tiết.

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

## Cách sử dụng

Sau khi cài đặt qua pip, bạn có thể sử dụng lệnh `vvrt` từ bất kỳ đâu:

### 1. Chế độ tương tác (Khuyên dùng)
Chỉ cần gõ lệnh và làm theo hướng dẫn trên màn hình:
```bash
vvrt
```

### 2. Chế độ dòng lệnh (CLI)
Dành cho người dùng nâng cao hoặc viết script tự động:
```bash
# Ví dụ: Tải truyện với định dạng EPUB, gộp tất cả chương, dùng 10 luồng tải
vvrt "ten-truyen-slug" -f EPUB -g tatca -t 10 --khong-minh-hoa
```

Các tham số chính:
- `-f, --format`: Định dạng đầu ra (PDF, EPUB, HTML, MD, TXT).
- `-g, --gop`: Cách gộp file (`rieng`, `volume`, `tatca`).
- `-t, --tasks`: Số lượng tác vụ song song (mặc định là 5).
- `--login`: Mở trình duyệt để đăng nhập thủ công/vượt Cloudflare.
- `--verbose`: Hiển thị log chi tiết để theo dõi quá trình.

## Xử lý Cloudflare và Đăng nhập

Dự án hỗ trợ chế độ **Session Capture** để vượt qua các biện pháp bảo vệ của website:

1. Chạy lệnh với cờ `--login`.
2. Một trình duyệt thực sẽ mở ra, bạn thực hiện đăng nhập hoặc giải Cloudflare.
3. Khi thấy nội dung truyện đã hiện ra, quay lại terminal và nhấn **Enter**.
4. Session sẽ được lưu vào `.vvr_session.json` và tự động sử dụng cho các lần sau.

## Lưu ý
- **Bản quyền:** Hãy tôn trọng quyền tác giả và chỉ sử dụng nội dung tải về cho mục đích lưu trữ cá nhân.
- **Lỗi tải:** Các chương gặp lỗi sẽ được ghi nhận vào file `cac_chuong_da_bo_qua.txt` trong thư mục truyện.
- **Font chữ:** Font hỗ trợ tiếng Việt (DejaVuSans, NotoSerif) sẽ được tự động tải xuống nếu máy bạn chưa có khi xuất file PDF.

## Giấy phép
Dự án được phát hành dưới [Giấy phép MIT](LICENSE).

## Liên hệ
- **Email:** notthanhtung@gmail.com
- **Issue:** Mở issue trên [GitHub repository](https://github.com/tungvn125/Valvrareteam.net-crawler/issues) nếu bạn gặp lỗi hoặc có ý tưởng mới.
