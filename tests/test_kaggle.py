from __future__ import annotations

import json
import zipfile
from contextlib import closing

import numpy as np

from ir.config import AppConfig, EmbedConfig
from ir.kaggle import export_keyframes, import_shards
from ir.store.db import connect, init_db, insert_keyframe, upsert_video
from ir.types import Keyframe, Video


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        artifacts_dir=tmp_path / "artifacts",
        state_dir=tmp_path / "state",
        embed=EmbedConfig(model="test-model", dim=4),
    )


def _seed_keyframe(cfg: AppConfig) -> int:
    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        upsert_video(conn, Video(video_id="V1", path="/videos/V1.mp4", duration_ms=5000))
        uid = insert_keyframe(
            conn,
            Keyframe(
                video_id="V1",
                shot_idx=0,
                kf_idx=0,
                ts_ms=1000,
                path="keyframes/V1/g0/000000_000.jpg",
            ),
        )
    image = cfg.keyframes_dir / "V1" / "g0" / "000000_000.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"jpeg-bytes")
    (cfg.artifacts_dir / "stray.txt").write_text("not a keyframe", encoding="utf-8")
    return uid


def _write_shard_zip(cfg: AppConfig, path, uid: int) -> None:
    shard = path.parent / "shards" / "V1"
    shard.mkdir(parents=True)
    vectors = np.eye(cfg.embed.dim, dtype=np.float16)[:1]
    np.save(shard / "embeddings.f16.npy", vectors)
    np.save(shard / "id_map.npy", np.asarray([uid], dtype=np.int64))
    (shard / "manifest.json").write_text(
        json.dumps(
            {
                "video_id": "V1",
                "model": cfg.embed.model,
                "dim": cfg.embed.dim,
                "count": 1,
            }
        ),
        encoding="utf-8",
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name in ("embeddings.f16.npy", "id_map.npy", "manifest.json"):
            archive.write(shard / name, f"shards/V1/{name}")


def test_export_bundles_only_keyframes_and_manifest(tmp_path) -> None:
    cfg = _config(tmp_path)
    uid = _seed_keyframe(cfg)

    path, files = export_keyframes(cfg, tmp_path / "bundle.zip")

    assert files == 1
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        manifest = [
            json.loads(line)
            for line in archive.read("manifest.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]

    assert names == {"keyframes/V1/g0/000000_000.jpg", "manifest.jsonl", "README.txt"}
    assert manifest == [
        {
            "kf_uid": uid,
            "video_id": "V1",
            "generation": 0,
            "shot_idx": 0,
            "kf_idx": 0,
            "ts_ms": 1000,
            "path": "keyframes/V1/g0/000000_000.jpg",
        }
    ]


def test_import_shards_extracts_and_merges(tmp_path) -> None:
    cfg = _config(tmp_path)
    uid = _seed_keyframe(cfg)
    archive = tmp_path / "shards.zip"
    _write_shard_zip(cfg, archive, uid)

    report = import_shards(cfg, archive)

    assert report is not None
    assert (report.videos, report.keyframes) == (1, 1)
    assert report.output_dir == cfg.embeddings_dir
    assert (cfg.shards_dir / "V1" / "manifest.json").is_file()
    assert cfg.faiss_path.is_file()
    assert np.load(cfg.id_map_path).tolist() == [uid]
