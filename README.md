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
uv run ir stats
```

Shot detection dùng PySceneDetect `ContentDetector`. Trong `config.yaml`:

- `shot.pyscenedetect_threshold`: ngưỡng cắt cảnh (mặc định 27.0).
- `shot.pyscenedetect_burst_merge_sec`: gộp các cụm ≥2 shot ngắn liên tiếp (card
  chuyển cảnh, transition, cảnh rung) thành một shot, giữ nguyên shot ngắn đơn lẻ.
  Đặt `0` để tắt.
- `shot.min_shot_sec`: thời lượng shot tối thiểu.

## Embedding (Kaggle)

`scripts/kaggle_embed.ipynb` là notebook self-contained, xuất **mỗi video một shard** để chạy Kaggle theo nhiều batch.

1. Upload `artifacts/` (`metadata.sqlite` + `keyframes/`) thành Kaggle Dataset; bật GPU + Internet.
2. Chọn batch bằng env:
   - mặc định: tất cả video;
   - `EMBED_VIDEO_OFFSET` + `EMBED_VIDEO_LIMIT` (ví dụ 0/100, 100/100, ...);
   - hoặc `EMBED_VIDEO_IDS=L01_V001,L01_V002`.
3. Tải `artifacts_embed_shards.zip`, giải nén vào `artifacts/artifacts_embed/` để có `artifacts/artifacts_embed/shards/<video_id>/`.
4. Merge ở local:

```bash
uv run ir merge
uv run ir merge --shards artifacts/artifacts_embed/shards --output artifacts/artifacts_embed
```

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

Follow frames: sau mỗi keyframe, extract thêm các frame kế tiếp **trong cùng shot** để chọn ra frame đúng nhất. Cấu hình trong `config.yaml`:

```yaml
keyframe:
  follow:
    step_sec: 0.5     # khoảng cách giữa các frame
    max_frames: 8     # tối đa mỗi keyframe
    window_sec: 1.0   # độ dài interval quanh frame khi chọn
```

Ảnh lưu ở `artifacts/follow_frames/<video_id>/g<generation>/<shot>_<kf>_<frame>.jpg`, metadata ở bảng `follow_frames`. Follow frames **không** được embed — FAISS/index giữ nguyên keyframe, nên không cần chạy lại Kaggle.

Lưu ý:

- Artifacts hiện tại đã sinh bằng PySceneDetect; dùng `uv run ir index --reindex` nếu muốn tạo generation mới.
- Embedding lấy từ notebook Kaggle, giải nén vào `artifacts/` hoặc `artifacts/artifacts_embed/`.

## Kiểm tra

```bash
uv run pytest
uv run ruff check .
```

## Cấu trúc

`config.yaml` cấu hình pipeline; `src/ir/` gồm `config`, `types`, `store` (SQLite + FAISS), `search` (CLIP encoder + search service), `api` (FastAPI), `cli`; `web/` là Vite React UI; `scripts/kaggle_embed.ipynb` là notebook embed trên Kaggle; `artifacts/` chứa DB, embeddings, FAISS index và keyframe (gitignored).
