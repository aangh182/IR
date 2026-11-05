from __future__ import annotations

from ir.config import FollowConfig, KeyframeConfig
from ir.ingest.sampling import follow_timestamps, sample_timestamps


def _cfg() -> KeyframeConfig:
    return KeyframeConfig(long_shot_sec=10.0, every_sec=5.0, max_per_shot=5)


def test_short_shot_uses_midpoint() -> None:
    assert sample_timestamps(1000, 3000, _cfg()) == [2000]


def test_long_shot_is_capped_and_inside_span() -> None:
    timestamps = sample_timestamps(0, 60_000, _cfg())

    assert len(timestamps) == 5
    assert timestamps == sorted(timestamps)
    assert 0 < timestamps[0] < timestamps[-1] < 60_000


def test_degenerate_span_returns_one_timestamp() -> None:
    assert sample_timestamps(500, 500, _cfg()) == [500]


def test_follow_timestamps_follow_after_keyframe() -> None:
    cfg = FollowConfig(step_sec=0.5, max_frames=8)

    assert follow_timestamps(1000, 2500, cfg) == [1500, 2000]


def test_follow_timestamps_are_capped() -> None:
    cfg = FollowConfig(step_sec=0.25, max_frames=3)

    assert follow_timestamps(0, 60_000, cfg) == [250, 500, 750]


def test_follow_timestamps_stop_at_shot_end() -> None:
    cfg = FollowConfig(step_sec=1.0, max_frames=8)

    assert follow_timestamps(1000, 2000, cfg) == []
