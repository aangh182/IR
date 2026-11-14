from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import faiss
import numpy as np

from ..config import AppConfig

REQUIRED_FILES = ("embeddings.f16.npy", "id_map.npy", "manifest.json")
BLOCK_SIZE = 50_000


@dataclass(frozen=True)
class MergeReport:
    videos: int
    keyframes: int
    output_dir: Path


def _sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_save(path: Path, array: np.ndarray) -> None:
    temporary = path.with_name(f"{path.stem}.tmp.npy")
    np.save(temporary, array)
    os.replace(temporary, path)


def merge_shards(
    cfg: AppConfig,
    shards_dir: Path | None = None,
    output_dir: Path | None = None,
    profile: str | None = None,
) -> MergeReport:
    spec = cfg.embed_profile(profile)
    root = Path(shards_dir) if shards_dir is not None else cfg.shards_dir_for(spec.name)
    if not root.is_dir():
        raise FileNotFoundError(f"Không thấy thư mục shards: {root}")

    shard_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if not shard_dirs:
        raise FileNotFoundError(f"Không có shard nào trong {root}")

    entries: list[tuple[str, np.ndarray, Path, dict]] = []
    for shard_dir in shard_dirs:
        missing = [name for name in REQUIRED_FILES if not (shard_dir / name).is_file()]
        if missing:
            raise ValueError(f"{shard_dir.name}: thiếu {', '.join(missing)}")

        manifest = json.loads((shard_dir / "manifest.json").read_text(encoding="utf-8"))
        ids = np.load(shard_dir / "id_map.npy")
        embeddings_path = shard_dir / "embeddings.f16.npy"
        embeddings = np.load(embeddings_path, mmap_mode="r")

        if ids.ndim != 1:
            raise ValueError(f"{shard_dir.name}: id_map phải là mảng 1 chiều")
        if embeddings.shape != (len(ids), spec.dim):
            raise ValueError(
                f"{shard_dir.name}: embeddings shape {embeddings.shape} "
                f"!= ({len(ids)}, {spec.dim})"
            )
        if int(manifest.get("count", -1)) != len(ids):
            raise ValueError(
                f"{shard_dir.name}: manifest.count {manifest.get('count')} != id_map {len(ids)}"
            )
        model = manifest.get("model")
        if model and model != spec.model:
            raise ValueError(
                f"{shard_dir.name}: model {model!r} != config {spec.model!r}"
            )
        del embeddings

        video_id = str(manifest.get("video_id") or shard_dir.name)
        entries.append((video_id, np.asarray(ids, dtype=np.int64), embeddings_path, manifest))

    all_ids = np.concatenate([entry[1] for entry in entries])
    if len(np.unique(all_ids)) != len(all_ids):
        raise ValueError("Có kf_uid trùng giữa các shard")

    order = np.argsort(all_ids, kind="stable")
    sorted_ids = all_ids[order].astype(np.int64)
    output = (
        Path(output_dir)
        if output_dir is not None
        else cfg.embeddings_dir_for(spec.name)
    )
    output.mkdir(parents=True, exist_ok=True)

    embeddings_path = output / "embeddings.f16.npy"
    temporary_embeddings = output / "embeddings.tmp.npy"
    memory_map = np.lib.format.open_memmap(
        str(temporary_embeddings),
        mode="w+",
        dtype=np.float16,
        shape=(len(sorted_ids), spec.dim),
    )
    for _, ids, shard_embeddings, _ in entries:
        positions = np.searchsorted(sorted_ids, ids)
        if not np.array_equal(sorted_ids[positions], ids):
            raise ValueError("id_map không khớp sau khi sort")
        memory_map[positions] = np.load(shard_embeddings, mmap_mode="r")
    memory_map.flush()
    del memory_map
    os.replace(temporary_embeddings, embeddings_path)
    _atomic_save(output / "id_map.npy", sorted_ids)

    index = faiss.IndexFlatIP(spec.dim)
    memory_map = np.lib.format.open_memmap(str(embeddings_path), mode="r")
    for start in range(0, len(sorted_ids), BLOCK_SIZE):
        block = np.asarray(memory_map[start : start + BLOCK_SIZE], dtype=np.float32)
        faiss.normalize_L2(block)
        index.add(block)
    del memory_map

    if index.ntotal != len(sorted_ids):
        raise RuntimeError(f"FAISS ntotal {index.ntotal} != keyframes {len(sorted_ids)}")

    temporary_index = output / "faiss.tmp.index"
    faiss.write_index(index, str(temporary_index))
    os.replace(temporary_index, output / "faiss.index")

    manifest = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model": spec.model,
        "dim": spec.dim,
        "count": int(len(sorted_ids)),
        "dtype": "float16",
        "normalized": "l2",
        "faiss": {"type": "IndexFlatIP", "ntotal": int(index.ntotal)},
        "order": "kf_uid",
        "source": {"shards": str(root)},
        "shards": [
            {"video_id": video_id, "count": int(len(ids)), "path": str(path)}
            for video_id, ids, path, _ in entries
        ],
        "files": {
            "embeddings": "embeddings.f16.npy",
            "faiss": "faiss.index",
            "id_map": "id_map.npy",
        },
        "checksums": {
            "embeddings_sha256": _sha256(embeddings_path),
            "faiss_sha256": _sha256(output / "faiss.index"),
            "id_map_sha256": _sha256(output / "id_map.npy"),
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return MergeReport(
        videos=len(entries),
        keyframes=int(len(sorted_ids)),
        output_dir=output,
    )
