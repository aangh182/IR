from __future__ import annotations

import sqlite3
from pathlib import Path

from ..types import Keyframe, Shot, Video

SCHEMA_VERSION = "2"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    fps REAL,
    width INTEGER,
    height INTEGER,
    has_audio INTEGER NOT NULL DEFAULT 0,
    generation INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shots (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL DEFAULT 0,
    shot_idx INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    scene_score REAL,
    PRIMARY KEY (video_id, generation, shot_idx)
);

CREATE TABLE IF NOT EXISTS keyframes (
    kf_uid INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL DEFAULT 0,
    shot_idx INTEGER NOT NULL,
    kf_idx INTEGER NOT NULL,
    ts_ms INTEGER NOT NULL,
    path TEXT NOT NULL,
    ocr_text TEXT NOT NULL DEFAULT '',
    objects TEXT NOT NULL DEFAULT '',
    obj_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (video_id, generation, shot_idx, kf_idx)
);

CREATE INDEX IF NOT EXISTS idx_keyframes_video_ts
    ON keyframes (video_id, ts_ms);

CREATE TABLE IF NOT EXISTS asr_segments (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL DEFAULT 0,
    seg_idx INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (video_id, generation, seg_idx)
);

CREATE TABLE IF NOT EXISTS index_status (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL DEFAULT 0,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (video_id, generation, step)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | Path) -> Path:
    path = Path(db_path)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        conn.commit()
    finally:
        conn.close()
    return path


def upsert_video(conn: sqlite3.Connection, video: Video) -> None:
    conn.execute(
        """
        INSERT INTO videos (video_id, path, duration_ms, fps, width, height, has_audio)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            path = excluded.path,
            duration_ms = excluded.duration_ms,
            fps = excluded.fps,
            width = excluded.width,
            height = excluded.height,
            has_audio = excluded.has_audio
        """,
        (
            video.video_id,
            video.path,
            video.duration_ms,
            video.fps,
            video.width,
            video.height,
            int(video.has_audio),
        ),
    )
    conn.commit()


def bump_generation(conn: sqlite3.Connection, video_id: str) -> int:
    conn.execute(
        "UPDATE videos SET generation = generation + 1 WHERE video_id = ?", (video_id,)
    )
    row = conn.execute("SELECT generation FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown video_id: {video_id}")
    conn.commit()
    return int(row["generation"])


def compact_video(conn: sqlite3.Connection, video_id: str) -> dict[str, int]:
    row = conn.execute("SELECT generation FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown video_id: {video_id}")
    generation = int(row["generation"])
    deleted: dict[str, int] = {}
    for table in ("keyframes", "shots", "asr_segments"):
        cur = conn.execute(
            f"DELETE FROM {table} WHERE video_id = ? AND generation < ?",
            (video_id, generation),
        )
        deleted[table] = cur.rowcount
    conn.commit()
    return deleted


def current_generation(conn: sqlite3.Connection, video_id: str) -> int:
    row = conn.execute("SELECT generation FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown video_id: {video_id}")
    return int(row["generation"])


def upsert_shot(conn: sqlite3.Connection, shot: Shot, generation: int) -> None:
    conn.execute(
        """
        INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms, scene_score)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id, generation, shot_idx) DO UPDATE SET
            start_ms = excluded.start_ms,
            end_ms = excluded.end_ms,
            scene_score = excluded.scene_score
        """,
        (
            shot.video_id,
            generation,
            shot.shot_idx,
            shot.start_ms,
            shot.end_ms,
            shot.scene_score,
        ),
    )
    conn.commit()


def load_shots(conn: sqlite3.Connection, video_id: str, generation: int) -> list[Shot]:
    rows = conn.execute(
        """
        SELECT video_id, shot_idx, start_ms, end_ms, scene_score
        FROM shots WHERE video_id = ? AND generation = ?
        ORDER BY shot_idx
        """,
        (video_id, generation),
    ).fetchall()
    return [
        Shot(
            video_id=row["video_id"],
            shot_idx=int(row["shot_idx"]),
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            scene_score=row["scene_score"],
        )
        for row in rows
    ]


def delete_shots(conn: sqlite3.Connection, video_id: str, generation: int) -> int:
    cur = conn.execute(
        "DELETE FROM shots WHERE video_id = ? AND generation = ?", (video_id, generation)
    )
    conn.commit()
    return cur.rowcount


def insert_keyframe(conn: sqlite3.Connection, keyframe: Keyframe) -> int:
    cur = conn.execute(
        """
        INSERT INTO keyframes
            (video_id, generation, shot_idx, kf_idx, ts_ms, path, ocr_text, objects, obj_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            keyframe.video_id,
            keyframe.generation,
            keyframe.shot_idx,
            keyframe.kf_idx,
            keyframe.ts_ms,
            keyframe.path,
            keyframe.ocr_text,
            ",".join(keyframe.objects),
            len(keyframe.objects),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def delete_keyframes(conn: sqlite3.Connection, video_id: str, generation: int) -> int:
    cur = conn.execute(
        "DELETE FROM keyframes WHERE video_id = ? AND generation = ?", (video_id, generation)
    )
    conn.commit()
    return cur.rowcount


def set_index_status(
    conn: sqlite3.Connection,
    video_id: str,
    generation: int,
    step: str,
    status: str,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO index_status (video_id, generation, step, status, error, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(video_id, generation, step) DO UPDATE SET
            status = excluded.status,
            error = excluded.error,
            updated_at = excluded.updated_at
        """,
        (video_id, generation, step, status, error),
    )
    conn.commit()


def get_index_status(
    conn: sqlite3.Connection, video_id: str, generation: int, step: str
) -> str | None:
    row = conn.execute(
        """
        SELECT status FROM index_status
        WHERE video_id = ? AND generation = ? AND step = ?
        """,
        (video_id, generation, step),
    ).fetchone()
    return str(row["status"]) if row is not None else None


def step_done(conn: sqlite3.Connection, video_id: str, generation: int, step: str) -> bool:
    return get_index_status(conn, video_id, generation, step) == "done"


def get_stats(conn: sqlite3.Connection) -> dict[str, int]:
    def active_count(table: str) -> int:
        return int(
            conn.execute(
                f"""
                SELECT COUNT(*) FROM {table} t
                JOIN videos v ON v.video_id = t.video_id AND t.generation = v.generation
                """
            ).fetchone()[0]
        )

    return {
        "videos": int(conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]),
        "shots": active_count("shots"),
        "keyframes": active_count("keyframes"),
        "asr_segments": active_count("asr_segments"),
    }
