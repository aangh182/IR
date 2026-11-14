# AIC2024 Known-Item Search

Hệ thống tìm kiếm video theo mô tả (Textual KIS), ảnh vẽ/upload (Video KIS) và Q&A cho vòng chung kết AIC2024.

## Trạng thái

- [x] Phase 0: nền tảng, config, SQLite schema, CLI, FastAPI, web scaffold
- [x] Phase 1: shot detection + keyframe extraction (PyAV, lọc frame rác)
  - [x] Shot detection: PySceneDetect `ContentDetector` (đã thay TransNetV2)
  - [x] Gộp burst card/transition/cảnh rung thành một shot
  - [x] Bỏ TransNetV2, CLI/config song song và notebook Colab/Kaggle
  - [x] Chạy keyframe trên corpus thật (53 video minibatch)
- [x] Phase 2: CLIP embedding (Kaggle notebook) + FAISS + search text + web UI keyframe/video
- [ ] Phase 3: OCR / ASR / object boost
- [ ] Phase 4: UI hoàn chỉnh (grid, player seek, timer, DRES payload)
- [ ] Phase 5: eval & tune

## Yêu cầu

- `uv >= 0.13` (tự tải Python 3.11 theo `.python-version`)
- Node >= 20.19 cho web

## Cài đặt local (search/serve, CPU)

```bash
uv python install 3.11
uv sync --group ml --group index --group serve
uv run ir init
uv run uvicorn ir.api.main:app --reload
```

Web:

```bash
cd web
npm install
npm run dev
```

Chi tiết cách mở web, dùng UI và nộp bài DRES: xem [Chạy web UI](#chạy-web-ui).

## Index

```bash
uv run ir index --limit 3          # thử 3 video đầu
uv run ir index                    # toàn bộ corpus trong config
uv run ir index --only shots       # chỉ detect shot
uv run ir index --reindex          # tạo generation mới rồi compact bản cũ
uv run ir index --only follow --reindex  # chạy lại follow frames tại generation hiện tại
uv run ir stats
```

`--reindex` chỉ tạo generation mới khi chạy đủ 3 bước (shots + keyframes + follow). Khi đi kèm `--only`, bước được chọn sẽ chạy lại ngay trong generation hiện tại, không đụng tới keyframe/embedding hay generation cũ.

Shot detection dùng PySceneDetect `ContentDetector`. Trong `config.yaml`:

- `shot.pyscenedetect_threshold`: ngưỡng cắt cảnh (mặc định 27.0).
- `shot.pyscenedetect_burst_merge_sec`: gộp các cụm ≥2 shot ngắn liên tiếp (card
  chuyển cảnh, transition, cảnh rung) thành một shot, giữ nguyên shot ngắn đơn lẻ.
  Mặc định `0` (tắt) để mỗi cảnh ngắn vẫn có keyframe riêng; bật lại bằng
  `1.5` nếu muốn giảm shot vụn.
- `shot.min_shot_sec`: thời lượng shot tối thiểu (shot ngắn hơn bị gộp vào shot trước).

### Keyframe sampling

Mỗi shot được chia thành các segment đều nhau, mỗi segment lấy một keyframe:

- `keyframe.every_sec`: độ dài mục tiêu mỗi segment (mặc định 4.0).
  `count = ceil(shot_length / every_sec)`, không cap.
- `keyframe.candidate_step_sec`: bước quét ứng viên trong segment (mặc định 0.25).
  Mỗi segment chọn frame non-junk có sharpness cao nhất.
- `keyframe.min_gap_sec`: khoảng cách tối thiểu giữa hai keyframe trong cùng shot
  (mặc định 1.0), tránh chụm cụm.
- `keyframe.filter`: hard-junk chỉ theo `std`/brightness (`min_std`, `min_brightness`,
  `max_brightness`); `duplicate_distance` dùng dHash 9×8 `INTER_AREA`.
  `metric_width` (mặc định 320) là chiều rộng dùng để tính junk/sharpness.
- Segment không có frame non-junk sẽ **không tạo keyframe** (không còn fallback ảnh rác).

## Layout artifacts

`artifacts/` là **bundle duy nhất để upload Kaggle**, chỉ gồm keyframe và manifest:

```
artifacts/
  keyframes/<video_id>/g<generation>/<shot>_<kf>.jpg
  manifest.jsonl        # kf_uid, video_id, generation, shot_idx, kf_idx, ts_ms, path
```

Toàn bộ state local nằm trong `state/` (không upload):

```
state/
  metadata.sqlite
  follow_frames/<video_id>/g<generation>/*.webp
  embed/                 # embedding profile "clip"
    shards/<video_id>/...
    embeddings.f16.npy
    id_map.npy
    faiss.index
    manifest.json
  embed_siglip2/         # embedding profile "siglip2"
    shards/<video_id>/...
    embeddings.f16.npy
    id_map.npy
    faiss.index
    manifest.json
```

Các profile dùng chung `metadata.sqlite` và follow frames; chỉ thư mục index tách riêng.

Repo cũ đang để DB/follow/embed trong `artifacts/`; chạy một lần `uv run ir migrate` để chuyển sang layout mới (không cần chạy lại keyframe).

## Embedding (Kaggle)

`scripts/kaggle_embed.ipynb` là notebook self-contained, xuất **mỗi video một shard** để chạy Kaggle theo nhiều batch. Notebook đọc `manifest.jsonl`, không cần SQLite.

1. Tạo bundle keyframe rồi upload thành Kaggle Dataset; bật GPU + Internet:

```bash
uv run ir export-keyframes          # -> artifacts_keyframes.zip
```

2. Chọn batch bằng env:
   - mặc định: tất cả video;
   - `EMBED_VIDEO_OFFSET` + `EMBED_VIDEO_LIMIT` (ví dụ 0/100, 100/100, ...);
   - hoặc `EMBED_VIDEO_IDS=L01_V001,L01_V002`.
3. Tải `artifacts_embed_shards.zip` về máy rồi import:

```bash
uv run ir import-shards artifacts_embed_shards.zip
```

Lệnh này giải nén vào `state/embed/shards/<video_id>/` và merge luôn. Nếu chỉ muốn giải nén: `uv run ir import-shards <zip> --no-merge`. Merge lại thủ công: `uv run ir merge`.

`ir merge` đọc toàn bộ shard hiện có và build `embeddings.f16.npy`, `id_map.npy`, `faiss.index`, `manifest.json`. Có thể merge sau mỗi batch.

Mỗi shard gồm `embeddings.f16.npy`, `id_map.npy`, `manifest.json`; notebook resume được theo từng video.

### Nhiều embedding model (CLIP + SigLIP2)

`config.yaml` khai báo `embed.profiles`; mỗi profile có `model`, `dim`, `encoder` và thư mục index
riêng dưới `state/`. `embed.default` chọn profile mặc định.

| profile | model | dim | encoder | index |
| --- | --- | --- | --- | --- |
| `clip` | `sentence-transformers/clip-ViT-B-16` | 512 | `sentence_transformers` | `state/embed` |
| `siglip2` | `hf-hub:timm/ViT-B-16-SigLIP2-384` | 768 | `open_clip` | `state/embed_siglip2` |

Hai index dùng chung DB và follow frames; chỉ model đang chọn được lazy-load khi search.

```bash
uv run ir models                                                     # profile + trạng thái index
uv run ir import-shards artifacts_embed_shards_siglip2-384.zip --model siglip2
uv run ir merge --model siglip2                                      # merge lại nếu cần
uv run ir search "a person at a desk" --model siglip2
uv run ir search "a person at a desk"                                # dùng embed.default (clip)
```

Web có dropdown `Model` (dữ liệu từ `GET /api/models`); `POST /api/search` nhận thêm
`{"model": "siglip2"}`. Model không có index sẽ hiện `chưa có index` và bị disable.

## Object tagging (Kaggle)

`scripts/kaggle_objects.ipynb` chạy YOLO11 pretrained COCO (`yolo11x.pt`) trên từng keyframe
trong bundle keyframe ở trên, rồi xuất **object shard theo video**:

```
objects_shards/
  shards/<video_id>/objects.jsonl
  shards/<video_id>/manifest.json
```

Mỗi dòng `objects.jsonl` lưu nhãn COCO duy nhất + số instance, không lưu bbox:

```json
{"kf_uid": 123, "video_id": "L01_V001", "generation": 0, "shot_idx": 4, "kf_idx": 1, "ts_ms": 16000, "objects": ["car", "person"], "counts": {"car": 2, "person": 1}}
```

Chạy notebook trên Kaggle (bật GPU + Internet, add dataset keyframe), tải
`artifacts_objects_shards.zip` rồi import:

```bash
uv run ir import-objects artifacts_objects_shards.zip
uv run ir objects          # xem nhãn + số keyframe
```

Import giải nén shard vào `state/objects/shards/<video_id>/` rồi ghi vào SQLite:
`keyframes.objects`/`obj_count` và bảng `keyframe_objects` (label + count) để filter nhanh.
Import lại cùng zip an toàn: nhãn của keyframe được thay thế, không cộng dồn. Keyframe
không còn tồn tại (do reindex) bị bỏ qua và đếm ở `missing`.

Object shard là artifact gốc (JSONL, dễ inspect); SQLite chỉ là index dẫn xuất. Có thể xoá
`state/objects` rồi import lại bất cứ lúc nào.

Filter theo object (nhiều nhãn là AND):

```bash
uv run ir search "a person at a desk" --object person
uv run ir search "a red car" --object car --object person
```

Trên web, ô `Lọc object COCO` nhận danh sách nhãn cách nhau bởi dấu phẩy; các chip
`Object có sẵn` lấy từ `GET /api/objects` để chọn nhanh. Kết quả trả thêm
`evidence.objects` để hiển thị tag trên card.

## Chạy web UI

Web là Vite React, nằm trong `web/` và gọi API qua proxy `/api` → `http://127.0.0.1:8000`.

### 1. Bật API

```bash
uv run uvicorn ir.api.main:app --reload
# hoặc: uv run ir serve --reload
```

### 2. Bật web

```bash
cd web
npm install
npm run dev
```

- Phải chạy trong `web/`, không phải thư mục gốc repo (gốc không có `package.json`).
- Nếu shell có `NODE_ENV=production`, npm sẽ bỏ qua devDependencies và Vite không khởi động được:
  dùng `NODE_ENV=development npm install --include=dev`.

Vite lắng nghe `0.0.0.0:5173` (`strictPort`, không tự nhảy cổng) nên mở được cả từ máy khác:

```
http://<ip-máy-chạy>:5173
```

### 3. Mở web khi SSH từ máy khác subnet

Nếu máy local và máy chạy web khác subnet thì chỉ cổng 22 tới được, không mở được
`http://<ip>:5173` trực tiếp. Dùng SSH tunnel từ **máy local**:

```bash
ssh -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 team06@<ip-máy-chạy>
```

rồi mở `http://localhost:5173` trên máy local. Với VS Code Remote-SSH thì forward
cổng `5173` và `8000` ở tab **PORTS**.

### 4. Dùng UI

1. Gõ mô tả **tiếng Việt** (hoặc tiếng Anh) vào ô tìm kiếm (hoặc bấm một ví dụ) → `Tìm`;
   query được dịch sang tiếng Anh bằng Gemini trước khi search.
2. Grid kết quả hiện keyframe kèm score; bấm một card để chọn.
3. Panel phải: player tự seek tới frame, dải thumbnail bên dưới cho chọn keyframe
   hoặc follow frame đúng nhất.
4. Nút `Copy DRES payload` copy JSON `answerSets` của frame đang chọn (KIS, `start = end`).
5. Panel `DRES` hiển thị user, evaluation, task đang chạy và form nộp bài (xem bước 5).

### 5. Nộp bài lên DRES

Panel DRES có 4 tab theo đúng quy định của BTC:

| Tab | Trường nhập | Payload gửi đi |
| --- | --- | --- |
| KIS / VKIS | Video ID, thời gian frame | `mediaItemName` + `start = end = ts_ms` |
| Q&A | Video ID, câu trả lời, thời gian frame | `text: QA-<ANSWER>-<VIDEO_ID>-<TS>` |
| TRAKE | Video ID, danh sách frame ids | `text: TR-<VIDEO_ID>-<ID1>,<ID2>,...` |
| Raw JSON | payload `ApiClientSubmission` | gửi nguyên văn |

- Tab tự chọn theo task đang chạy (`tkis`/`vkis` → KIS, `qa` → Q&A, `trake` → TRAKE).
- Video ID tự điền từ kết quả đang chọn, thời gian tự điền theo frame đang chọn;
  nhập được cả `MM:SS.mmm` lẫn số ms. Phần mở rộng `.mp4`, `.mkv`… được tự cắt bỏ.
- Khung "Payload gửi lên DRES" hiển thị đúng JSON trước khi bấm `Nộp bài (Submit)`.
- Mỗi truy vấn **không được nộp trùng**.

Kết quả chấm hiện ngay bằng banner theo 4 trường hợp:

| Banner | Ý nghĩa |
| --- | --- |
| `CHÍNH XÁC` (CORRECT) | đúng, được tính điểm |
| `SAI` (WRONG) | sai, bị trừ điểm |
| `ĐANG THẨM ĐỊNH` (INDETERMINATE / UNDECIDABLE) | BGK kiểm tra thủ công |
| lỗi HTTP | 401 session hết hạn, 404 sai evaluation, 412 nộp trùng/hết giờ |

CLI:

```bash
uv run ir dres-status                        # user, evaluation, task đang chạy
uv run ir dres-submit video_0108 18500              # KIS
uv run ir dres-submit video_0108 24300 --kind qa --answer 42
uv run ir dres-submit video_0055 --kind trake --frames 140,395,820,1450
uv run ir dres-submit --kind raw --payload payload.json
uv run ir dres-submit video_0108 18500 --dry-run    # chỉ in payload, không nộp
```

API tương ứng:

- `GET /api/dres/status` — user + evaluation + task hiện tại.
- `POST /api/dres/submit` — body `{kind, video_id, ts_ms, answer, frame_ids, payload}`.

Cấu hình trong `config.yaml`:

```yaml
dres:
  base_url: https://aiclub.uit.edu.vn/dres
  session_id: null      # không đặt token trong file này (được git track)
  evaluation_id: null   # null = tự lấy evaluation đang ACTIVE
  timeout_sec: 15.0
```

Session id lấy theo thứ tự: env `DRES_SESSION_ID` → `dres.session_id` trong config →
file `state/dres_session` (gitignored). Cách dùng file:

```bash
printf 'your-session-id' > state/dres_session
chmod 600 state/dres_session
```

Kiểm tra và nộp bằng CLI:

```bash
uv run ir dres-status                        # user, evaluation, task đang chạy
uv run ir dres-submit L01_V001 12000 15000   # video_id start_ms end_ms
```

API tương ứng:

- `GET /api/dres/status` — user + evaluation + task hiện tại.
- `POST /api/dres/submit` — body `{video_id, start_ms, end_ms}`.

## Search

```bash
uv run ir search "a person speaking at a conference" -k 10
uv run uvicorn ir.api.main:app --reload
cd web && npm run dev
```

- `POST /api/search` — `{text, top_k}` → keyframe + shot interval + danh sách `frames` (keyframe + follow frames, mỗi frame có interval riêng) + `dres_payload`.
- `GET /api/keyframes/{path}` — ảnh keyframe.
- `GET /api/frames/{path}` — ảnh follow frame.
- `GET /api/videos/{id}/stream` — video gốc, hỗ trợ HTTP Range.
- Web UI: grid keyframe, click → player seek, dải thumbnail chọn frame đúng nhất, copy DRES payload theo frame được chọn.
- DRES: `GET /api/dres/status`, `POST /api/dres/submit` — xem [Chạy web UI](#chạy-web-ui).

Query tiếng Việt được dịch sang tiếng Anh bằng Gemini trước khi encode CLIP. Cấu hình trong
`config.yaml`:

```yaml
translate:
  enabled: true
  model: gemini-3.1-flash-lite
  api_key: null          # không đặt key trong file này (được git track)
  api_key_env: GEMINI_API_KEY
  base_url: https://generativelanguage.googleapis.com/v1beta
  timeout_sec: 15.0
```

API key lấy theo thứ tự: env `GEMINI_API_KEY` (hoặc `GOOGLE_API_KEY`) → `translate.api_key`
→ file `state/gemini_api_key` (gitignored):

```bash
printf 'your-gemini-api-key' > state/gemini_api_key
chmod 600 state/gemini_api_key
```

Nếu thiếu key hoặc Gemini lỗi, search dùng query gốc. Response có thêm `query` và
`translated_query`; CLI in bản dịch trước danh sách kết quả.

## Chạy keyframe

```bash
uv run ir index                    # resume: video đã có shot sẽ chạy keyframe + follow frames
uv run ir index --only keyframes   # chỉ chạy keyframe
uv run ir index --only follow      # chỉ extract follow frames (backfill, giữ nguyên keyframe/embedding)
uv run ir stats
```

Follow frames: quanh mỗi keyframe, extract thêm các frame **cả trước lẫn sau trong cùng shot** để chọn ra frame đúng nhất. dHash của keyframe được seed vào nhóm để frame follow đầu tiên không trùng ảnh chính. Cấu hình trong `config.yaml`:

```yaml
keyframe:
  follow:
    step_sec: 0.5       # khoảng cách giữa các frame
    max_frames: 8       # tối đa mỗi keyframe (chia đều hai phía)
    window_sec: 1.0     # độ dài interval quanh frame khi chọn
    short_side: 320     # cạnh ngắn của ảnh (keyframe chính vẫn 448)
    quality: 75         # quality của WebP/JPEG
    image_format: webp  # webp | jpeg
    bidirectional: true # lấy cả trước và sau keyframe
```

Ảnh lưu ở `state/follow_frames/<video_id>/g<generation>/<shot>_<kf>_<frame>.webp` (hoặc `.jpg` nếu `image_format: jpeg`), metadata ở bảng `follow_frames`. Follow frames **không** được embed — FAISS/index giữ nguyên keyframe, nên không cần chạy lại Kaggle.

Follow frames chỉ dùng để hiển thị/chọn frame trên UI nên được lưu nhỏ hơn keyframe: WebP 320px quality 75 giảm khoảng 4x dung lượng (≈79 KB → ≈20 KB mỗi ảnh). Chạy `uv run ir index --only follow --reindex` để sinh lại ảnh cũ theo cấu hình mới.

Lưu ý:

- Sampling mới (4s/segment, bỏ burst merge, follow hai chiều) cần chạy lại `uv run ir index --reindex` để áp dụng.
- Số keyframe tăng khoảng 40-50% so với cấu hình cũ; thời gian embed Kaggle tăng tương ứng.
- Artifacts hiện tại đã sinh bằng PySceneDetect; dùng `uv run ir index --reindex` nếu muốn tạo generation mới.
- Embedding lấy từ notebook Kaggle, import bằng `uv run ir import-shards <zip>`.
- `uv run ir export-keyframes` luôn ghi lại `artifacts/manifest.jsonl` từ DB trước khi zip.

## Kiểm tra

```bash
uv run pytest
uv run ruff check .
```

## Cấu trúc

`config.yaml` cấu hình pipeline; `src/ir/` gồm `config`, `types`, `store` (SQLite + FAISS), `search` (CLIP encoder + search service), `api` (FastAPI), `cli`; `web/` là Vite React UI; `scripts/kaggle_embed.ipynb` là notebook embed trên Kaggle; `scripts/kaggle_objects.ipynb` là notebook YOLO11 object tagging. `artifacts/` chỉ chứa keyframe + `manifest.jsonl` để upload Kaggle; `state/` chứa DB, follow frames, embeddings và FAISS index (cả hai đều gitignored).
