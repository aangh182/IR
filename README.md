# AIC2024 Known-Item Search

Hệ thống tìm kiếm video theo mô tả (Textual KIS), ảnh vẽ/upload (Video KIS) và Q&A cho vòng chung kết AIC2024.

## Trạng thái

- [x] Phase 0: nền tảng, config, SQLite schema, CLI, FastAPI, web scaffold
- [x] Phase 1: TransNetV2 shot detection + keyframe extraction (PyAV, lọc frame rác)
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
uv sync --group ml --group serve
uv run ir init
uv run uvicorn ir.api.main:app --reload
```

Web:

```bash
cd web
npm install
npm run dev
```

## Index trên Colab/Kaggle (GPU)

Trên Colab, cài vào system Python để dùng torch CUDA có sẵn (không tạo venv 3.11 riêng):

```bash
pip install -q uv
uv pip install --system -e .
uv pip install --system --group ml --group index
ir index --corpus /content/drive/MyDrive/aic2024/videos
```

Trên Kaggle: copy repo sang `/kaggle/working/IR` (vì `/kaggle/input` read-only), `%cd` vào đó, corpus ở `/kaggle/input/...`, dùng cùng hai lệnh `uv pip install --system` như trên.

Với corpus lớn (100GB+): mở `scripts/kaggle_index.ipynb`. Notebook quét tất cả dataset batch đang attach, chia shard, chạy theo deadline 11h và restore artifact từ notebook version trước để resume. Nếu upload bị giới hạn, chỉ cần attach thêm batch; notebook tự gom lại.

Hoặc mở `scripts/colab_index.ipynb` (có cell restore artifact để resume). Artifact nằm trong `artifacts/` (metadata.sqlite, keyframes/).

## Index

```bash
uv run ir index --limit 3          # thử 3 video đầu
uv run ir index                    # toàn bộ corpus trong config
uv run ir index --only shots       # chỉ detect shot
uv run ir index --reindex          # tạo generation mới rồi compact bản cũ
uv run ir stats
```

## Kiểm tra

```bash
uv run pytest
uv run ruff check .
```

## Cấu trúc

`config.yaml` cấu hình pipeline; `src/ir/` gồm `config`, `types`, `store` (SQLite), `api` (FastAPI), `cli`; `web/` là Vite React UI; `artifacts/` chứa DB, embeddings, FAISS index và keyframe (gitignored).
