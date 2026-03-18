# Web Novel Scraper

## Mô tả dự án
Dự án **Web Novel Scraper** là một công cụ được viết bằng Python để tải và lưu các bộ truyện từ trang web [Valvrare Team](https://valvrareteam.net) dưới dạng file PDF và/hoặc EPUB. Công cụ này sử dụng các thư viện như `playwright`, `BeautifulSoup`, `ebooklib`, và `reportlab` để thu thập nội dung (bao gồm văn bản và hình ảnh minh họa) từ các chương truyện, sau đó tạo file đầu ra theo định dạng người dùng chọn.

## Tính năng
- **Tải nội dung song song**: Hỗ trợ tải nhiều chương cùng lúc với số lượng tác vụ song song tùy chỉnh.
- **Vượt rào cản (Session Capture)**: Hỗ trợ lấy session thủ công qua trình duyệt (non-headless) để vượt qua Cloudflare hoặc truy cập các chương yêu cầu đăng nhập.
- **Định dạng đầu ra**: Lưu nội dung dưới dạng PDF, EPUB, hoặc các định dạng khác.
- **Ghi log lỗi**: Lưu danh sách các chương bị lỗi vào file `cac_chuong_da_bo_qua.txt`.
- **Tự động sắp xếp files**: Tự động tạo và sắp xếp các file chương(chapter) vào các thư mục tập(volume).

## Yêu cầu cài đặt
Để chạy dự án, bạn cần cài đặt Python 3.8+ và các thư viện sau:

-**Cách 1: Cài đặt thủ công**
```bash
pip install -r requirements.txt
```

Cài đặt trình duyệt Playwright (chromium-headless-shell):
```bash
playwright install chromium-headless-shell
```

Font hỗ trợ tiếng Việt (nếu tải PDF):
- **DejaVuSans** (mặc định): Tự động tải xuống khi cần.
- **NotoSerif**: Tự động tải xuống khi cần.
- Nếu muốn dùng font có sẵn, đặt file font (.ttf) vào cùng thư mục với mã nguồn.

-**Cách 1: Sử dụng file cài đặt tự động**

Chạy file `install.bat` (Windows) hoặc `install.sh` (Linux/macOS) để tự động cài đặt các thư viện cần thiết trong môi trường ảo (venv) và trình duyệt Playwright.

-**Cách 2: Sử dụng file setup.sh (Linux/macOS) - Khuyến nghị**

File `setup.sh` cung cấp các tính năng nâng cao:
- Tạo môi trường ảo sử dụng `uv` (nếu có) hoặc `venv` mặc định
- Cài đặt dependencies từ `requirements.txt`
- Cài đặt trình duyệt Playwright
- **Thêm alias `vvrt`** vào shell config (bash/zsh) để chạy scraper từ bất kỳ đâu
- Hỗ trợ chạy kiểm thử (pytest) sau khi cài đặt

```bash
chmod +x setup.sh
./setup.sh
```

**Lưu ý:** Alias `vvrt` có thể không hoạt động ngay lập tức. Nếu lệnh `vvrt` không được nhận diện, hãy chạy lệnh `source ~/.bashrc` (bash) hoặc `source ~/.zshrc` (zsh) hoặc khởi động lại terminal.

Sau khi cài đặt, bạn có thể chạy scraper bằng lệnh `vvrt` từ bất kỳ thư mục nào.
## Xử lý Cloudflare và Đăng nhập

Valvrare Team đã áp dụng các biện pháp bảo vệ (Cloudflare, JWT tokens). Công cụ này hỗ trợ chế độ **Dynamic Session Capture** để vượt qua các rào cản này:

1. **`--login`**: Khi chạy lệnh này, một trình duyệt thực (không ẩn danh) sẽ mở ra. Bạn hãy thực hiện đăng nhập trên trình duyệt đó. Sau khi hoàn tất và thấy nội dung truyện, hãy quay lại terminal và nhấn **Enter**.
2. **Lưu Session**: Thông tin đăng nhập (cookies, local storage) sẽ được lưu vào file ẩn `.vvr_session.json`. Các lần chạy sau sẽ tự động sử dụng session này mà không cần đăng nhập lại.
3. **`--refresh-session`**: Sử dụng khi session cũ đã hết hạn và bạn cần đăng nhập lại để lấy session mới.
4. **`--verbose`**: Hiển thị log chi tiết về các request, bao gồm cookies và headers. Rất hữu ích để kiểm tra xem session có được áp dụng đúng hay không.

Ví dụ:
```bash
python scraper.py "ten-truyen" --login --verbose
```

**Cảnh báo:** Không chia sẻ log khi dùng `--verbose` lên mạng hoặc cho người lạ vì nó chứa session token cá nhân của bạn.

## Cách sử dụng

**Phương pháp 1: Sử dụng Python trực tiếp**
```bash
python scraper.py
```

**Phương pháp 2: Sử dụng alias `vvrt` (sau khi chạy `setup.sh`)**
```bash
vvrt
```

Sau đó làm theo hướng dẫn trong terminal.

## Lưu ý
- Đảm bảo kết nối internet ổn định để tải nội dung và hình ảnh.
- Một số chương có thể bị bỏ qua nếu gặp lỗi tải (xem file `cac_chuong_da_bo_qua.txt`).
- Font tiếng Việt sẽ tự động tải xuống khi cần.
- Tôn trọng quyền tác giả và chỉ sử dụng nội dung tải về cho mục đích cá nhân.

## Loi thuong gap
- After running `setup.py`: can not run `vvrt` command not found -> manualy add alias to your shell config
```
# Bash/Zsh
alias vvrt='path-to-your-python path-to-scraper.py'
# Other shell

```

## Giấy phép
Dự án này được phát hành dưới [Giấy phép MIT](LICENSE). Xem file `LICENSE` để biết thêm chi tiết.

## Liên hệ
Nếu bạn có câu hỏi hoặc góp ý, vui lòng liên hệ qua email: notthanhtung@gmail.com hoặc mở issue trên repository.
