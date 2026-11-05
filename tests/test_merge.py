from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ir.config import AppConfig, EmbedConfig
from ir.index.merge import merge_shards
from ir.store.faiss_store import FaissStore


def _write_shard(
    directory: Path,
    video_id: str,
    ids: list[int],
    vectors: np.ndarray,
    model: str = "test-model",
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    np.save(directory / "embeddings.f16.npy", vectors.astype(np.float16))
    np.save(directory / "id_map.npy", np.asarray(ids, dtype=np.int64))
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "video_id": video_id,
                "model": model,
                "dim": vectors.shape[1],
                "count": len(ids),
            }
        ),
        encoding="utf-8",
    )


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        embed=EmbedConfig(model="test-model", dim=4),
    )


def test_merge_shards_builds_combined_index(tmp_path) -> None:
    cfg = _config(tmp_path)
    shards = cfg.artifacts_dir / "artifacts_embed" / "shards"
    _write_shard(
        shards / "V1",
        "V1",
        [10, 20],
        np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]),
    )
    _write_shard(
        shards / "V2",
        "V2",
        [5, 30],
        np.array([[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]),
    )

    report = merge_shards(cfg, shards_dir=shards)

    assert (report.videos, report.keyframes) == (2, 4)
    assert report.output_dir == cfg.artifacts_dir / "artifacts_embed"

    store = FaissStore.load(cfg)
    assert store.count == 4
    assert np.load(cfg.id_map_path).tolist() == [5, 10, 20, 30]

    hits = store.search(np.array([0.0, 0.0, 1.0, 0.0]), 1)
    assert hits[0][1] == 5


def test_merge_rejects_duplicate_ids(tmp_path) -> None:
    cfg = _config(tmp_path)
    shards = tmp_path / "shards"
    vectors = np.eye(4, dtype=np.float32)
    _write_shard(shards / "V1", "V1", [10], vectors[[0]])
    _write_shard(shards / "V2", "V2", [10], vectors[[1]])

    with pytest.raises(ValueError):
        merge_shards(cfg, shards_dir=shards, output_dir=tmp_path / "out")


def test_merge_rejects_model_mismatch(tmp_path) -> None:
    cfg = _config(tmp_path)
    shards = tmp_path / "shards"
    _write_shard(
        shards / "V1",
        "V1",
        [10],
        np.array([[1.0, 0.0, 0.0, 0.0]]),
        model="other-model",
    )

    with pytest.raises(ValueError):
        merge_shards(cfg, shards_dir=shards, output_dir=tmp_path / "out")
