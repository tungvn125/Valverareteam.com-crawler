# Bản Đặc tả Thiết kế: Audio Drama v2 - Atmospheric Immersion

**Tác giả:** Gemini CLI
**Ngày:** 2026-03-29
**Trạng thái:** Đang chờ duyệt (Approved by User in Brainstorming)

## 1. Tổng quan (Project Overview)

Tính năng **Audio Drama v2: Atmospheric Immersion** nhằm mục tiêu nâng cấp khả năng tạo kịch bản âm thanh tự động của `vvr-scraper`. Thay vì chỉ có các giọng đọc thoại rời rạc, phiên bản này sẽ bổ sung nhạc nền (BGM) thông minh, có khả năng tự động thay đổi theo cảm xúc (Mood) của từng cảnh trong truyện và tự động điều chỉnh âm lượng (Ducking) để tạo ra trải nghiệm điện ảnh thực thụ.

## 2. Mục tiêu (Success Criteria)

1.  **Phân tích bối cảnh (Contextual Awareness):** Sử dụng LLM để nhận diện các thay đổi về tâm trạng (Mood Shift) trong văn bản.
2.  **Trộn âm đa tầng (Layered Mixing):** Kết hợp Voice (Giọng đọc) và BGM (Nhạc nền) trên hai track riêng biệt.
3.  **Điều khiển âm lượng thông minh (Auto-Ducking):** Nhạc nền tự động giảm âm lượng khi có tiếng nhân vật nói và tăng lại khi có khoảng lặng.
4.  **Chuyển cảnh mượt mà (Cross-fade):** Các bản nhạc nền chuyển đổi nhẹ nhàng (Fade-in/out) khi bối cảnh thay đổi.
5.  **Thư viện nhạc cộng đồng (Community BGM):** Cấu trúc thư mục đơn giản giúp người dùng dễ dàng đóng góp nhạc nền.

## 3. Kiến trúc Hệ thống (System Architecture)

### 3.1. Cấu trúc Thư mục Nhạc (BGM Library)
Hệ thống sẽ quét thư mục `bgm/` với cấu trúc sau:
```text
bgm/
├── action/      (Nhạc chiến đấu, dồn dập)
├── peaceful/    (Nhạc bình yên, thường nhật - Mặc định)
├── mysterious/  (Nhạc bí ẩn, huyền ảo)
├── romantic/    (Nhạc lãng mạn, nhẹ nhàng)
├── sad/         (Nhạc buồn, bi thương)
└── suspense/    (Nhạc hồi hộp, lo lắng)
```

### 3.2. Nâng cấp OpenAIParser (MoodEngine)
`OpenAIParser.parse_chapter()` sẽ được cập nhật để trả về danh sách kịch bản mở rộng:
- **`type: "mood_shift"`**: Đánh dấu điểm thay đổi nhạc nền.
- **`mood`**: Nhãn của mood tương ứng (`action`, `peaceful`, v.v.).

### 3.3. Bộ trộn âm thanh (MixingEngine)
Sử dụng thư viện `pydub` (hoặc tương đương) để thực hiện quy trình trộn âm:
1.  **Voice Segmenting:** Tổng hợp từng đoạn audio từ Vieneu.
2.  **BGM Ducking:** Tính toán vị trí có giọng nói và áp dụng giảm âm lượng nhạc nền (khoảng -15dB đến -20dB).
3.  **Cross-fading:** Khi gặp `mood_shift`, thực hiện Fade-out bài cũ (3s) và Fade-in bài mới (3s).

## 4. Quy trình xử lý (Data Flow)

1.  **Nhận văn bản:** Lấy nội dung chương truyện từ scraper.
2.  **Phân tích AI:** Gọi OpenAI API để lấy kịch bản có kèm Mood markers.
3.  **Chuẩn bị Audio:** 
    - Gọi Vieneu TTS cho từng đoạn hội thoại.
    - Chọn ngẫu nhiên file nhạc từ thư mục `bgm/mood_name/`.
4.  **Trộn (Mixing):**
    - Tạo Track BGM dài bằng tổng thời lượng chương.
    - Chèn Track Voice lên trên.
    - Áp dụng các hiệu ứng âm lượng (Ducking, Fading).
5.  **Xuất bản (Export):** Lưu file MP3 cuối cùng.

## 5. Xử lý lỗi & Fallback (Error Handling)

- **AI Parser lỗi:** Sử dụng mood `peaceful` cho toàn bộ chương.
- **Thiếu nhạc:** Nếu folder mood trống, không phát nhạc cho cảnh đó hoặc dùng file mặc định trong root `bgm/`.
- **Lỗi trộn âm:** Nếu MixingEngine gặp lỗi nghiêm trọng, hệ thống sẽ tự động fallback về bản Audio Drama v1 (chỉ có giọng đọc).

## 6. Kế hoạch Kiểm thử (Testing)

- **Mô phỏng (Mocking):** Tạo các kịch bản JSON mẫu để kiểm tra thuật toán Ducking và Cross-fade mà không cần gọi OpenAI thực tế.
- **Kiểm tra thư viện:** Đảm bảo hệ thống nhận diện đúng các file âm thanh trong thư mục `bgm/`.
- **Đánh giá thủ công:** Nghe thử các file MP3 được tạo ra để điều chỉnh độ trễ và mức giảm âm lượng (dB) tối ưu nhất.
