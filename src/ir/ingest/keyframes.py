from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

import av
import numpy as np
from PIL import Image

from ..config import KeyframeConfig
from ..types import Keyframe, Shot
from .junk import dhash, hamming, is_junk
from .sampling import sample_timestamps

logger = logging.getLogger(__name__)

Target = tuple[int, int, int, int]


def frame_time_ms(frame, stream) -> int:
    if frame.time is not None:
        return int(round(frame.time * 1000))
    if frame.pts is not None:
        return int(round(float(frame.pts * stream.time_base) * 1000))
    return 0


def save_frame_image(rgb: np.ndarray, path: Path, cfg: KeyframeConfig) -> None:
    image = Image.fromarray(rgb)
    width, height = image.size
    scale = cfg.short_side / min(width, height)
    if scale < 1:
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=cfg.jpeg_quality)


def _write_frame(
    rgb: np.ndarray,
    video_dir: Path,
    artifacts_dir: Path,
    shot_idx: int,
    kf_idx: int,
    cfg: KeyframeConfig,
) -> str:
    path = video_dir / f"{shot_idx:06d}_{kf_idx:03d}.jpg"
    save_frame_image(rgb, path, cfg)
    return path.relative_to(artifacts_dir).as_posix()


def extract_keyframes(
    video_path: str,
    video_id: str,
    shots: list[Shot],
    cfg: KeyframeConfig,
    artifacts_dir: Path,
    generation: int = 0,
) -> list[Keyframe]:
    targets: list[Target] = []
    for shot in shots:
        for kf_idx, timestamp in enumerate(sample_timestamps(shot.start_ms, shot.end_ms, cfg)):
            targets.append((timestamp, shot.shot_idx, kf_idx, shot.end_ms))
    targets.sort()
    if not targets:
        return []

    video_dir = artifacts_dir / "keyframes" / video_id / f"g{generation}"
    pending = deque(targets)
    extracted: list[Keyframe] = []

    shot_state: dict[str, object] = {"shot": None, "saved": 0, "best": None, "hashes": []}

    def flush() -> None:
        shot_idx = shot_state["shot"]
        best = shot_state["best"]
        if shot_idx is not None and shot_state["saved"] == 0 and best is not None:
            score, rgb, timestamp = best
            kf_idx = int(shot_state["saved"])
            path = _write_frame(rgb, video_dir, artifacts_dir, int(shot_idx), kf_idx, cfg)
            extracted.append(
                Keyframe(
                    video_id=video_id,
                    shot_idx=int(shot_idx),
                    kf_idx=kf_idx,
                    ts_ms=int(timestamp),
                    path=path,
                    generation=generation,
                )
            )
            logger.debug("fallback keyframe shot=%s score=%.1f", shot_idx, score)
        shot_state.update({"best": None, "saved": 0, "hashes": [], "shot": None})

    def switch_shot(shot_idx: int) -> None:
        if shot_state["shot"] is None:
            shot_state["shot"] = shot_idx
        elif shot_state["shot"] != shot_idx:
            flush()
            shot_state["shot"] = shot_idx

    with av.open(video_path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            timestamp = frame_time_ms(frame, stream)
            while pending and pending[0][0] <= timestamp:
                ts_ms, shot_idx, kf_idx, _ = pending.popleft()
                switch_shot(shot_idx)

                rgb = frame.to_ndarray(format="rgb24")
                junk, score = is_junk(rgb, cfg.filter)
                if not junk:
                    fingerprint = dhash(rgb)
                    if any(
                        hamming(fingerprint, previous) < cfg.filter.duplicate_distance
                        for previous in shot_state["hashes"]
                    ):
                        junk = True
                    else:
                        shot_state["hashes"].append(fingerprint)

                if junk:
                    best = shot_state["best"]
                    if best is None or score > best[0]:
                        shot_state["best"] = (score, rgb.copy(), ts_ms)
                    continue

                path = _write_frame(rgb, video_dir, artifacts_dir, shot_idx, kf_idx, cfg)
                extracted.append(
                    Keyframe(
                        video_id=video_id,
                        shot_idx=shot_idx,
                        kf_idx=kf_idx,
                        ts_ms=ts_ms,
                        path=path,
                        generation=generation,
                    )
                )
                shot_state["saved"] = int(shot_state["saved"]) + 1
            if not pending:
                break

    while pending:
        _, shot_idx, _, _ = pending.popleft()
        switch_shot(shot_idx)
    flush()

    if len(extracted) < len(shots):
        logger.warning(
            "%s: %d/%d shots produced a keyframe", video_id, len(extracted), len(shots)
        )
    return extracted
