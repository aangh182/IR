from __future__ import annotations

import logging
import shutil
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from ..config import AppConfig
from ..ingest.follow import extract_follow_frames
from ..ingest.keyframes import extract_keyframes
from ..ingest.scan import scan_corpus
from ..ingest.shots import detect_shots
from ..store.db import (
    bump_generation,
    compact_video,
    connect,
    current_generation,
    delete_follow_frames,
    delete_keyframes,
    delete_shots,
    init_db,
    insert_follow_frame,
    insert_keyframe,
    load_keyframes,
    load_shots,
    set_index_status,
    step_done,
    upsert_shot,
    upsert_video,
)
from ..types import Shot, Video

logger = logging.getLogger(__name__)


@dataclass
class BuildReport:
    videos: int = 0
    shots: int = 0
    keyframes: int = 0
    follow_frames: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def build(
    cfg: AppConfig,
    corpus_dir: str | Path | None = None,
    limit: int | None = None,
    steps: list[str] | None = None,
    reindex: bool = False,
) -> BuildReport:
    steps = list(steps or ["shots", "keyframes", "follow"])
    unknown = set(steps) - {"shots", "keyframes", "follow"}
    if unknown:
        raise ValueError(f"unknown steps: {sorted(unknown)}")

    videos = scan_corpus(corpus_dir or cfg.corpus_dir)
    if limit is not None:
        videos = videos[:limit]

    report = BuildReport()
    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        for video in videos:
            report.videos += 1
            try:
                _process_video(conn, cfg, video, steps, reindex, report)
            except Exception as exc:
                report.failed += 1
                report.errors.append(f"{video.video_id}: {exc}")
                logger.exception("failed to index %s", video.video_id)
    return report


def _process_video(
    conn,
    cfg: AppConfig,
    video: Video,
    steps: list[str],
    reindex: bool,
    report: BuildReport,
) -> None:
    upsert_video(conn, video)
    generation = (
        bump_generation(conn, video.video_id)
        if reindex
        else current_generation(conn, video.video_id)
    )
    logger.info(
        "processing %s (%d ms, generation %d)",
        video.video_id,
        video.duration_ms,
        generation,
    )
    did_work = False
    shots: list[Shot] | None = None

    if "shots" in steps and not step_done(conn, video.video_id, generation, "shots"):
        set_index_status(conn, video.video_id, generation, "shots", "running")
        try:
            shots = detect_shots(
                video.path,
                video.video_id,
                video.fps or 25.0,
                video.duration_ms,
                cfg.shot,
            )
            delete_shots(conn, video.video_id, generation)
            for shot in shots:
                upsert_shot(conn, shot, generation)
            set_index_status(conn, video.video_id, generation, "shots", "done")
        except Exception as exc:
            set_index_status(conn, video.video_id, generation, "shots", "failed", str(exc))
            raise
        report.shots += len(shots)
        did_work = True
        logger.info("%s: %d shots", video.video_id, len(shots))

    if shots is None:
        shots = load_shots(conn, video.video_id, generation)

    if "keyframes" in steps and not step_done(conn, video.video_id, generation, "keyframes"):
        if not shots:
            raise RuntimeError("no shots available for keyframe extraction")
        set_index_status(conn, video.video_id, generation, "keyframes", "running")
        try:
            delete_keyframes(conn, video.video_id, generation)
            shutil.rmtree(cfg.keyframes_dir / video.video_id / f"g{generation}", ignore_errors=True)
            keyframes = extract_keyframes(
                video.path,
                video.video_id,
                shots,
                cfg.keyframe,
                cfg.artifacts_dir,
                generation,
            )
            for keyframe in keyframes:
                insert_keyframe(conn, keyframe.model_copy(update={"generation": generation}))
            set_index_status(conn, video.video_id, generation, "keyframes", "done")
        except Exception as exc:
            set_index_status(conn, video.video_id, generation, "keyframes", "failed", str(exc))
            raise
        report.keyframes += len(keyframes)
        did_work = True
        logger.info("%s: %d keyframes", video.video_id, len(keyframes))

    if "follow" in steps and not step_done(conn, video.video_id, generation, "follow"):
        set_index_status(conn, video.video_id, generation, "follow", "running")
        try:
            delete_follow_frames(conn, video.video_id, generation)
            shutil.rmtree(
                cfg.follow_frames_dir / video.video_id / f"g{generation}", ignore_errors=True
            )
            keyframes = load_keyframes(conn, video.video_id, generation)
            count = 0
            if not keyframes or not shots:
                logger.warning("%s: no keyframes/shots for follow frames", video.video_id)
            else:
                follow_frames = extract_follow_frames(
                    video.path,
                    video.video_id,
                    keyframes,
                    shots,
                    cfg.keyframe,
                    cfg.artifacts_dir,
                    generation,
                )
                for follow_frame in follow_frames:
                    insert_follow_frame(conn, follow_frame)
                count = len(follow_frames)
                report.follow_frames += count
            set_index_status(conn, video.video_id, generation, "follow", "done")
        except Exception as exc:
            set_index_status(conn, video.video_id, generation, "follow", "failed", str(exc))
            raise
        did_work = True
        logger.info("%s: %d follow frames", video.video_id, count)

    if not did_work:
        report.skipped += 1

    if reindex:
        _cleanup_previous_generations(cfg, video.video_id, generation)
        compact_video(conn, video.video_id)


def _cleanup_previous_generations(cfg: AppConfig, video_id: str, generation: int) -> None:
    current = f"g{generation}"
    for root in (cfg.keyframes_dir, cfg.follow_frames_dir):
        video_dir = root / video_id
        if not video_dir.exists():
            continue
        for child in video_dir.iterdir():
            if child.is_dir() and child.name != current:
                shutil.rmtree(child, ignore_errors=True)
