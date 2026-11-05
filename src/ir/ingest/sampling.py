from __future__ import annotations

from ..config import FollowConfig, KeyframeConfig


def sample_timestamps(start_ms: int, end_ms: int, cfg: KeyframeConfig) -> list[int]:
    start = max(0, int(start_ms))
    end = max(start + 1, int(end_ms))
    length = end - start
    mid = start + length // 2

    if length <= int(cfg.long_shot_sec * 1000):
        return [mid]

    step = max(1, int(cfg.every_sec * 1000))
    count = min(cfg.max_per_shot, max(1, length // step))
    return sorted({start + int((i + 0.5) * length / count) for i in range(count)})


def follow_timestamps(ts_ms: int, shot_end_ms: int, cfg: FollowConfig) -> list[int]:
    step = max(1, int(cfg.step_sec * 1000))
    timestamps: list[int] = []
    timestamp = ts_ms + step
    while timestamp < shot_end_ms and len(timestamps) < cfg.max_frames:
        timestamps.append(timestamp)
        timestamp += step
    return timestamps
