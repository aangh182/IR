from __future__ import annotations

import os
import shutil
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from .config import AppConfig
from .index.manifest import write_keyframe_manifest
from .index.merge import MergeReport, merge_shards
from .store.db import connect, init_db

BUNDLE_README = """AIC2024 KIS - keyframe bundle for Kaggle
Contents:
  keyframes/<video_id>/g<generation>/<shot>_<keyframe>.jpg
  manifest.jsonl   (kf_uid, video_id, generation, shot_idx, kf_idx, ts_ms, path)
Upload this zip as a Kaggle Dataset, run scripts/kaggle_embed.ipynb, then download
the shard zip and import it locally with:
  uv run ir import-shards artifacts_embed_shards.zip
"""


def export_keyframes(cfg: AppConfig, zip_path: Path) -> tuple[Path, int]:
    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        manifest = write_keyframe_manifest(cfg, conn)

    if not cfg.keyframes_dir.is_dir():
        raise FileNotFoundError(f"Không thấy keyframes: {cfg.keyframes_dir}")

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = zip_path.with_suffix(zip_path.suffix + ".tmp")
    files = 0
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(cfg.keyframes_dir.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, path.relative_to(cfg.artifacts_dir).as_posix())
            files += 1
        archive.write(manifest, "manifest.jsonl")
        archive.writestr("README.txt", BUNDLE_README)
    os.replace(temporary, zip_path)
    return zip_path, files


def _extract_shards(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    video_dirs = {
        destination / "shards" / parts[1]
        for member in archive.infolist()
        if (parts := PurePosixPath(member.filename).parts)
        and parts[0] == "shards"
        and len(parts) > 1
    }
    for video_dir in video_dirs:
        if video_dir.is_dir():
            shutil.rmtree(video_dir)

    for member in archive.infolist():
        if member.is_dir():
            continue
        parts = PurePosixPath(member.filename).parts
        if not parts or parts[0] != "shards":
            continue
        target = destination.joinpath(*parts)
        if not target.resolve().is_relative_to(root):
            raise ValueError(f"zip chứa đường dẫn không hợp lệ: {member.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def _copy_shards(source: Path, destination: Path) -> None:
    root = source / "shards" if (source / "shards").is_dir() else source
    shards_root = destination / "shards"
    shards_root.mkdir(parents=True, exist_ok=True)
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        target = shards_root / child.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(child, target)


def import_shards(cfg: AppConfig, source: Path, run_merge: bool = True) -> MergeReport | None:
    destination = cfg.embeddings_dir
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        _copy_shards(source, destination)
    else:
        with zipfile.ZipFile(source) as archive:
            _extract_shards(archive, destination)
    if not cfg.shards_dir.is_dir():
        raise FileNotFoundError(f"Không thấy shards sau khi giải nén: {cfg.shards_dir}")
    if not run_merge:
        return None
    return merge_shards(cfg)
