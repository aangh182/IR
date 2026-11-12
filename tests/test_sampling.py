from __future__ import annotations

from ir.config import FollowConfig, KeyframeConfig
from ir.ingest.sampling import follow_timestamps, shot_segments


def _cfg() -> KeyframeConfig:
    return KeyframeConfig(every_sec=4.0)


def test_short_shot_is_one_segment() -> None:
    assert shot_segments(1000, 3000, _cfg()) == [(1000, 3000)]


def test_long_shot_is_split_evenly() -> None:
    segments = shot_segments(0, 60_000, _cfg())

    assert len(segments) == 15
    assert segments[0] == (0, 4000)
    assert segments[-1] == (56_000, 60_000)
    for previous, current in zip(segments, segments[1:], strict=False):
        assert previous[1] == current[0]


def test_degenerate_span_returns_one_segment() -> None:
    assert shot_segments(500, 500, _cfg()) == [(500, 501)]


def test_follow_timestamps_are_bidirectional() -> None:
    cfg = FollowConfig(step_sec=0.5, max_frames=8, bidirectional=True)

    assert follow_timestamps(1000, 0, 2500, cfg) == [500, 1500, 2000]


def test_follow_timestamps_keep_closest_when_capped() -> None:
    cfg = FollowConfig(step_sec=0.25, max_frames=3, bidirectional=True)

    assert follow_timestamps(10_000, 0, 20_000, cfg) == [9500, 9750, 10_250]


def test_follow_timestamps_forward_only() -> None:
    cfg = FollowConfig(step_sec=0.5, max_frames=8, bidirectional=False)

    assert follow_timestamps(1000, 0, 2500, cfg) == [1500, 2000]


def test_follow_timestamps_stop_at_shot_end() -> None:
    cfg = FollowConfig(step_sec=0.5, max_frames=8)

    assert follow_timestamps(1000, 0, 1200, cfg) == [500]
    assert follow_timestamps(1000, 900, 1100, cfg) == []
