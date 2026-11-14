from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import faiss
import numpy as np
import pytest

from ir.config import AppConfig, EmbedConfig
from ir.index.boilerplate import compute_boilerplate
from ir.store.db import connect, init_db, insert_keyframe, upsert_video
from ir.types import Keyframe, Video


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        state_dir=tmp_path / "state",
        embed=EmbedConfig(model="test-model", dim=4),
    )


def _seed(cfg: AppConfig, count: int = 11) -> list[int]:
    init_db(cfg.db_path)
    uids: list[int] = []
    with closing(connect(cfg.db_path)) as conn:
        for index in range(count):
            upsert_video(
                conn,
                Video(
                    video_id=f"V{index:02d}",
                    path=f"/videos/V{index:02d}.mp4",
                    duration_ms=1000,
                ),
            )
        for index in range(count):
            uids.append(
                insert_keyframe(
                    conn,
                    Keyframe(
                        video_id=f"V{index:02d}",
                        shot_idx=0,
                        kf_idx=0,
                        ts_ms=index * 1000,
                        path=f"keyframes/V{index:02d}/g0/000000_000.jpg",
                    ),
                )
            )
    return uids


def _write_embeddings(
    directory: Path, vectors: np.ndarray, ids: np.ndarray, model: str
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    faiss.normalize_L2(vectors)
    np.save(directory / "embeddings.f16.npy", vectors.astype(np.float16))
    np.save(directory / "id_map.npy", ids.astype(np.int64))
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(directory / "faiss.index"))
    (directory / "manifest.json").write_text(
        json.dumps({"model": model, "count": len(ids), "dim": vectors.shape[1]}),
        encoding="utf-8",
    )


def test_compute_boilerplate_marks_frames_shared_across_videos(tmp_path) -> None:
    cfg = _config(tmp_path)
    uids = _seed(cfg)

    rng = np.random.default_rng(0)
    shared = np.tile(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), (10, 1))
    shared += rng.normal(0.0, 0.0001, shared.shape).astype(np.float32)
    vectors = np.vstack([shared, np.array([[0.0, 0.0, 1.0, 0.0]], dtype=np.float32)])
    _write_embeddings(cfg.embeddings_dir, vectors, np.asarray(uids), "test-model")

    report = compute_boilerplate(
        cfg, threshold=0.95, min_videos=10, neighbors=100, block=4
    )

    mask = np.load(cfg.boilerplate_mask_path)
    meta = json.loads(cfg.boilerplate_meta_path.read_text(encoding="utf-8"))

    assert (report.keyframes, report.boilerplate, report.videos) == (11, 10, 11)
    assert report.missing == 0
    assert mask.dtype == bool
    assert mask[:10].all()
    assert not mask[10]
    assert meta["boilerplate"] == 10
    assert meta["threshold"] == 0.95
    assert meta["min_videos"] == 10
    assert meta["profile"] == "clip"


def test_compute_boilerplate_requires_index(tmp_path) -> None:
    cfg = _config(tmp_path)

    with pytest.raises(FileNotFoundError):
        compute_boilerplate(cfg)
