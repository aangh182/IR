from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import av
import numpy as np
from PIL import Image

from ..config import KeyframeConfig
from ..types import Keyframe, Shot
from .junk import dhash_gray, hamming, is_hard_junk, laplacian_variance, metric_gray
from .sampling import shot_segments

logger = logging.getLogger(__name__)

Segment = tuple[int, int, int, int]  # seg_start, seg_end, shot_idx, kf_idx
Candidate = tuple[float, int, int, np.ndarray]  # sharpness, ts_ms, dhash, rgb
MAX_CANDIDATES = 4


def frame_time_ms(frame, stream) -> int:
    time_base = float(stream.time_base) if stream.time_base else 0.0
    offset = float(stream.start_time) * time_base if stream.start_time else 0.0
    if frame.time is not None:
        return max(0, int(round((float(frame.time) - offset) * 1000)))
    if frame.pts is not None:
        return max(0, int(round((float(frame.pts) * time_base - offset) * 1000)))
    return 0


def save_frame_image(
    rgb: np.ndarray,
    path: Path,
    short_side: int,
    quality: int,
    image_format: str = "JPEG",
) -> None:
    image = Image.fromarray(rgb)
    width, height = image.size
    scale = short_side / min(width, height)
    if scale < 1:
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format=image_format, quality=quality)


def _write_frame(
    rgb: np.ndarray,
    video_dir: Path,
    artifacts_dir: Path,
    shot_idx: int,
    kf_idx: int,
    cfg: KeyframeConfig,
) -> str:
    path = video_dir / f"{shot_idx:06d}_{kf_idx:03d}.jpg"
    save_frame_image(rgb, path, cfg.short_side, cfg.jpeg_quality)
    return path.relative_to(artifacts_dir).as_posix()


def _evaluate(
    frame,
    ts_ms: int,
    candidates: list[Candidate],
    cfg: KeyframeConfig,
) -> None:
    rgb = frame.to_ndarray(format="rgb24")
    gray = metric_gray(rgb, cfg.filter.metric_width)
    if is_hard_junk(gray, cfg.filter):
        return

    sharpness = laplacian_variance(gray)
    if len(candidates) >= MAX_CANDIDATES and sharpness <= candidates[-1][0]:
        return

    candidates.append((sharpness, ts_ms, dhash_gray(gray), rgb))
    candidates.sort(key=lambda item: item[0], reverse=True)
    del candidates[MAX_CANDIDATES:]


def _acceptable(
    shot_idx: int,
    ts_ms: int,
    fingerprint: int,
    chosen: dict[int, list[tuple[int, int]]],
    cfg: KeyframeConfig,
) -> bool:
    gap_ms = int(cfg.min_gap_sec * 1000)
    for previous_ts, previous_hash in chosen.get(shot_idx, []):
        if abs(ts_ms - previous_ts) < gap_ms:
            return False
        if hamming(fingerprint, previous_hash) < cfg.filter.duplicate_distance:
            return False
    return True


def _finalize_segment(
    segment: Segment,
    candidates: list[Candidate],
    chosen: dict[int, list[tuple[int, int]]],
    video_dir: Path,
    artifacts_dir: Path,
    video_id: str,
    generation: int,
    cfg: KeyframeConfig,
) -> Keyframe | None:
    _, _, shot_idx, kf_idx = segment
    for sharpness, ts_ms, fingerprint, rgb in candidates:
        if not _acceptable(shot_idx, ts_ms, fingerprint, chosen, cfg):
            continue
        path = _write_frame(rgb, video_dir, artifacts_dir, shot_idx, kf_idx, cfg)
        chosen[shot_idx].append((ts_ms, fingerprint))
        logger.debug(
            "keyframe video=%s shot=%s kf=%s ts=%s sharpness=%.1f",
            video_id,
            shot_idx,
            kf_idx,
            ts_ms,
            sharpness,
        )
        return Keyframe(
            video_id=video_id,
            shot_idx=shot_idx,
            kf_idx=kf_idx,
            ts_ms=ts_ms,
            path=path,
            generation=generation,
        )
    return None


def extract_keyframes(
    video_path: str,
    video_id: str,
    shots: list[Shot],
    cfg: KeyframeConfig,
    artifacts_dir: Path,
    generation: int = 0,
) -> list[Keyframe]:
    segments: list[Segment] = []
    for shot in shots:
        for kf_idx, (start_ms, end_ms) in enumerate(shot_segments(shot.start_ms, shot.end_ms, cfg)):
            segments.append((start_ms, end_ms, shot.shot_idx, kf_idx))
    if not segments:
        return []
    segments.sort()

    video_dir = artifacts_dir / "keyframes" / video_id / f"g{generation}"
    step_ms = max(1, int(cfg.candidate_step_sec * 1000))
    candidate_lead = step_ms // 2

    extracted: list[Keyframe] = []
    chosen: dict[int, list[tuple[int, int]]] = defaultdict(list)
    candidates: list[Candidate] = []
    position = 0
    current: Segment | None = segments[0]
    next_eval = current[0] + candidate_lead

    def finish_current() -> None:
        nonlocal current, candidates, position, next_eval
        if current is None:
            return
        keyframe = _finalize_segment(
            current,
            candidates,
            chosen,
            video_dir,
            artifacts_dir,
            video_id,
            generation,
            cfg,
        )
        if keyframe is not None:
            extracted.append(keyframe)
        candidates = []
        position += 1
        current = segments[position] if position < len(segments) else None
        next_eval = current[0] + candidate_lead if current is not None else 0

    with av.open(video_path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            timestamp = frame_time_ms(frame, stream)
            while current is not None and timestamp >= current[1]:
                finish_current()
            if current is None:
                break
            if timestamp >= next_eval:
                _evaluate(frame, timestamp, candidates, cfg)
                while next_eval <= timestamp:
                    next_eval += step_ms

    while current is not None:
        finish_current()

    produced = {keyframe.shot_idx for keyframe in extracted}
    if len(produced) < len(shots):
        logger.warning("%s: %d/%d shots produced a keyframe", video_id, len(produced), len(shots))
    return extracted
