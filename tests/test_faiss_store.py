from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pytest

from ir.config import AppConfig
from ir.store.faiss_store import FaissStore, IndexUnavailableError


def _write_artifacts(root: Path, vectors: np.ndarray, ids: np.ndarray) -> AppConfig:
    root.mkdir(parents=True, exist_ok=True)
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    faiss.normalize_L2(vectors)

    np.save(root / "embeddings.f16.npy", vectors.astype(np.float16))
    np.save(root / "id_map.npy", ids.astype(np.int64))

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(root / "faiss.index"))

    (root / "manifest.json").write_text(
        json.dumps({"model": "test-model", "count": len(ids), "dim": vectors.shape[1]}),
        encoding="utf-8",
    )
    return AppConfig(artifacts_dir=root)


def test_load_and_search(tmp_path) -> None:
    vectors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.8, 0.6, 0.0]])
    cfg = _write_artifacts(tmp_path / "artifacts", vectors, np.array([10, 20, 30]))

    store = FaissStore.load(cfg)

    assert store.count == 3
    assert store.dim == 3
    assert store.model == "test-model"

    hits = store.search(np.array([0.0, 1.0, 0.0]), 2)
    assert hits[0][1] == 20
    assert hits[0][0] == pytest.approx(1.0)


def test_missing_artifacts_raise(tmp_path) -> None:
    with pytest.raises(IndexUnavailableError):
        FaissStore.load(AppConfig(artifacts_dir=tmp_path / "artifacts"))


def test_index_and_id_map_must_match(tmp_path) -> None:
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]])
    cfg = _write_artifacts(tmp_path / "artifacts", vectors, np.array([1, 2]))

    np.save(cfg.id_map_path, np.array([1], dtype=np.int64))

    with pytest.raises(IndexUnavailableError):
        FaissStore.load(cfg)
