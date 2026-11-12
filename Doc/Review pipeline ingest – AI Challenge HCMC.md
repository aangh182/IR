# Review pipeline ingest – AI Challenge HCMC

Ghi chú: review dựa trên tài liệu `ingest.md`, chưa đọc code thật nên một số điểm là suy ra từ mô tả. Thiết kế tổng thể ổn: tách bước, resume được, có generation, có fallback. Các điểm dưới đây xếp theo mức ảnh hưởng tới recall.

## Rủi ro cao

**1. `merge_short_bursts` có thể làm mất nội dung montage.**

- Một cụm ≥2 shot ngắn (<1.5s) bị gộp thành một shot, rồi `sample_timestamps` chỉ lấy 1 keyframe ở giữa nếu shot ≤10s.
- Tin tức VN có rất nhiều đoạn cắt nhanh B-roll, mỗi cảnh \~1s. Cả đoạn đó chỉ còn 1 ảnh, hoặc không ảnh nào nếu bị kéo dính vào shot dài phía trước. Với KIS, đây là chỗ dễ mất đáp án nhất.
- Gợi ý: đừng gộp. Mỗi shot ngắn lấy 1 keyframe rồi dedupe bằng dHash hoặc embedding. Card chuyển cảnh để junk filter xử lý.

**2. Shot ≤10s chỉ có đúng 1 keyframe.**

- Shot 9s, camera pan hoặc đối tượng xuất hiện ở giây 1 và giây 8, chỉ lấy giây 4.5 là sẽ hụt.
- Ngưỡng gây nhảy bậc: shot 9.9s ra 1 ảnh, shot 10.1s ra 2 ảnh.
- Gợi ý: `count = ceil(length / every_sec)` hoặc hạ `long_shot_sec` xuống \~3–4s. Có thể thêm ảnh ở đầu/cuối shot nếu cuộc thi có truy vấn theo hành động hoặc chuỗi sự kiện.

**3. Timestamp có thể lệch giữa PySceneDetect và PyAV.**

- Ranh giới shot được đổi từ frame sang ms bằng `fps` của PyAV (`average_rate`), trong khi frame number do scenedetect đếm. Với video VFR, hai bên lệch nhau.
- `frame.time` của PyAV là pts tuyệt đối, chưa trừ `stream.start_time`. Video có start\_time ≠ 0 (TS, mp4 có edit list) sẽ lệch so với phép đếm frame từ 0.
- Gợi ý: lấy ms trực tiếp từ `FrameTimecode.get_seconds()` của scenedetect, và trừ `start_time` trong `frame_time_ms`.

**4. Kiểm tra `Keyframe.ts_ms` đang lưu timestamp nào.**

Nó phải là timestamp của frame thực sự được decode (`frame_ts`), không phải timestamp mục tiêu. Nếu BTC yêu cầu nộp theo frame index hoặc ms, lệch vài frame có thể làm sai kết quả. Nên lưu thêm `frame_idx` (theo fps gốc) để submit cho chắc.

## Trung bình

**5. Dedupe chỉ trong một shot.** Studio, người dẫn, intro, logo và cảnh phát lại lặp lại giữa các shot, nên top-k dễ bị một cảnh chiếm hết. Nên dedupe thêm theo embedding sau khi chạy model, hoặc so dHash với keyframe của vài shot lân cận.

**6. `dhash` không resize.** Lấy mẫu lưới cố định không lọc anti-alias nên nhạy với nhiễu nén và độ phân giải. Nên resize gray về 9×8 bằng `INTER_AREA` rồi mới so sánh.

**7. Ngưỡng `min_sharpness=120` phụ thuộc độ phân giải.**

- Laplacian variance tính trên frame gốc, nên video 1080p và 360p cho giá trị rất khác nhau.
- Cảnh tĩnh ít chi tiết như studio hay nền phẳng có thể bị coi là mờ oan.
- Gợi ý: resize về chiều rộng cố định (\~320px) trước khi tính. Nên log tỉ lệ junk theo video để chỉnh ngưỡng.

**8. Fallback có thể là ảnh rác.** Fallback chỉ chọn trong các target đã bị loại. Nên thử thêm frame lân cận (±0.5s) trước khi chịu nhận ảnh tối hoặc mờ. Ảnh fallback nên có cờ `is_fallback` để hạ trọng số hoặc loại khỏi index.

**9. Follow frame chỉ đi về phía sau keyframe.** Keyframe nằm giữa shot nên nửa đầu shot không có follow frame nào. Với bước chọn frame hoặc tính interval trong UI, nên lấy cả trước lẫn sau, hoặc phủ đều cả shot. Ngoài ra follow frame chưa được dedupe với chính keyframe, nên frame đầu tiên có thể trùng nó.

**10. `short_side=448` có thể quá nhỏ cho OCR.** Chữ chạy dưới màn hình hay lower-third trong tin tức rất nhỏ. Nếu OCR chạy trên ảnh 448 đã resize thì sẽ kém. Nên OCR trên frame gốc lúc extract, hoặc lưu bản độ phân giải cao hơn cho OCR.

**11. Shot detection.**

- `ContentDetector` bỏ sót chuyển cảnh mờ dần hoặc dissolve, và nhạy với chuyển động camera nhanh.
- Có thể thử `AdaptiveDetector`

## Nhỏ

- `scan_corpus` để một file hỏng làm chết cả lần scan. Nên bọc try/except từng video, ghi vào danh sách lỗi rồi chạy tiếp.
- `video_id = path.stem` sẽ đụng ID nếu hai thư mục có cùng tên file. Nên assert unique.
- `scene_score` hiện là code chết (luôn `None`). Nên tính từ stats manager hoặc bỏ field đi.
- `window_sec` nằm trong config ingest nhưng không dùng ở đây, dễ gây hiểu nhầm.
- Mỗi video bị decode 2 lần. Nếu corpus lớn thì cân nhắc gộp keyframe và follow vào một lượt decode.
