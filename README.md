# Web Novel Scraper

## Mô tả dự án
Dự án **Web Novel Scraper** là một công cụ được viết bằng Python để tải và lưu các chương truyện từ trang web [Valvrare Team](https://valvrareteam.net) dưới dạng file PDF và/hoặc EPUB. Công cụ này sử dụng các thư viện như `playwright`, `BeautifulSoup`, `ebooklib`, và `reportlab` để thu thập nội dung (bao gồm văn bản và hình ảnh minh họa) từ các chương truyện, sau đó tạo file đầu ra theo định dạng người dùng chọn.

## Tính năng
- **Tải nội dung song song**: Hỗ trợ tải nhiều chương cùng lúc với số lượng tác vụ song song tùy chỉnh.
- **Định dạng đầu ra**: Lưu nội dung dưới dạng PDF, EPUB, hoặc cả hai.
- **Hỗ trợ font tiếng Việt**: Lựa chọn giữa font `NotoSerif` và `DejaVuSans` cho file PDF.
- **Ghi log lỗi**: Lưu danh sách các chương bị lỗi vào file `cac_chuong_da_bo_qua.txt`.

## Yêu cầu cài đặt
Để chạy dự án, bạn cần cài đặt Python 3.8+ và các thư viện sau:

-**Cách 1: cài gói thủ oông**
```bash
pip install -r requirement.txt
```

Cài đặt trình duyệt Playwright:
```bash
playwright install
```
 Font hỗ trợ tiếng Việt:
- **DejaVuSans** (mặc định): Tải tại [DejaVu Fonts](https://dejavu-fonts.github.io/).
- **NotoSerif**: Tải tại [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Serif).
- Đặt file font (.ttf) vào cùng thư mục với mã nguồn để sử dụng trong file PDF.

-**Cách 2: Sử dụng file .bat**

chạy file `install.bat` để tự động cài đặt các thư viện cần thiết và trình duyệt Playwright.
## Cách sử dụng
1. Chạy file Python:
   ```bash
   python scraper.py
   ```
2. Nhập tên truyện (ví dụ: "Tên Truyện Của Bạn").
3. Chọn bỏ qua các chương minh họa (nhập `y` hoặc `n`).
4. Chọn định dạng file đầu ra:
   - `1`: PDF
   - `2`: EPUB
   - `3`: Cả PDF và EPUB
5. Nếu chọn PDF, chọn font (`1` cho NotoSerif, `2` cho DejaVuSans, hoặc Enter để dùng mặc định).
6. Nhập số lượng tác vụ song song (mặc định là 5).
7. Các file đầu ra sẽ được lưu trong thư mục mang tên truyện.

## Cấu trúc thư mục
Sau khi chạy, thư mục dự án sẽ có cấu trúc như sau:
```
project/
│
├── scraper.py                # File mã nguồn chính
├── cac_chuong_da_bo_qua.txt  # File log các chương bị lỗi (nếu có)
├── Tên Truyện/               # Thư mục chứa các file PDF/EPUB
│   ├── chuong-1.pdf
│   ├── chuong-1.epub
│   ├── ...
└── README.md                 # File hướng dẫn sử dụng
```

## Lưu ý
- Đảm bảo kết nối internet ổn định để tải nội dung và hình ảnh.
- Một số chương có thể bị bỏ qua nếu gặp lỗi tải (xem file `cac_chuong_da_bo_qua.txt`).
- Font tiếng Việt cần được cài đặt đúng để tránh lỗi hiển thị trong file PDF.
- Tôn trọng quyền tác giả và chỉ sử dụng nội dung tải về cho mục đích cá nhân.

## Giấy phép
Dự án này được phát hành dưới [Giấy phép MIT](LICENSE). Xem file `LICENSE` để biết thêm chi tiết.

## Liên hệ
Nếu bạn có câu hỏi hoặc góp ý, vui lòng liên hệ qua email: notthanhtung@gmail.com hoặc mở issue trên repository.