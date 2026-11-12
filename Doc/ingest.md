# `src/ir/ingest` — Tài liệu chi tiết

Package `ir.ingest` biến **video gốc** thành dữ liệu ingest:
`Video → Shot → Segment → Keyframe → FollowFrame`, kèm ảnh JPEG/WebP ghi ra đĩa.

Thiết kế hiện tại ưu tiên **recall**: bỏ burst merge, mỗi shot chia segment 4s và lấy
frame nét nhất trong từng segment, follow frame hai chiều, không còn fallback ảnh rác.

```
video
  │  scan.py        probe metadata, bỏ file lỗi, chặn video_id trùng
  ▼
Video
  │  shots.py       PySceneDetect ContentDetector (+ compact shot < min_shot_sec)
  ▼
Shot[]
  │  sampling.py    chia shot thành segment ceil(length / every_sec)
  │  junk.py        hard-junk (std/brightness) + sharpness ranking + dHash
  │  keyframes.py   quét ứng viên trong segment, chọn frame nét nhất
  ▼
Keyframe[]
  │  sampling.py    timestamp follow hai chiều quanh keyframe
  │  follow.py      decode + ghi follow frame, seed hash keyframe
  ▼
FollowFrame[]
```

Orchestrator là `src/ir/index/build.py` (không thuộc package) gọi lần lượt các hàm
trên và ghi kết quả vào SQLite.

---

## 1. Cấu trúc package

| File | Vai trò |
| --- | --- |
| `__init__.py` | Package rỗng. |
| `scan.py` | Quét corpus, probe metadata bằng PyAV, bỏ file hỏng. |
| `shots.py` | Detect shot, chuẩn hoá biên, compact shot ngắn. |
| `sampling.py` | Chia segment keyframe và sinh timestamp follow hai chiều. |
| `junk.py` | Hard-junk, sharpness ranking, dHash 9×8. |
| `keyframes.py` | Quét segment, chọn frame tốt nhất, ghi JPEG. |
| `follow.py` | Ghi follow frame trước/sau keyframe, chống trùng. |

### Data model (`src/ir/types.py`)

```python
class Video:        video_id, path, duration_ms, fps, width, height, has_audio
class Shot:         video_id, shot_idx, start_ms, end_ms, scene_score
class Keyframe:     video_id, shot_idx, kf_idx, ts_ms, path, kf_uid, generation,
                    ocr_text, objects
class FollowFrame:  video_id, shot_idx, kf_idx, frame_idx, ts_ms, path, generation
```

`path` là đường dẫn tương đối:

- keyframe: `keyframes/<video_id>/g<generation>/<shot>_<kf>.jpg` (root `artifacts_dir`)
- follow: `follow_frames/<video_id>/g<generation>/<shot>_<kf>_<frame>.<ext>` (root `state_root`)

`kf_idx` là **chỉ số segment** trong shot, không phải thứ tự ảnh được lưu. Nếu một
segment bị bỏ (toàn frame junk), `kf_idx` có thể bị khuyết.

---

## 2. `scan.py`

### `VIDEO_EXTENSIONS`

```python
{".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v"}
```

So khớp không phân biệt hoa/thường.

### `_container_duration_ms(container) -> int`

1. `container.duration` (micro-giây) → ms;
2. `video_stream.duration * time_base` → ms;
3. `0`.

### `probe_video(path) -> Video`

- Mở bằng `av.open`, lấy stream video đầu tiên; không có → `ValueError`.
- `video_id = path.stem`.
- `fps = float(average_rate)` nếu có.
- `has_audio = any(stream.type == "audio")`.

### `scan_corpus(corpus_dir) -> list[Video]`

- `rglob("*")`, lọc đuôi video, sort theo đường dẫn.
- **Bọc try/except từng file**: file hỏng bị log warning và bỏ qua, không làm chết
  cả lần scan.
- **Chặn `video_id` trùng**: hai file cùng stem (khác thư mục) → `ValueError`, vì
  `video_id` là khóa chính trong DB.

---

## 3. `shots.py`

### `build_shots(video_id, scenes, fps, duration_ms, min_shot_sec) -> list[Shot]`

1. `duration_ms <= 0` → `[]`.
2. Scene `(start_frame, end_frame, score)` → ms:
   - `start = clamp(round(start_frame * 1000 / fps))`
   - `end = clamp(round((end_frame + 1) * 1000 / fps))`
   - bỏ scene rỗng.
3. Không còn scene → một shot phủ toàn video.
4. Sort, gộp scene chồng lấn.
5. **Compact** shot ngắn hơn `min_shot_sec` (mặc định 0.5s) vào shot trước,
   giữ `scene_score` lớn nhất. Đây là ngưỡng sàn, khác với burst merge.
6. Chuẩn hoá biên: shot đầu `start = 0`, lấp chỗ hở bằng cách kéo `end` shot trước,
   shot cuối `end = duration_ms`.
7. Đánh lại `shot_idx`.

`scene_score` hiện luôn `None` vì `ContentDetector` không trả score.

### `merge_short_bursts(shots, min_ms) -> list[Shot]`

Gộp cụm **≥ 2 shot ngắn liên tiếp** thành một shot; shot ngắn đơn lẻ được giữ.
`min_ms <= 0` → trả nguyên input.

**Mặc định đã tắt** (`pyscenedetect_burst_merge_sec: 0.0`) để mỗi cảnh ngắn vẫn có
keyframe riêng. Hàm vẫn còn để bật lại khi cần giảm shot vụn.

### `detect_shots(...)`

```python
scenes = _pyscenedetect_scenes(video_path, cfg)
shots  = build_shots(video_id, scenes, fps, duration_ms, cfg.min_shot_sec)
return merge_short_bursts(shots, int(cfg.pyscenedetect_burst_merge_sec * 1000))
```

---

## 4. `sampling.py`

### `shot_segments(start_ms, end_ms, cfg) -> list[tuple[int, int]]`

Chia shot thành các segment đều nhau:

```python
length = max(1, end - start)
count  = max(1, ceil(length / (every_sec * 1000)))
segment_i = (start + length * i // count, start + length * (i + 1) // count)
```

- Shot 1s với `every_sec=4` → 1 segment phủ cả shot.
- Shot 34s → 9 segment.
- Không cap số segment; shot càng dài càng nhiều keyframe.
- Mỗi segment là vùng sở hữu của đúng một keyframe, không chồng lấn.

### `follow_timestamps(ts_ms, shot_start_ms, shot_end_ms, cfg) -> list[int]`

- Sinh tối đa `max_frames` timestamp mỗi phía, bước `step_sec`.
- Nếu `bidirectional=False`, bỏ phía trước.
- Chọn `max_frames` timestamp **gần keyframe nhất** (hai phía), trả về đã sort.
- Không lấy timestamp trùng keyframe, không vượt biên shot.

---

## 5. `junk.py`

### `to_gray(rgb) -> ndarray`

`rgb @ [0.299, 0.587, 0.114]` (BT.601).

### `metric_gray(rgb, width) -> ndarray`

- Nếu ảnh rộng hơn `width`, resize **BOX** (area) giữ tỉ lệ.
- Trả grayscale float.
- Dùng chung cho hard-junk, sharpness và dHash để giảm chi phí và ổn định scale.

### `laplacian_variance(gray) -> float`

Laplacian 4 hướng bằng `np.roll`, bỏ viền 1px, trả variance.
**Chỉ dùng để xếp hạng**, không phải cổng chặn cứng. Ảnh `< 3×3` → `0.0`.

### `is_hard_junk(gray, cfg) -> bool`

| Điều kiện | Ý nghĩa |
| --- | --- |
| `std < min_std` | gần như đồng màu |
| `mean < min_brightness` và `std < 2*min_std` | tối và phẳng |
| `mean > max_brightness` và `std < 2*min_std` | sáng/cháy và phẳng |

Không còn ngưỡng `min_sharpness`: dữ liệu corpus 720p cho thấy gần như 0% frame
dưới ngưỡng cũ, nên sharpness chỉ dùng để chọn frame tốt nhất.

### `dhash_gray(gray, size=8) -> int`

- Resize grayscale về `(size+1) × size` bằng `BOX`.
- So sánh từng cặp ngang, đóng gói 64 bit thành `int`.
- `dhash(rgb)` là wrapper qua `to_gray`.

### `hamming(a, b)`

`(a ^ b).bit_count()`.

---

## 6. `keyframes.py`

### `frame_time_ms(frame, stream) -> int`

1. `frame.time` → giây, **trừ `stream.start_time * time_base`**;
2. `frame.pts * time_base` → giây, trừ offset tương tự;
3. `0`.

Guard `start_time` cần cho container có start_time ≠ 0; corpus hiện tại start_time = 0.

### `save_frame_image(rgb, path, short_side, quality, image_format)`

- Resize LANCZOS nếu cạnh ngắn > `short_side`, không upscale.
- Lưu JPEG cho keyframe, WebP/JPEG cho follow.

### `extract_keyframes(...) -> list[Keyframe]`

1. Sinh toàn bộ segment từ `shot_segments`, sort theo thời gian.
2. Decode tuần tự. Khi timestamp vượt cuối segment hiện tại → **finalize** segment
   và chuyển sang segment kế.
3. Trong mỗi segment, quét ứng viên mỗi `candidate_step_sec` (mặc định 0.25s),
   bắt đầu lệch nửa bước để tránh đúng biên segment.
4. Với mỗi ứng viên:
   - tính grayscale tại `metric_width` (320);
   - nếu `is_hard_junk` → bỏ;
   - tính sharpness, dHash;
   - giữ **top 4** frame có sharpness cao nhất trong segment (đủ để thay thế nếu
     ứng viên tốt nhất bị loại vì trùng/gần keyframe trước).
5. Finalize segment: duyệt ứng viên theo sharpness giảm dần, chọn frame đầu tiên
   thỏa:
   - cách mọi keyframe đã chọn trong cùng shot ≥ `min_gap_sec`;
   - dHash cách mọi keyframe đó ≥ `duplicate_distance`.
   Nếu không có ứng viên nào thỏa → **segment không có keyframe** (không fallback).
6. Ghi ảnh JPEG với `short_side`/`jpeg_quality`; `ts_ms` là timestamp frame thật,
   `kf_idx` là chỉ số segment.
7. Log warning nếu số shot có keyframe ít hơn tổng số shot.

Điểm quan trọng:

- Không còn fallback: frame junk không bao giờ được ghi.
- Segment không có frame non-junk bị bỏ; với corpus hiện tại tỉ lệ hard-junk ~0.15%
  nên blind spot rất nhỏ.
- `min_gap_sec` chống hai segment liền kề chọn hai frame sát nhau ở biên.
- dHash chỉ so trong cùng shot; dedupe xuyên shot **chưa làm** (xem giới hạn).

---

## 7. `follow.py`

### `follow_requests(keyframes, shots, cfg) -> list[Request]`

```python
Request = tuple[int, int, int]   # ts_ms, shot_idx, kf_idx
```

- Với mỗi keyframe, lấy shot tương ứng.
- Sinh timestamp hai chiều bằng
  `follow_timestamps(kf.ts_ms, shot.start_ms, shot.end_ms, cfg)`.
- Sort toàn bộ request theo timestamp.

### `extract_follow_frames(..., keyframe_root=None) -> list[FollowFrame]`

- `keyframe_root` mặc định là `artifacts_dir`; `build.py` truyền `cfg.artifacts_dir`
  vì keyframe nằm trong `artifacts/`, còn follow ghi vào `state/`.
- **Seed hash**: đọc ảnh keyframe, tính dHash, đưa vào danh sách hash của nhóm
  `(shot_idx, kf_idx)`. Nhờ vậy frame follow đầu tiên gần trùng keyframe bị bỏ.
- Decode tuần tự, xử lý request khi timestamp vượt mốc:
  - tính dHash frame;
  - nếu Hamming `< duplicate_distance` với hash trong nhóm → bỏ;
  - nếu không, ghi WebP/JPEG với `follow.short_side`/`follow.quality`;
  - `frame_idx` tăng dần theo nhóm.
- Không lọc brightness/sharpness; không fallback; nhóm có thể ra ít hơn `max_frames`.
- Follow frame **không được embed**.

---

## 8. Cấu hình

### `ShotConfig`

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `pyscenedetect_threshold` | `27.0` | Ngưỡng `ContentDetector`. |
| `pyscenedetect_burst_merge_sec` | `0.0` | Tắt gộp burst; đặt `1.5` để bật. |
| `min_shot_sec` | `0.5` | Shot ngắn hơn bị compact vào shot trước. |

### `KeyframeConfig`

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `short_side` | `448` | Cạnh ngắn ảnh keyframe. |
| `jpeg_quality` | `90` | Quality JPEG. |
| `every_sec` | `4.0` | Độ dài mục tiêu mỗi segment. |
| `candidate_step_sec` | `0.25` | Bước quét ứng viên trong segment. |
| `min_gap_sec` | `1.0` | Khoảng cách tối thiểu giữa keyframe cùng shot. |

Đã bỏ `long_shot_sec` và `max_per_shot`: số keyframe tính trực tiếp từ độ dài shot.

### `KeyframeFilterConfig`

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `min_std` | `8.0` | Độ lệch chuẩn tối thiểu. |
| `min_brightness` | `20.0` | Ngưỡng tối. |
| `max_brightness` | `235.0` | Ngưỡng sáng. |
| `duplicate_distance` | `5` | Hamming tối thiểu để coi là khác ảnh. |
| `metric_width` | `320` | Chiều rộng dùng tính junk/sharpness/dHash. |

Đã bỏ `min_sharpness`.

### `FollowConfig`

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `step_sec` | `0.5` | Bước giữa các follow frame. |
| `max_frames` | `8` | Tổng tối đa mỗi keyframe. |
| `window_sec` | `1.0` | Độ dài interval khi search/UI (không dùng khi extract). |
| `short_side` | `320` | Cạnh ngắn ảnh follow. |
| `quality` | `75` | Quality WebP/JPEG. |
| `image_format` | `webp` | `webp` hoặc `jpeg`. |
| `bidirectional` | `true` | Lấy cả trước và sau keyframe. |

---

## 9. Orchestration trong `index/build.py`

```python
detect_shots(video.path, video.video_id, video.fps or 25.0, video.duration_ms, cfg.shot)

extract_keyframes(video.path, video.video_id, shots, cfg.keyframe, cfg.artifacts_dir, generation)

extract_follow_frames(
    video.path, video.video_id, keyframes, shots, cfg.keyframe,
    cfg.state_root, generation, keyframe_root=cfg.artifacts_dir,
)
```

- Ba bước độc lập: `shots`, `keyframes`, `follow`, có trạng thái trong `index_status`
  để resume.
- Chạy lại một bước sẽ xoá rows DB và thư mục của generation hiện tại.
- `--reindex` đủ 3 bước → generation mới và dọn generation cũ.
- `--reindex` + `--only` → chạy lại trong generation hiện tại.
- Sau khi xong, `write_keyframe_manifest` ghi `artifacts/manifest.jsonl`.

### CLI

```bash
uv run ir index                       # resume các bước còn thiếu
uv run ir index --only shots
uv run ir index --only keyframes
uv run ir index --only follow
uv run ir index --limit 3
uv run ir index --reindex             # áp dụng sampling mới
uv run ir index --only follow --reindex
```

---

## 10. Output trên đĩa

```text
artifacts/
  keyframes/<video_id>/g<generation>/<shot:06d>_<kf:03d>.jpg

state/
  follow_frames/<video_id>/g<generation>/<shot:06d>_<kf:03d>_<frame:03d>.webp
```

- Keyframe luôn `.jpg`; follow mặc định `.webp`.
- Tên file 6 chữ số cho `shot_idx`, 3 chữ số cho `kf_idx`/`frame_idx`.
- DB lưu path tương đối nên có thể đổi root mà không sửa dữ liệu.

---

## 11. Test hiện có

| File | Nội dung |
| --- | --- |
| `tests/test_shots.py` | `build_shots`, `merge_short_bursts`, chuẩn hoá biên. |
| `tests/test_sampling.py` | `shot_segments`, follow hai chiều, cap theo khoảng cách. |
| `tests/test_junk.py` | hard-junk, sharpness, dHash/Hamming. |
| `tests/test_keyframes.py` | Một keyframe mỗi shot, segment scan trên video tổng hợp. |
| `tests/test_follow_frames.py` | Request hai chiều, extract trước/sau, seed hash. |
| `tests/test_build.py` | Resume, reindex, partial reindex, lỗi thiếu keyframe. |

```bash
uv run pytest
```

---

## 12. Ghi chú & giới hạn

- **Chưa dedupe xuyên shot**: bỏ burst merge nên logo/card/intro lặp lại có thể
  chiếm nhiều slot top-k. Đã quyết định defer; nên đo bằng eval rồi làm MMR ở search.
- **Không fallback**: segment toàn frame hard-junk sẽ không có keyframe. Với corpus
  hiện tại tỉ lệ này rất thấp, nhưng cảnh tối/phẳng kéo dài có thể thành điểm mù.
- **Sharpness chỉ xếp hạng**, không loại frame mờ; frame dissolve có thể vẫn được chọn
  nếu không bị hard-junk.
- **Decode hai lần** cho keyframe và follow; chưa gộp một pass.
- **OCR**: ảnh keyframe 448px có thể quá nhỏ cho chữ nhỏ; khi làm OCR nên chạy trên
  frame gốc lúc extract hoặc lưu bản high-res riêng.
- **`scene_score`** vẫn là code chết; có thể bỏ field hoặc tính từ stats manager sau.
- **`window_sec`** nằm trong config ingest nhưng chỉ search/UI dùng.
- Corpus hiện tại: 53 video, 720p, CFR 25fps, `start_time = 0`; các guard VFR/start_time
  vẫn được giữ để an toàn với corpus khác.
