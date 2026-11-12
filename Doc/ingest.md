# `src/ir/ingest` — Tài liệu chi tiết

Package `ir.ingest` chịu trách nhiệm biến **video gốc** thành dữ liệu ingest:
`Video → Shot → Keyframe → FollowFrame`, kèm ảnh JPEG/WebP ghi ra đĩa.

```
video
  │  scan.py        probe metadata (duration, fps, kích thước, audio)
  ▼
Video
  │  shots.py       PySceneDetect ContentDetector + gộp burst ngắn
  ▼
Shot[]
  │  sampling.py    chọn timestamp keyframe trong mỗi shot
  │  junk.py        lọc frame rác + dHash chống trùng
  │  keyframes.py   decode + ghi ảnh keyframe
  ▼
Keyframe[]
  │  sampling.py    chọn timestamp follow frame sau keyframe
  │  follow.py      decode + ghi ảnh follow frame
  ▼
FollowFrame[]
```

Orchestrator là `src/ir/index/build.py` (không nằm trong package này) gọi lần lượt
các hàm trên và ghi kết quả vào SQLite.

---

## 1. Cấu trúc package

| File | Vai trò |
| --- | --- |
| `__init__.py` | Package rỗng, không export gì. |
| `scan.py` | Quét thư mục corpus, probe metadata video bằng PyAV. |
| `shots.py` | Detect shot, chuẩn hoá/gộp shot, gộp burst ngắn. |
| `sampling.py` | Tính timestamp keyframe và follow frame. |
| `junk.py` | Đo độ nét/độ sáng, phát hiện frame rác, dHash + Hamming. |
| `keyframes.py` | Decode video, chọn/ghi ảnh keyframe. |
| `follow.py` | Decode video, ghi các follow frame sau keyframe. |

### Data model liên quan (`src/ir/types.py`)

```python
class Video:        video_id, path, duration_ms, fps, width, height, has_audio
class Shot:         video_id, shot_idx, start_ms, end_ms, scene_score
class Keyframe:     video_id, shot_idx, kf_idx, ts_ms, path, kf_uid, generation,
                    ocr_text, objects
class FollowFrame:  video_id, shot_idx, kf_idx, frame_idx, ts_ms, path, generation
```

`path` của `Keyframe`/`FollowFrame` là đường dẫn **tương đối** so với root tương ứng:

- keyframe: `keyframes/<video_id>/g<generation>/<shot>_<kf>.jpg` (root = `artifacts_dir`)
- follow frame: `follow_frames/<video_id>/g<generation>/<shot>_<kf>_<frame>.<ext>`
  (root = `state_root`)

---

## 2. `scan.py`

### `VIDEO_EXTENSIONS`

```python
{".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v"}
```

So khớp không phân biệt hoa/thường qua `path.suffix.lower()`.

### `_container_duration_ms(container) -> int`

Lấy thời lượng theo thứ tự ưu tiên:

1. `container.duration` (micro-giây) → ms;
2. `video_stream.duration * time_base` → ms;
3. trả `0` nếu không xác định được.

### `probe_video(path) -> Video`

- Mở video bằng `av.open`.
- Lấy stream video đầu tiên; nếu không có → `ValueError("no video stream: ...")`.
- `video_id = path.stem` (tên file không đuôi).
- `path` lưu dạng chuỗi như được truyền vào.
- `fps = float(average_rate)` nếu có, ngược lại `None`.
- `has_audio = any(stream.type == "audio")`.

### `scan_corpus(corpus_dir) -> list[Video]`

- `rglob("*")` toàn bộ thư mục con.
- Giữ file có đuôi thuộc `VIDEO_EXTENSIONS`.
- Sắp xếp theo đường dẫn (ổn định, dễ resume/tái lập).
- Probe từng file; **một video lỗi sẽ raise** và làm hỏng cả lần scan
  (orchestrator bọc từng video, nhưng lỗi ở bước scan là lỗi toàn cục).

---

## 3. `shots.py`

### Kiểu dữ liệu

```python
Scene = tuple[int, int, float | None]   # start_frame, end_frame, score
```

### `_frame_to_ms(frame, fps) -> int`

`round(frame * 1000 / fps)`. Nếu `fps` không hợp lệ, `build_shots` thay bằng `25.0`.

### `build_shots(video_id, scenes, fps, duration_ms, min_shot_sec) -> list[Shot]`

Chuẩn hoá scene list thô (frame-based) thành shot (ms-based):

1. `duration_ms <= 0` → trả `[]`.
2. Mỗi scene → `[start_ms, end_ms, score]`:
   - `start_ms = clamp(_frame_to_ms(start_frame), 0, duration)`
   - `end_ms = clamp(_frame_to_ms(end_frame + 1), 0, duration)`
   - bỏ scene có `end <= start`.
3. Không còn scene nào → **một shot duy nhất** phủ toàn video
   `Shot(shot_idx=0, start=0, end=duration)`.
4. Sort theo `start`; gộp scene chồng lấn (dịch `start` lên bằng `end` của scene trước).
5. **Compact shot ngắn** (`end - start < min_shot_sec`):
   - nối vào shot trước bằng cách kéo `end` của shot trước;
   - giữ `scene_score` lớn nhất khi gộp;
   - nếu shot đầu tiên quá ngắn và còn shot khác: đẩy `start` của shot kế về đầu shot đầu rồi bỏ shot đầu.
6. Chuẩn hoá biên:
   - shot đầu `start = 0`;
   - chỗ hở giữa hai shot được lấp bằng cách kéo `end` shot trước tới `start` shot sau;
   - shot cuối `end = duration_ms`.
7. Đánh lại `shot_idx = 0..n-1`, bỏ shot rỗng.

`scene_score` chỉ được giữ khi scene gốc có score (hiện `ContentDetector` trả `None`).

### `merge_short_bursts(shots, min_ms) -> list[Shot]`

Gộp các **cụm ≥ 2 shot ngắn liên tiếp** (card chuyển cảnh, transition, cảnh rung)
thành một shot. Shot ngắn **đơn lẻ** được giữ nguyên.

- `min_ms <= 0` hoặc `< 2` shot → trả nguyên input.
- Đánh dấu shot có `end - start < min_ms`.
- Duyệt các run shot ngắn liên tiếp:
  - run ≥ 2: nếu có shot trước → kéo `end` shot trước tới cuối run;
    nếu run ở đầu và còn shot sau → đẩy `start` shot sau về đầu run;
    nếu cả danh sách đều ngắn → tạo một shot `[đầu run, cuối run]`.
- Chuẩn hoá biên giống `build_shots` và đánh lại `shot_idx`.
- `scene_score` bị mất sau bước này (các `Shot` mới không set score).

### `_pyscenedetect_scenes(video_path, cfg) -> list[Scene]`

Import lazy `scenedetect` (chỉ cần khi chạy detect):

```python
ContentDetector(threshold=cfg.pyscenedetect_threshold)
```

Trả `(start_frame, end_frame - 1, None)` cho từng scene.

### `detect_shots(video_path, video_id, fps, duration_ms, cfg) -> list[Shot]`

```python
scenes = _pyscenedetect_scenes(video_path, cfg)
shots  = build_shots(video_id, scenes, fps, duration_ms, cfg.min_shot_sec)
return merge_short_bursts(shots, int(cfg.pyscenedetect_burst_merge_sec * 1000))
```

---

## 4. `sampling.py`

### `sample_timestamps(start_ms, end_ms, cfg) -> list[int]`

Chọn timestamp cho keyframe trong một shot:

- `start = max(0, start_ms)`, `end = max(start + 1, end_ms)`, `length = end - start`, `mid = start + length // 2`.
- Nếu `length <= long_shot_sec * 1000` → **một timestamp ở giữa shot**.
- Shot dài:
  ```python
  step  = max(1, int(every_sec * 1000))
  count = min(max_per_shot, max(1, length // step))
  ts_i  = start + int((i + 0.5) * length / count)   # i = 0..count-1
  ```
  Trả danh sách đã sort và loại trùng.
- Timestamp luôn nằm **bên trong** shot (offset nửa khoảng), không lấy đúng biên.

### `follow_timestamps(ts_ms, shot_end_ms, cfg) -> list[int]`

- Bắt đầu từ `ts_ms + step_sec*1000`.
- Tăng dần theo `step_sec`, chỉ lấy khi `< shot_end_ms`.
- Dừng khi đạt `max_frames`.
- Follow frame không bao giờ vượt quá cuối shot hay trùng timestamp keyframe.

---

## 5. `junk.py`

### `to_gray(rgb) -> ndarray`

`rgb.astype(float32) @ [0.299, 0.587, 0.114]` (ITU-R BT.601).

### `laplacian_variance(gray) -> float`

Xấp xỉ Laplacian 4 hướng bằng `np.roll`, bỏ viền 1 px, trả variance.
Ảnh `< 3×3` → `0.0`. Giá trị càng thấp càng mờ/ít chi tiết.

### `is_junk(rgb, cfg) -> tuple[bool, float]`

Trả `(is_junk, sharpness)`; `sharpness` luôn được tính và dùng làm điểm dự phòng.

Thứ tự kiểm tra (dừng ở điều kiện đầu tiên đúng):

| Điều kiện | Ý nghĩa |
| --- | --- |
| `std < min_std` | ảnh gần như đồng màu |
| `mean < min_brightness` và `std < 2*min_std` | quá tối và phẳng |
| `mean > max_brightness` và `std < 2*min_std` | quá sáng/cháy và phẳng |
| `sharpness < min_sharpness` | quá mờ |

Ngược lại frame được coi là "tốt".

### `dhash(rgb, size=8) -> int`

- Chuyển grayscale, sample lưới `size × (size+1)` điểm.
- So sánh từng cặp ngang `small[:, 1:] > small[:, :-1]`.
- Đóng gói 64 bit thành một `int` (MSB trước).
- Dùng để phát hiện frame gần trùng trong cùng shot/nhóm follow.

### `hamming(a, b) -> int`

`(a ^ b).bit_count()` — số bit khác nhau giữa hai dHash.

---

## 6. `keyframes.py`

### `frame_time_ms(frame, stream) -> int`

Thời điểm frame theo thứ tự:

1. `frame.time` (giây) → ms;
2. `frame.pts * stream.time_base` → ms;
3. `0`.

### `save_frame_image(rgb, path, short_side, quality, image_format="JPEG")`

- `PIL.Image.fromarray(rgb)`.
- Nếu cạnh ngắn > `short_side`: resize LANCZOS giữ tỉ lệ, cạnh ngắn = `short_side`
  (không upscale ảnh nhỏ).
- Tạo thư mục cha, lưu với `format` và `quality`.
- Dùng chung cho keyframe (JPEG) và follow frame (WEBP/JPEG).

### `_write_frame(rgb, video_dir, artifacts_dir, shot_idx, kf_idx, cfg) -> str`

- Tên file: `f"{shot_idx:06d}_{kf_idx:03d}.jpg"` (luôn JPEG cho keyframe).
- Ghi ảnh bằng `cfg.short_side`, `cfg.jpeg_quality`.
- Trả path tương đối so với `artifacts_dir` dạng POSIX.

### `extract_keyframes(video_path, video_id, shots, cfg, artifacts_dir, generation=0) -> list[Keyframe]`

1. Với mỗi shot, sinh target `(timestamp, shot_idx, kf_idx, shot.end_ms)` từ
   `sample_timestamps`, rồi sort toàn bộ theo timestamp. Không có target → `[]`.
2. Thư mục đích: `<artifacts_dir>/keyframes/<video_id>/g<generation>/`.
3. Decode tuần tự bằng PyAV (`stream.thread_type = "AUTO"`).
4. Với mỗi frame:
   - Nếu đã tới timestamp của target kế tiếp (`pending[0].ts <= frame_ts`):
     - chuyển shot nếu target thuộc shot khác (`flush` shot cũ trước);
     - lấy RGB, chấm `is_junk`;
     - nếu không junk, tính `dhash`; nếu gần trùng một hash đã lưu **trong cùng shot**
       (`hamming < duplicate_distance`) → coi là junk;
     - nếu junk: lưu frame có `sharpness` cao nhất làm **fallback** cho shot;
     - nếu tốt: ghi JPEG, thêm `Keyframe`, tăng số keyframe đã lưu của shot.
   - Nhiều target cùng rơi vào một frame sẽ được xử lý trong cùng vòng `while`.
5. Kết thúc video: flush target còn lại để đóng shot cuối.
6. `flush()` shot:
   - Nếu shot **chưa lưu keyframe nào** nhưng có fallback → ghi fallback với `kf_idx=0`
     (frame sắc nét nhất trong số frame bị coi là junk).
   - Reset state của shot (`best`, `saved`, `hashes`, `shot`).
7. Nếu `len(keyframes) < len(shots)` → log warning `%d/%d shots produced a keyframe`.

Điểm cần lưu ý:

- Keyframe hợp lệ giữ `kf_idx` của target (do `sample_timestamps` đánh số), nên nếu
  một target bị junk thì `kf_idx` có thể bị khuyết; fallback luôn dùng `kf_idx = 0`.
- dHash chống trùng chỉ so trong phạm vi **một shot**.
- Fallback vẫn có thể là ảnh tối/mờ (vì mọi frame đều junk); mục tiêu là mỗi shot
  vẫn có ít nhất một ảnh đại diện.
- Chỉ stream video đầu tiên được dùng.

---

## 7. `follow.py`

### `Request`

```python
Request = tuple[int, int, int]   # ts_ms, shot_idx, kf_idx
```

### `follow_requests(keyframes, shots, cfg) -> list[Request]`

- Map `shot_idx → Shot`.
- Với mỗi keyframe, sinh timestamp bằng `follow_timestamps(kf.ts_ms, shot.end_ms, cfg)`.
- Bỏ keyframe không tìm thấy shot.
- Sort toàn bộ request theo timestamp.

### `extract_follow_frames(video_path, video_id, keyframes, shots, cfg, artifacts_dir, generation=0) -> list[FollowFrame]`

- `cfg` là `KeyframeConfig`; phần follow lấy từ `cfg.follow`.
- Không có request → `[]`.
- Thư mục đích: `<root>/follow_frames/<video_id>/g<generation>/`
  (`root` là `state_root` khi chạy qua `build`).
- Đuôi ảnh: `.webp` nếu `image_format == "webp"`, ngược lại `.jpg`.
- Decode tuần tự, xử lý mọi request có `ts <= frame_ts`:
  - nhóm theo `(shot_idx, kf_idx)`;
  - `dhash` + Hamming so với các frame đã lưu **trong cùng nhóm**;
    nếu trùng (`< duplicate_distance`) → **bỏ qua**;
  - `frame_idx` tăng dần theo nhóm;
  - tên file `f"{shot_idx:06d}_{kf_idx:03d}_{frame_idx:03d}{suffix}"`;
  - lưu ảnh với `follow.short_side`, `follow.quality`, format `WEBP`/`JPEG`;
  - thêm `FollowFrame` với path tương đối so với `root`.
- Dừng decode khi hết request.

Khác với keyframe:

- **Không** lọc độ sáng/độ nét (chỉ chống trùng dHash).
- **Không** có fallback: nhóm có thể ra 0 ảnh nếu mọi frame trùng nhau.
- Follow frame **không được embed**, chỉ dùng cho UI chọn frame và tính interval.

---

## 8. Cấu hình liên quan

Nguồn: `src/ir/config.py` và `config.yaml`.

### `ShotConfig`

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `pyscenedetect_threshold` | `27.0` | Ngưỡng `ContentDetector`. |
| `pyscenedetect_burst_merge_sec` | `1.5` | Độ dài tối đa để coi shot là "ngắn" khi gộp burst; `0` = tắt. |
| `min_shot_sec` | `0.5` | Shot ngắn hơn bị compact vào shot trước. |

### `KeyframeConfig`

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `short_side` | `448` | Cạnh ngắn ảnh keyframe (px). |
| `jpeg_quality` | `90` | Quality JPEG. |
| `long_shot_sec` | `10.0` | Shot dài hơn ngưỡng mới lấy nhiều keyframe. |
| `every_sec` | `5.0` | Khoảng cách mục tiêu giữa các keyframe. |
| `max_per_shot` | `5` | Số keyframe tối đa mỗi shot. |

### `KeyframeFilterConfig` (`keyframe.filter`)

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `min_sharpness` | `120.0` | Ngưỡng Laplacian variance. |
| `min_std` | `8.0` | Độ lệch chuẩn tối thiểu. |
| `min_brightness` | `20.0` | Ngưỡng tối. |
| `max_brightness` | `235.0` | Ngưỡng sáng. |
| `duplicate_distance` | `5` | Hamming distance tối thiểu để coi là khác ảnh. |

### `FollowConfig` (`keyframe.follow`)

| Field | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `step_sec` | `0.5` | Bước giữa các follow frame. |
| `max_frames` | `8` | Tối đa mỗi keyframe. |
| `window_sec` | `1.0` | Độ dài interval khi search/UI (không dùng khi extract). |
| `short_side` | `320` | Cạnh ngắn ảnh follow frame. |
| `quality` | `75` | Quality WebP/JPEG. |
| `image_format` | `"webp"` | `webp` hoặc `jpeg`. |

---

## 9. Orchestration trong `index/build.py`

Dù không thuộc package, đây là nơi các hàm ingest được gọi:

```python
detect_shots(video.path, video.video_id, video.fps or 25.0, video.duration_ms, cfg.shot)

extract_keyframes(video.path, video.video_id, shots, cfg.keyframe, cfg.artifacts_dir, generation)

extract_follow_frames(video.path, video.video_id, keyframes, shots, cfg.keyframe, cfg.state_root, generation)
```

- Ba bước độc lập: `shots`, `keyframes`, `follow`.
- Mỗi bước có trạng thái trong bảng `index_status`
  (`running` / `done` / `failed`) để resume.
- Trước khi chạy lại một bước, rows DB và thư mục của generation hiện tại bị xoá.
- `--reindex` đủ 3 bước → tăng generation, chạy xong dọn generation cũ.
- `--reindex` kèm `--only` → chạy lại trong generation hiện tại (không tạo mới).
- Sau khi xong toàn bộ video, `write_keyframe_manifest` ghi
  `artifacts/manifest.jsonl` cho bundle Kaggle.

### CLI

```bash
uv run ir index                       # resume: làm các bước còn thiếu
uv run ir index --only shots          # chỉ detect shot
uv run ir index --only keyframes      # chỉ extract keyframe
uv run ir index --only follow         # chỉ extract follow frames
uv run ir index --limit 3             # 3 video đầu
uv run ir index --reindex             # generation mới cho đủ 3 bước
uv run ir index --only follow --reindex
```

---

## 10. Output trên đĩa

```text
artifacts/                                  # bundle upload Kaggle
  keyframes/<video_id>/g<generation>/<shot:06d>_<kf:03d>.jpg

state/                                      # local-only
  follow_frames/<video_id>/g<generation>/<shot:06d>_<kf:03d>_<frame:03d>.webp
```

- Keyframe luôn `.jpg`.
- Follow frame `.webp` mặc định, `.jpg` nếu `image_format: jpeg`.
- Tên file dùng 6 chữ số cho `shot_idx`, 3 chữ số cho `kf_idx`/`frame_idx` để sort ổn định.
- DB lưu path tương đối (`keyframes/...`, `follow_frames/...`) nên có thể đổi root
  mà không phải sửa dữ liệu.

---

## 11. Test hiện có

| File | Nội dung |
| --- | --- |
| `tests/test_shots.py` | `build_shots`, `merge_short_bursts`, chuẩn hoá biên/gộp shot. |
| `tests/test_sampling.py` | Timestamp keyframe/follow theo cấu hình. |
| `tests/test_junk.py` | `to_gray`, Laplacian, `is_junk`, `dhash`/`hamming`. |
| `tests/test_keyframes.py` | Fallback keyframe, vị trí timestamp, generation, ảnh ghi ra. |
| `tests/test_follow_frames.py` | `follow_requests` và extract follow frame thực tế từ video tổng hợp. |
| `tests/test_build.py` | Resume, reindex, partial reindex, lỗi thiếu keyframe. |

Chạy:

```bash
uv run pytest
```

---

## 12. Ghi chú & giới hạn

- Mỗi video bị **decode hai lần** khi chạy đủ pipeline (một lần keyframe, một lần follow)
  vì hai bước tách biệt và có thể resume độc lập.
- Chỉ xử lý stream video đầu tiên; video không có stream video làm `probe_video` raise
  `ValueError`, nên lỗi này có thể dừng cả lần `scan_corpus`.
- `frame_time_ms` trả `0` nếu frame không có `time` lẫn `pts`, có thể làm lệch target
  với container lạ.
- `dhash` dùng lưới sample cố định (không resize ảnh), nên phụ thuộc kích thước frame gốc.
- Follow frame không lọc chất lượng ảnh, chỉ chống trùng; UI có thể nhận frame mờ.
- `merge_short_bursts` bỏ `scene_score` của các shot được tạo lại.
- `sample_timestamps` với shot dài có thể trả ít hơn `max_per_shot` nếu
  `length // step` nhỏ hơn `max_per_shot`.
