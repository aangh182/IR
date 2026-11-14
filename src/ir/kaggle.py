from __future__ import annotations

import json
import os
import shutil
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import AppConfig
from .index.manifest import write_keyframe_manifest
from .index.merge import MergeReport, merge_shards
from .store.db import connect, init_db, set_keyframe_objects

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


@dataclass(frozen=True)
class ObjectImportReport:
    videos: int
    keyframes: int
    labels: int
    missing: int


def _read_object_counts(record: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    raw_counts = record.get("counts")
    if isinstance(raw_counts, dict):
        for label, value in raw_counts.items():
            name = str(label).strip().lower()
            if name:
                counts[name] = max(1, int(value))
    for label in record.get("objects") or []:
        name = str(label).strip().lower()
        if name and name not in counts:
            counts[name] = 1
    return counts


def _existing_uids(conn, uids: list[int]) -> set[int]:
    found: set[int] = set()
    for start in range(0, len(uids), 500):
        chunk = uids[start : start + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT kf_uid FROM keyframes WHERE kf_uid IN ({placeholders})", chunk
        ).fetchall()
        found.update(int(row["kf_uid"]) for row in rows)
    return found


def import_objects(cfg: AppConfig, source: Path) -> ObjectImportReport:
    init_db(cfg.db_path)
    destination = cfg.objects_dir
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        _copy_shards(source, destination)
    else:
        with zipfile.ZipFile(source) as archive:
            _extract_shards(archive, destination)

    root = cfg.objects_shards_dir
    if not root.is_dir():
        raise FileNotFoundError(f"Không thấy object shards sau khi giải nén: {root}")

    videos = 0
    keyframes = 0
    missing = 0
    labels: set[str] = set()

    with closing(connect(cfg.db_path)) as conn:
        for shard_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            objects_path = shard_dir / "objects.jsonl"
            if not objects_path.is_file():
                continue
            records = []
            for line in objects_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                counts = _read_object_counts(record)
                records.append((int(record["kf_uid"]), counts))

            if not records:
                videos += 1
                continue

            existing = _existing_uids(conn, [uid for uid, _ in records])
            for kf_uid, counts in records:
                if kf_uid not in existing:
                    missing += 1
                    continue
                set_keyframe_objects(conn, kf_uid, counts)
                keyframes += 1
                labels.update(counts)
            videos += 1
            conn.commit()

    return ObjectImportReport(
        videos=videos,
        keyframes=keyframes,
        labels=len(labels),
        missing=missing,
    )


def import_shards(
    cfg: AppConfig,
    source: Path,
    run_merge: bool = True,
    profile: str | None = None,
) -> MergeReport | None:
    spec = cfg.embed_profile(profile)
    destination = cfg.embeddings_dir_for(spec.name)
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        _copy_shards(source, destination)
    else:
        with zipfile.ZipFile(source) as archive:
            _extract_shards(archive, destination)
    shards_dir = cfg.shards_dir_for(spec.name)
    if not shards_dir.is_dir():
        raise FileNotFoundError(f"Không thấy shards sau khi giải nén: {shards_dir}")
    if not run_merge:
        return None
    return merge_shards(cfg, profile=spec.name)
