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
  embed/
    shards/<video_id>/...
    embeddings.f16.npy
    id_map.npy
    faiss.index
    manifest.json
```

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

Hiện search nhận query tiếng Anh; lớp dịch vi→en chưa thêm.

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

`config.yaml` cấu hình pipeline; `src/ir/` gồm `config`, `types`, `store` (SQLite + FAISS), `search` (CLIP encoder + search service), `api` (FastAPI), `cli`; `web/` là Vite React UI; `scripts/kaggle_embed.ipynb` là notebook embed trên Kaggle. `artifacts/` chỉ chứa keyframe + `manifest.jsonl` để upload Kaggle; `state/` chứa DB, follow frames, embeddings và FAISS index (cả hai đều gitignored).
