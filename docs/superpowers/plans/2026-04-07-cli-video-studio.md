# CLI Autonomous Video Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng tính năng render video MP4 tự động cho web novel qua CLI bằng cách sử dụng Playwright (Headless) và FFmpeg.

**Architecture:** 
1. Sử dụng `Playwright` để mở trình phát Cinema (HTML/JS) trong chế độ ẩn danh.
2. Inject một "Virtual Clock" script để điều khiển chính xác từng frame hình ảnh.
3. Chụp ảnh màn hình (buffer) và truyền trực tiếp vào `FFmpeg` qua stdin pipe để mã hóa video.
4. Ghép audio đã mix sẵn vào video kết quả.

**Tech Stack:** Playwright, FFmpeg (libx264), Python (asyncio), simple_term_menu.

---

### Task 1: Cập nhật CLI Interface (Interactive Menu)

**Files:**
- Modify: `vvr_scraper/cli.py`

- [ ] **Step 1: Cập nhật hàm `_parse_arguments` để thêm các tham số video.**

```python
        parser.add_argument('-f', '--format', nargs='+', default=['EPUB'], 
                           choices=['PDF', 'EPUB', 'HTML', 'MD', 'TXT', 'MP3', 'AD-MP3', 'MP4'], help="Định dạng file.")
        parser.add_argument('--fps', type=int, default=30, help="FPS cho video (mặc định 30).")
        parser.add_argument('--render-format', default='landscape', choices=['landscape', 'portrait'], 
                           help="Khung hình video (landscape/portrait).")
```

- [ ] **Step 2: Cập nhật hàm `_get_export_config` để hỗ trợ menu con cho MP4.**

```python
        format_items = ["PDF", "EPUB", "HTML", "Markdown (.md)", "Text (.txt)", "MP3 (Audiobook)", "MP3 (Audio Drama)", "MP4 (Cinematic Video)"]
        # ... logic chọn format ...
        if "MP4" in formats:
            # Chọn tỉ lệ khung hình
            ratio_idx = InteractiveUI.show_menu(["Landscape (16:9)", "Portrait (9:16)"], "Chọn tỉ lệ khung hình")
            render_format = "landscape" if ratio_idx == 0 else "portrait"
            
            # Chọn FPS
            fps_idx = InteractiveUI.show_menu(["30 FPS", "60 FPS"], "Chọn FPS")
            fps = 30 if fps_idx == 0 else 60
            
            config.update({'render_format': render_format, 'fps': fps})
```

- [ ] **Step 3: Commit.**
`git commit -m "cli: add MP4 export options and interactive menus"`

---

### Task 2: Xây dựng Module Video Renderer (Phần lõi)

**Files:**
- Create: `vvr_scraper/video_renderer.py`

- [ ] **Step 1: Tạo module `VideoRenderer` cơ bản với FFmpeg pipe.**

```python
import subprocess
import asyncio
from playwright.async_api import async_playwright

class VideoRenderer:
    def __init__(self, manifest_path, output_path, fps=30, format='landscape'):
        self.manifest_path = manifest_path
        self.output_path = output_path
        self.fps = fps
        self.width, self.height = (1920, 1080) if format == 'landscape' else (1080, 1920)

    async def render(self):
        # Start FFmpeg process
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-f', 'image2pipe', '-vcodec', 'png', '-r', str(self.fps),
            '-i', '-', '-pix_fmt', 'yuv420p', '-vcodec', 'libx264', '-crf', '18', self.output_path
        ]
        process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        # ... logic render ...
```

- [ ] **Step 2: Viết hàm `capture_frames` sử dụng Playwright.**
Dùng `page.screenshot(type='png')` trong vòng lặp dựa trên mốc thời gian của audio.

- [ ] **Step 3: Commit.**
`git commit -m "feat: implement core video rendering logic using Playwright and FFmpeg"`

---

### Task 3: Tích hợp và Đồng bộ hóa Audio

**Files:**
- Modify: `vvr_scraper/exporter.py`
- Modify: `vvr_scraper/video_renderer.py`

- [ ] **Step 1: Cập nhật `tao_file_mp4` (hàm wrapper) trong `exporter.py`.**
Hàm này sẽ gọi `VideoRenderer` sau đó dùng FFmpeg để gộp file audio `.mp3` vào file `.mp4`.

- [ ] **Step 2: Thực hiện lệnh FFmpeg cuối cùng để mux audio.**
`ffmpeg -i video_nosound.mp4 -i audio.mp3 -c copy -map 0:v:0 -map 1:a:0 final.mp4`

- [ ] **Step 3: Commit.**
`git commit -m "feat: add audio muxing to video export pipeline"`

---

### Task 4: Kiểm thử (Validation)

- [ ] **Step 1: Viết test case cho `VideoRenderer`.**
`tests/test_video_renderer.py` - Kiểm tra xem file MP4 có được tạo ra và có metadata (width, height, fps) đúng không.

- [ ] **Step 2: Chạy thử lệnh CLI.**
`vvrt test-slug --format MP4 --fps 30`

- [ ] **Step 3: Commit.**
`git commit -m "test: add video renderer validation tests"`
