from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import faiss
import numpy as np

from ..config import AppConfig
from ..store.db import connect, init_db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoilerplateReport:
    profile: str
    keyframes: int
    boilerplate: int
    videos: int
    missing: int
    mask_path: Path
    meta_path: Path
    elapsed_sec: float


def _video_array(cfg: AppConfig, id_map: np.ndarray) -> tuple[np.ndarray, int, int]:
    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        rows = conn.execute("SELECT kf_uid, video_id FROM keyframes").fetchall()
    mapping = {int(row["kf_uid"]): str(row["video_id"]) for row in rows}

    names: dict[str, int] = {}
    result = np.empty(len(id_map), dtype=np.int32)
    missing = 0
    for position, uid in enumerate(id_map):
        video_id = mapping.get(int(uid))
        if video_id is None:
            missing += 1
            video_id = f"__missing_{int(uid)}"
        result[position] = names.setdefault(video_id, len(names))
    return result, len(names), missing


def compute_boilerplate(
    cfg: AppConfig,
    profile: str | None = None,
    threshold: float | None = None,
    min_videos: int | None = None,
    neighbors: int | None = None,
    block: int | None = None,
) -> BoilerplateReport:
    spec = cfg.embed_profile(profile)
    directory = cfg.embeddings_dir_for(spec.name)
    index_path = directory / "faiss.index"
    id_map_path = directory / "id_map.npy"
    embeddings_path = directory / "embeddings.f16.npy"
    if not index_path.is_file() or not id_map_path.is_file():
        raise FileNotFoundError(f"Không thấy index cho model {spec.name!r}: {directory}")

    if threshold is None:
        threshold = cfg.boilerplate.thresholds.get(
            spec.name, cfg.boilerplate.threshold
        )
    min_videos = cfg.boilerplate.min_videos if min_videos is None else min_videos
    neighbors = cfg.boilerplate.neighbors if neighbors is None else neighbors
    block = cfg.boilerplate.block if block is None else block
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold phải trong (0, 1]")
    if min_videos < 2:
        raise ValueError("min_videos phải >= 2")
    if neighbors < min_videos:
        raise ValueError("neighbors phải >= min_videos")
    if block < 1:
        raise ValueError("block phải >= 1")

    started = time.perf_counter()
    index = faiss.read_index(str(index_path))
    id_map = np.load(id_map_path).astype(np.int64, copy=False)
    if id_map.ndim != 1:
        raise ValueError("id_map.npy phải là mảng 1 chiều")
    if index.ntotal != len(id_map):
        raise ValueError(f"faiss.ntotal={index.ntotal} != id_map={len(id_map)}")

    embeddings = None
    if embeddings_path.is_file():
        embeddings = np.load(embeddings_path, mmap_mode="r")
        if embeddings.shape != (len(id_map), index.d):
            raise ValueError(
                f"embeddings shape {embeddings.shape} != ({len(id_map)}, {index.d})"
            )

    video_array, videos, missing = _video_array(cfg, id_map)
    mask = np.zeros(len(id_map), dtype=bool)
    k = min(int(neighbors), index.ntotal)

    for start in range(0, len(id_map), block):
        end = min(len(id_map), start + block)
        if embeddings is not None:
            queries = np.asarray(embeddings[start:end], dtype=np.float32)
        else:
            queries = index.reconstruct_batch(np.arange(start, end)).astype(np.float32)
        faiss.normalize_L2(queries)
        sims, neighbor_idx = index.search(queries, k)
        close = sims > threshold
        neighbor_videos = video_array[neighbor_idx]
        for row in range(end - start):
            if not close[row].any():
                continue
            if np.unique(neighbor_videos[row][close[row]]).size >= min_videos:
                mask[start + row] = True
        logger.info("boilerplate %s: %d/%d", spec.name, end, len(id_map))

    mask_path = cfg.boilerplate_mask_path_for(spec.name)
    meta_path = cfg.boilerplate_meta_path_for(spec.name)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = mask_path.with_name(f"{mask_path.name}.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, mask)
    os.replace(temporary, mask_path)

    elapsed = time.perf_counter() - started
    meta = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "profile": spec.name,
        "model": spec.model,
        "dim": spec.dim,
        "count": int(len(id_map)),
        "id_map_sha256": hashlib.sha256(id_map.tobytes()).hexdigest(),
        "videos": videos,
        "missing": missing,
        "k": k,
        "threshold": threshold,
        "min_videos": min_videos,
        "block": block,
        "boilerplate": int(mask.sum()),
        "ratio": float(mask.mean()) if len(mask) else 0.0,
        "elapsed_sec": round(elapsed, 1),
        "source": "embeddings.f16.npy" if embeddings is not None else "faiss.reconstruct",
    }
    temporary_meta = meta_path.with_name(f"{meta_path.name}.tmp")
    temporary_meta.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary_meta, meta_path)

    return BoilerplateReport(
        profile=spec.name,
        keyframes=int(len(id_map)),
        boilerplate=int(mask.sum()),
        videos=videos,
        missing=missing,
        mask_path=mask_path,
        meta_path=meta_path,
        elapsed_sec=elapsed,
    )
