from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import av

from ..config import FollowConfig, KeyframeConfig
from ..types import FollowFrame, Keyframe, Shot
from .junk import dhash, hamming
from .keyframes import frame_time_ms, save_frame_image
from .sampling import follow_timestamps

Request = tuple[int, int, int]  # ts_ms, shot_idx, kf_idx


def follow_requests(
    keyframes: list[Keyframe], shots: list[Shot], cfg: FollowConfig
) -> list[Request]:
    shots_by_idx = {shot.shot_idx: shot for shot in shots}
    requests: list[Request] = []
    for keyframe in keyframes:
        shot = shots_by_idx.get(keyframe.shot_idx)
        if shot is None:
            continue
        for timestamp in follow_timestamps(keyframe.ts_ms, shot.end_ms, cfg):
            requests.append((timestamp, keyframe.shot_idx, keyframe.kf_idx))
    requests.sort()
    return requests


def extract_follow_frames(
    video_path: str,
    video_id: str,
    keyframes: list[Keyframe],
    shots: list[Shot],
    cfg: KeyframeConfig,
    artifacts_dir: Path,
    generation: int = 0,
) -> list[FollowFrame]:
    pending = deque(follow_requests(keyframes, shots, cfg.follow))
    if not pending:
        return []

    video_dir = artifacts_dir / "follow_frames" / video_id / f"g{generation}"
    extracted: list[FollowFrame] = []
    hashes: dict[tuple[int, int], list[int]] = defaultdict(list)
    counts: dict[tuple[int, int], int] = defaultdict(int)

    with av.open(video_path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            timestamp = frame_time_ms(frame, stream)
            while pending and pending[0][0] <= timestamp:
                _, shot_idx, kf_idx = pending.popleft()

                rgb = frame.to_ndarray(format="rgb24")
                group = (shot_idx, kf_idx)
                fingerprint = dhash(rgb)
                if any(
                    hamming(fingerprint, previous) < cfg.filter.duplicate_distance
                    for previous in hashes[group]
                ):
                    continue
                hashes[group].append(fingerprint)

                frame_idx = counts[group]
                counts[group] += 1
                path = video_dir / f"{shot_idx:06d}_{kf_idx:03d}_{frame_idx:03d}.jpg"
                save_frame_image(rgb, path, cfg)
                extracted.append(
                    FollowFrame(
                        video_id=video_id,
                        shot_idx=shot_idx,
                        kf_idx=kf_idx,
                        frame_idx=frame_idx,
                        ts_ms=timestamp,
                        path=path.relative_to(artifacts_dir).as_posix(),
                        generation=generation,
                    )
                )
            if not pending:
                break

    return extracted
