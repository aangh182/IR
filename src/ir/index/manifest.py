from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..config import AppConfig


def write_keyframe_manifest(cfg: AppConfig, conn: sqlite3.Connection) -> Path:
    rows = conn.execute(
        """
        SELECT k.kf_uid, k.video_id, k.generation, k.shot_idx, k.kf_idx, k.ts_ms, k.path
        FROM keyframes k
        JOIN videos v
          ON v.video_id = k.video_id AND v.generation = k.generation
        ORDER BY k.video_id, k.kf_uid
        """
    ).fetchall()

    path = cfg.keyframes_manifest_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    {
                        "kf_uid": int(row["kf_uid"]),
                        "video_id": str(row["video_id"]),
                        "generation": int(row["generation"]),
                        "shot_idx": int(row["shot_idx"]),
                        "kf_idx": int(row["kf_idx"]),
                        "ts_ms": int(row["ts_ms"]),
                        "path": str(row["path"]),
                    },
                    ensure_ascii=False,
                )
            )
            handle.write("\n")
    os.replace(temporary, path)
    return path
