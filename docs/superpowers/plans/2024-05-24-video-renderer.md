# VVR-Cinema Video Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng module Video Renderer để chuyển đổi các chương truyện Cinematic thành video MP4 sử dụng Playwright và FFmpeg.

**Architecture:** Sử dụng Playwright để điều khiển trình duyệt ở chế độ render thủ công (frame-by-frame). Mỗi frame được chụp ảnh màn hình và đẩy trực tiếp vào pipe của FFmpeg để mã hóa video.

**Tech Stack:** Python, Playwright, FFmpeg, JavaScript (Vanilla), CSS.

---

### Task 1: Cập nhật CSS cho chế độ Rendering

**Files:**
- Modify: `vvr_scraper/static/cinema.css`

- [ ] **Step 1: Thêm class `.rendering-mode` để ẩn UI và vô hiệu hóa animations**

```css
/* Rendering Mode */
body.rendering-mode #player-controls {
    display: none !important;
}

body.rendering-mode .bg-layer {
    transition: none !important;
    animation: none !important;
}

body.rendering-mode #vfx-overlay {
    transition: none !important;
    animation: none !important;
}

body.rendering-mode .word {
    transition: none !important;
}
```

- [ ] **Step 2: Commit**

```bash
git add vvr_scraper/static/cinema.css
git commit -m "style: add rendering-mode classes to cinema.css"
```

---

### Task 2: Cập nhật CinemaPlayer JS cho chế độ Rendering

**Files:**
- Modify: `vvr_scraper/static/cinema.js`

- [ ] **Step 1: Thêm property `isRendering` và phương thức `prepareForRendering`**

```javascript
// Trong constructor
this.isRendering = false;

// Thêm phương thức
prepareForRendering() {
    this.isRendering = true;
    document.body.classList.add('rendering-mode');
    this.stopSyncLoop();
    this.audio.pause();
    // Reset state để đảm bảo sạch sẽ
    this.resetState();
}
```

- [ ] **Step 2: Thêm logic tính toán Ken Burns thủ công**

```javascript
calculateKenBurns(effect, timeMs) {
    const duration = 20000; // 20s per cycle
    const p = (timeMs % duration) / duration;
    // Đơn giản hóa: linear nội suy cho demo, có thể dùng ease-in-out sau
    let scale = 1, x = 0, y = 0;
    
    switch(effect) {
        case 'ken-burns-in':
            scale = 1 + (0.1 * p);
            x = -1 * p; y = -1 * p;
            break;
        case 'ken-burns-out':
            scale = 1.2 - (0.2 * p);
            x = 1 - p; y = 1 - p;
            break;
        case 'ken-burns-left':
            scale = 1.1;
            x = 1 - (2 * p);
            break;
        case 'ken-burns-right':
            scale = 1.1;
            x = -1 + (2 * p);
            break;
    }
    return `scale(${scale}) translate(${x}%, ${y}%)`;
}
```

- [ ] **Step 3: Thêm phương thức `renderFrame(timeMs)`**

```javascript
renderFrame(timeMs) {
    // 1. Cập nhật events dựa trên timeMs
    this.processEvents(timeMs);
    
    // 2. Cập nhật Ken Burns thủ công cho các layer đang hiển thị
    if (this.bgCurrent.style.backgroundImage) {
        const effect = this.bgCurrent.dataset.effect || 'ken-burns-in';
        this.bgCurrent.style.transform = this.calculateKenBurns(effect, timeMs);
    }
    
    // 3. Cập nhật VFX thủ công (Ví dụ: flash)
    // (Cần mở rộng logic applyVFX để hỗ trợ manual timing)
    
    // 4. Cập nhật UI thời gian (nếu cần cho debug)
    this.lastTimeMs = timeMs;
}
```

- [ ] **Step 4: Commit**

```bash
git add vvr_scraper/static/cinema.js
git commit -m "feat: add renderFrame and manual animation logic to cinema.js"
```

---

### Task 3: Xây dựng Module VideoRenderer

**Files:**
- Create: `vvr_scraper/video_renderer.py`

- [ ] **Step 1: Implement lớp VideoRenderer với FFmpeg pipe**

```python
import os
import subprocess
import asyncio
from playwright.async_api import async_playwright
from loguru import logger

class VideoRenderer:
    def __init__(self, manifest_path, output_path, fps=30, render_format='landscape'):
        self.manifest_path = manifest_path
        self.output_path = output_path
        self.fps = fps
        self.width, self.height = (1920, 1080) if render_format == 'landscape' else (1080, 1920)

    async def render(self):
        # 1. Khởi tạo FFmpeg
        cmd = [
            'ffmpeg', '-y', '-f', 'image2pipe', '-vcodec', 'png',
            '-r', str(self.fps), '-i', '-',
            '-pix_fmt', 'yuv420p', '-vcodec', 'libx264', '-crf', '18',
            self.output_path
        ]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={'width': self.width, 'height': self.height})
            
            # Load page (giả sử server đang chạy hoặc dùng file://)
            abs_html_path = os.path.abspath("vvr_scraper/static/cinema.html")
            novel_rel_path = os.path.relpath(os.path.dirname(self.manifest_path), "novels")
            await page.goto(f"file://{abs_html_path}?path={novel_rel_path}")
            
            # Đợi manifest
            await page.wait_for_function("window.player && window.player.manifest")
            await page.evaluate("window.player.prepareForRendering()")
            
            duration_ms = await page.evaluate("window.player.audio.duration * 1000")
            if not duration_ms: # Fallback to last event
                duration_ms = await page.evaluate("Math.max(...window.player.events.map(e => e.end || e.start))")

            # 2. Render Loop
            current_ms = 0
            step_ms = 1000 / self.fps
            
            while current_ms <= duration_ms:
                await page.evaluate(f"window.player.renderFrame({current_ms})")
                screenshot = await page.screenshot(type='png')
                process.stdin.write(screenshot)
                current_ms += step_ms

            process.stdin.close()
            process.wait()
            await browser.close()
```

- [ ] **Step 2: Commit**

```bash
git add vvr_scraper/video_renderer.py
git commit -m "feat: implement core VideoRenderer class"
```

---

### Task 4: Kiểm tra tích hợp

**Files:**
- Create: `tests/test_video_renderer.py`

- [ ] **Step 1: Viết test case cơ bản**
- [ ] **Step 2: Chạy test và xác nhận video output được tạo**
- [ ] **Step 3: Commit**
