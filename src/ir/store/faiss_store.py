from __future__ import annotations

import json
from dataclasses import dataclass

import faiss
import numpy as np

from ..config import AppConfig


class IndexUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaissStore:
    index: faiss.Index
    id_map: np.ndarray
    dim: int
    model: str | None = None

    @property
    def count(self) -> int:
        return len(self.id_map)

    @classmethod
    def load(cls, cfg: AppConfig) -> FaissStore:
        required = {"faiss.index": cfg.faiss_path, "id_map.npy": cfg.id_map_path}
        missing = [f"{name} ({path})" for name, path in required.items() if not path.is_file()]
        if missing:
            raise IndexUnavailableError(
                "Chưa có embedding artifacts: " + ", ".join(missing)
            )

        index = faiss.read_index(str(cfg.faiss_path))
        id_map = np.load(cfg.id_map_path)
        if id_map.ndim != 1:
            raise IndexUnavailableError("id_map.npy phải là mảng 1 chiều")
        if index.ntotal != len(id_map):
            raise IndexUnavailableError(
                f"faiss.ntotal={index.ntotal} != id_map={len(id_map)}"
            )

        if cfg.embeddings_path.is_file():
            embeddings = np.load(cfg.embeddings_path, mmap_mode="r")
            expected = (len(id_map), index.d)
            if embeddings.shape != expected:
                raise IndexUnavailableError(
                    f"embeddings shape {embeddings.shape} != {expected}"
                )
            del embeddings

        model: str | None = None
        if cfg.manifest_path.is_file():
            manifest = json.loads(cfg.manifest_path.read_text(encoding="utf-8"))
            model = manifest.get("model")
            count = manifest.get("count")
            if count is not None and int(count) != len(id_map):
                raise IndexUnavailableError(
                    f"manifest.count={count} != id_map={len(id_map)}"
                )

        return cls(
            index=index,
            id_map=np.asarray(id_map, dtype=np.int64),
            dim=int(index.d),
            model=model,
        )

    def search(self, vector: np.ndarray, k: int) -> list[tuple[float, int]]:
        if k <= 0 or self.index.ntotal == 0:
            return []

        query = np.ascontiguousarray(vector, dtype=np.float32).reshape(1, -1)
        if query.shape[1] != self.dim:
            raise ValueError(f"query dim {query.shape[1]} != index dim {self.dim}")
        faiss.normalize_L2(query)

        scores, indices = self.index.search(query, min(k, self.index.ntotal))
        return [
            (float(score), int(self.id_map[int(index)]))
            for score, index in zip(scores[0], indices[0], strict=False)
            if index >= 0
        ]
