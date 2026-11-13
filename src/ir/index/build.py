from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
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
from ..types import FollowFrame, Keyframe, Shot, Video
from .manifest import write_keyframe_manifest

logger = logging.getLogger(__name__)

ALL_STEPS = {"shots", "keyframes", "follow"}
VISUAL_STEPS = ("shots", "keyframes")
_WORKER_LIMITS: list[object] = []


@dataclass
class BuildReport:
    videos: int = 0
    shots: int = 0
    keyframes: int = 0
    follow_frames: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class VideoJob:
    video: Video
    generation: int
    steps: list[str]
    new_generation: bool = False
    shots: list[Shot] | None = None
    keyframes: list[Keyframe] | None = None


@dataclass
class VideoResult:
    shots: list[Shot] | None = None
    keyframes: list[Keyframe] | None = None
    follow_frames: list[FollowFrame] | None = None


def build(
    cfg: AppConfig,
    corpus_dir: str | Path | None = None,
    limit: int | None = None,
    steps: list[str] | None = None,
    reindex: bool = False,
) -> BuildReport:
    steps = list(steps or ["shots", "keyframes", "follow"])
    unknown = set(steps) - ALL_STEPS
    if unknown:
        raise ValueError(f"unknown steps: {sorted(unknown)}")

    # A new generation is only safe when every step is rebuilt: steps left out
    # would lose their previous generation to the cleanup below.
    new_generation = reindex and set(steps) == ALL_STEPS
    force = reindex and not new_generation
    if force:
        logger.warning(
            "--reindex with partial steps (%s): rerunning in the current generation",
            ", ".join(sorted(set(steps))),
        )

    videos = scan_corpus(corpus_dir or cfg.corpus_dir)
    if limit is not None:
        videos = videos[:limit]

    # Keyframe extraction is what the rest of the pipeline consumes, and follow
    # frames are the slow tail. Running them as separate passes makes the
    # keyframe index usable (and manifest written) while follow is still going.
    phases = _split_phases(steps)

    report = BuildReport(videos=len(videos))
    handled: set[str] = set()
    init_db(cfg.db_path)
    with closing(connect(cfg.db_path)) as conn:
        for index, phase in enumerate(phases):
            _run_phase(
                conn,
                cfg,
                videos,
                phase,
                new_generation and index == 0,
                force,
                report,
                handled,
            )
            write_keyframe_manifest(cfg, conn)
    report.skipped = len(videos) - len(handled)
    return report


def _split_phases(steps: list[str]) -> list[list[str]]:
    visual = [step for step in steps if step in VISUAL_STEPS]
    if visual and "follow" in steps:
        return [visual, ["follow"]]
    return [steps]


def _run_phase(
    conn,
    cfg: AppConfig,
    videos: list[Video],
    steps: list[str],
    new_generation: bool,
    force: bool,
    report: BuildReport,
    handled: set[str],
) -> None:
    if not steps:
        return

    workers = max(1, cfg.ingest.workers)
    logger.info(
        "phase %s: %d videos, %d workers, %d decode threads",
        "+".join(steps),
        len(videos),
        workers,
        cfg.ingest.decode_threads,
    )
    if workers > 1 and len(videos) > 1:
        _run_parallel(conn, cfg, videos, steps, new_generation, force, report, handled, workers)
    else:
        for video in videos:
            _run_one(conn, cfg, video, steps, new_generation, force, report, handled)


def _run_one(
    conn,
    cfg: AppConfig,
    video: Video,
    steps: list[str],
    new_generation: bool,
    force: bool,
    report: BuildReport,
    handled: set[str],
) -> None:
    try:
        job = _plan_video(conn, cfg, video, steps, new_generation, force)
    except Exception as exc:
        _record_failure(report, handled, video.video_id, exc)
        return

    if job is None:
        return

    handled.add(video.video_id)
    if not job.steps:
        return

    try:
        result = _execute_job(job, cfg)
    except Exception as exc:
        _mark_failed(conn, job, exc)
        _record_failure(report, handled, video.video_id, exc)
        return

    try:
        _apply_result(conn, cfg, job, result, report)
    except Exception as exc:
        _record_failure(report, handled, video.video_id, exc)


def _run_parallel(
    conn,
    cfg: AppConfig,
    videos: list[Video],
    steps: list[str],
    new_generation: bool,
    force: bool,
    report: BuildReport,
    handled: set[str],
    workers: int,
) -> None:
    queue = deque(videos)
    pending: dict[Future, VideoJob] = {}
    max_in_flight = workers * 2

    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("fork"),
        initializer=_init_worker,
    ) as pool:
        while queue or pending:
            while queue and len(pending) < max_in_flight:
                video = queue.popleft()
                try:
                    job = _plan_video(conn, cfg, video, steps, new_generation, force)
                except Exception as exc:
                    _record_failure(report, handled, video.video_id, exc)
                    continue

                if job is None:
                    continue

                handled.add(video.video_id)
                if job.steps:
                    pending[pool.submit(_execute_job, job, cfg)] = job

            if not pending:
                break

            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                job = pending.pop(future)
                try:
                    _apply_result(conn, cfg, job, future.result(), report)
                except Exception as exc:
                    _mark_failed(conn, job, exc)
                    _record_failure(report, handled, job.video.video_id, exc)


def _init_worker() -> None:
    # One worker owns one video: stop BLAS/OpenCV from spawning extra threads
    # and fighting the pool for cores.
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:
        pass
    else:
        _WORKER_LIMITS.append(threadpool_limits(1))
    try:
        import cv2
    except ImportError:
        pass
    else:
        cv2.setNumThreads(1)


def _record_failure(
    report: BuildReport, handled: set[str], video_id: str, exc: Exception
) -> None:
    handled.add(video_id)
    report.failed += 1
    report.errors.append(f"{video_id}: {exc}")
    logger.exception("failed to index %s", video_id)


def _plan_video(
    conn,
    cfg: AppConfig,
    video: Video,
    steps: list[str],
    new_generation: bool,
    force: bool,
) -> VideoJob | None:
    upsert_video(conn, video)
    generation = (
        bump_generation(conn, video.video_id)
        if new_generation
        else current_generation(conn, video.video_id)
    )
    logger.info(
        "processing %s (%d ms, generation %d)",
        video.video_id,
        video.duration_ms,
        generation,
    )

    plan = [
        step
        for step in steps
        if force or not step_done(conn, video.video_id, generation, step)
    ]
    if not plan:
        return None

    running: list[str] = []
    touched = False
    shots: list[Shot] | None = None
    keyframes: list[Keyframe] | None = None

    try:
        for step in plan:
            running.append(step)
            set_index_status(conn, video.video_id, generation, step, "running")

        if "shots" not in plan and plan:
            shots = load_shots(conn, video.video_id, generation)
            if not shots:
                raise RuntimeError("no shots available for the next step")

        if "follow" in plan and "keyframes" not in plan:
            keyframes = load_keyframes(conn, video.video_id, generation)
            if not keyframes:
                if not step_done(conn, video.video_id, generation, "keyframes"):
                    raise RuntimeError(
                        "no keyframes available for follow frame extraction"
                    )
                logger.warning("%s: no keyframes, skipping follow", video.video_id)
                plan.remove("follow")
                running.remove("follow")
                set_index_status(conn, video.video_id, generation, "follow", "done")
                touched = True
    except Exception as exc:
        for step in running:
            set_index_status(conn, video.video_id, generation, step, "failed", str(exc))
        raise

    if not plan and not touched:
        return None

    return VideoJob(
        video=video,
        generation=generation,
        steps=plan,
        new_generation=new_generation,
        shots=shots,
        keyframes=keyframes,
    )


def _execute_job(job: VideoJob, cfg: AppConfig) -> VideoResult:
    video = job.video
    result = VideoResult()

    shots = job.shots
    if "shots" in job.steps:
        shots = detect_shots(
            video.path,
            video.video_id,
            video.fps or 25.0,
            video.duration_ms,
            cfg.shot,
        )
        result.shots = shots
        logger.info("%s: %d shots", video.video_id, len(shots))

    keyframes = job.keyframes
    if "keyframes" in job.steps:
        if not shots:
            raise RuntimeError("no shots available for keyframe extraction")
        shutil.rmtree(
            cfg.keyframes_dir / video.video_id / f"g{job.generation}", ignore_errors=True
        )
        keyframes = extract_keyframes(
            video.path,
            video.video_id,
            shots,
            cfg.keyframe,
            cfg.artifacts_dir,
            job.generation,
            decode_threads=cfg.ingest.decode_threads,
        )
        result.keyframes = keyframes
        logger.info("%s: %d keyframes", video.video_id, len(keyframes))

    if "follow" in job.steps:
        if not shots:
            raise RuntimeError("no shots available for follow frame extraction")
        shutil.rmtree(
            cfg.follow_frames_dir / video.video_id / f"g{job.generation}",
            ignore_errors=True,
        )
        frames = extract_follow_frames(
            video.path,
            video.video_id,
            keyframes or [],
            shots,
            cfg.keyframe,
            cfg.state_root,
            job.generation,
            keyframe_root=cfg.artifacts_dir,
            decode_threads=cfg.ingest.decode_threads,
        )
        result.follow_frames = frames
        logger.info("%s: %d follow frames", video.video_id, len(frames))

    return result


def _apply_result(
    conn,
    cfg: AppConfig,
    job: VideoJob,
    result: VideoResult,
    report: BuildReport,
) -> None:
    video_id = job.video.video_id
    generation = job.generation

    if result.shots is not None:
        try:
            delete_shots(conn, video_id, generation)
            for shot in result.shots:
                upsert_shot(conn, shot, generation)
            set_index_status(conn, video_id, generation, "shots", "done")
        except Exception as exc:
            set_index_status(conn, video_id, generation, "shots", "failed", str(exc))
            raise
        report.shots += len(result.shots)

    if result.keyframes is not None:
        try:
            delete_keyframes(conn, video_id, generation)
            for keyframe in result.keyframes:
                insert_keyframe(conn, keyframe.model_copy(update={"generation": generation}))
            set_index_status(conn, video_id, generation, "keyframes", "done")
        except Exception as exc:
            set_index_status(conn, video_id, generation, "keyframes", "failed", str(exc))
            raise
        report.keyframes += len(result.keyframes)

    if result.follow_frames is not None:
        try:
            delete_follow_frames(conn, video_id, generation)
            for follow_frame in result.follow_frames:
                insert_follow_frame(conn, follow_frame)
            set_index_status(conn, video_id, generation, "follow", "done")
        except Exception as exc:
            set_index_status(conn, video_id, generation, "follow", "failed", str(exc))
            raise
        report.follow_frames += len(result.follow_frames)

    if job.new_generation:
        _cleanup_previous_generations(cfg, video_id, generation)
        compact_video(conn, video_id)


def _mark_failed(conn, job: VideoJob, exc: Exception) -> None:
    for step in job.steps:
        set_index_status(conn, job.video.video_id, job.generation, step, "failed", str(exc))


def _cleanup_previous_generations(cfg: AppConfig, video_id: str, generation: int) -> None:
    current = f"g{generation}"
    for root in (cfg.keyframes_dir, cfg.follow_frames_dir):
        video_dir = root / video_id
        if not video_dir.exists():
            continue
        for child in video_dir.iterdir():
            if child.is_dir() and child.name != current:
                shutil.rmtree(child, ignore_errors=True)
