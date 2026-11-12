from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from .config import AppConfig
from .index.manifest import write_keyframe_manifest
from .store.db import connect, init_db


def _checkpoint(path: Path) -> None:
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def _merge_move(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in list(source.iterdir()):
        destination = target / child.name
        if child.is_dir():
            if destination.is_dir():
                _merge_move(child, destination)
                child.rmdir()
            else:
                if destination.exists():
                    destination.unlink()
                shutil.move(str(child), str(destination))
        else:
            if destination.exists():
                destination.unlink()
            shutil.move(str(child), str(destination))
    source.rmdir()


def migrate_layout(cfg: AppConfig) -> list[str]:
    cfg.state_root.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []

    source_db = cfg.artifacts_dir / "metadata.sqlite"
    if source_db.is_file() and source_db.resolve() != cfg.db_path.resolve():
        _checkpoint(source_db)
        for suffix in ("", "-wal", "-shm"):
            source = Path(f"{source_db}{suffix}")
            if not source.is_file():
                continue
            destination = Path(f"{cfg.db_path}{suffix}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.unlink()
            shutil.move(str(source), str(destination))
        messages.append(f"database -> {cfg.db_path}")

    for source, target, label in (
        (cfg.artifacts_dir / "follow_frames", cfg.follow_frames_dir, "follow_frames"),
        (cfg.artifacts_dir / "artifacts_embed", cfg.embeddings_dir, "embeddings"),
        (cfg.artifacts_dir / "shards", cfg.embeddings_dir / "shards", "shards"),
    ):
        if not source.is_dir() or source.resolve() == target.resolve():
            continue
        _merge_move(source, target)
        messages.append(f"{label} -> {target}")

    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        manifest = write_keyframe_manifest(cfg, conn)
    messages.append(f"keyframe manifest -> {manifest}")
    return messages
