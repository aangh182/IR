# AIC2024 Known-Item Search

Hệ thống tìm kiếm video theo mô tả (Textual KIS), ảnh vẽ/upload (Video KIS) và Q&A cho vòng chung kết AIC2024.

## Trạng thái

- [x] Phase 0: nền tảng, config, SQLite schema, CLI, FastAPI, web scaffold
- [x] Phase 1: shot detection + keyframe extraction (PyAV, lọc frame rác)
  - [x] Shot detection: PySceneDetect `ContentDetector` (đã thay TransNetV2)
  - [x] Gộp burst card/transition/cảnh rung thành một shot
  - [x] Bỏ TransNetV2, CLI/config song song và notebook Colab/Kaggle
  - [ ] Chạy keyframe trên corpus thật — code sẵn sàng, xem lệnh bên dưới
- [ ] Phase 2: CLIP embedding + FAISS + search text
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

## Chạy keyframe

```bash
uv run ir index                    # resume: video đã có shot sẽ chạy keyframe
uv run ir index --only keyframes   # chỉ chạy keyframe
uv run ir stats
```

Lưu ý:

- `artifacts/` đang chứa kết quả cũ của TransNetV2. Dùng `uv run ir index --reindex`
  nếu muốn sinh lại toàn bộ shot + keyframe bằng PySceneDetect.
- `artifacts_pyscene/` là output so sánh cũ, không còn được pipeline dùng, có thể xóa.

## Kiểm tra

```bash
uv run pytest
uv run ruff check .
```

## Cấu trúc

`config.yaml` cấu hình pipeline; `src/ir/` gồm `config`, `types`, `store` (SQLite), `api` (FastAPI), `cli`; `web/` là Vite React UI; `artifacts/` chứa DB, embeddings, FAISS index và keyframe (gitignored).
