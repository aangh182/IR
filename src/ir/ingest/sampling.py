from __future__ import annotations

import math

from ..config import FollowConfig, KeyframeConfig

Span = tuple[int, int]


def shot_segments(start_ms: int, end_ms: int, cfg: KeyframeConfig) -> list[Span]:
    start = max(0, int(start_ms))
    end = max(start + 1, int(end_ms))
    length = end - start
    step = max(1, int(cfg.every_sec * 1000))
    count = max(1, math.ceil(length / step))
    return [
        (start + length * index // count, start + length * (index + 1) // count)
        for index in range(count)
    ]


def follow_timestamps(
    ts_ms: int, shot_start_ms: int, shot_end_ms: int, cfg: FollowConfig
) -> list[int]:
    step = max(1, int(cfg.step_sec * 1000))
    limit = max(0, cfg.max_frames)
    if limit == 0:
        return []

    before: list[int] = []
    timestamp = ts_ms - step
    while timestamp > shot_start_ms and len(before) < limit:
        before.append(timestamp)
        timestamp -= step

    after: list[int] = []
    timestamp = ts_ms + step
    while timestamp < shot_end_ms and len(after) < limit:
        after.append(timestamp)
        timestamp += step

    if not cfg.bidirectional:
        before = []

    closest = sorted(before + after, key=lambda value: (abs(value - ts_ms), value))
    return sorted(closest[:limit])
