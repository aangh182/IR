from __future__ import annotations

from ir.ingest.shots import build_shots, merge_short_bursts
from ir.types import Shot


def test_no_scenes_covers_whole_video() -> None:
    shots = build_shots("v", [], 25.0, 10_000, 0.5)

    assert len(shots) == 1
    assert (shots[0].start_ms, shots[0].end_ms) == (0, 10_000)


def test_shots_are_contiguous_and_cover_timeline() -> None:
    scenes = [(25, 49, None), (100, 124, None)]

    shots = build_shots("v", scenes, 25.0, 6_000, 0.5)

    assert shots[0].start_ms == 0
    assert shots[-1].end_ms == 6_000
    for previous, current in zip(shots, shots[1:], strict=False):
        assert previous.end_ms == current.start_ms
    assert [shot.shot_idx for shot in shots] == list(range(len(shots)))


def test_adjacent_scenes_stay_separate() -> None:
    scenes = [(0, 24, None), (25, 49, None)]

    shots = build_shots("v", scenes, 25.0, 2_000, 0.5)

    assert len(shots) == 2


def test_short_shot_is_merged_into_previous() -> None:
    scenes = [(0, 49, 0.9), (50, 54, 0.8), (55, 99, 0.7)]

    shots = build_shots("v", scenes, 25.0, 4_000, 0.5)

    assert len(shots) == 2
    assert shots[0].scene_score == 0.9
    assert shots[0].end_ms == shots[1].start_ms


def test_scores_keep_maximum_when_merging() -> None:
    scenes = [(0, 24, 0.4), (25, 29, 0.9)]

    shots = build_shots("v", scenes, 25.0, 1_200, 0.5)

    assert len(shots) == 1
    assert shots[0].scene_score == 0.9


def _shots(spans: list[tuple[int, int]]) -> list[Shot]:
    return [
        Shot(video_id="v", shot_idx=index, start_ms=start, end_ms=end)
        for index, (start, end) in enumerate(spans)
    ]


def test_isolated_short_shot_is_kept() -> None:
    shots = _shots([(0, 3000), (3000, 4000), (4000, 9000)])

    merged = merge_short_bursts(shots, 1500)

    assert [(shot.start_ms, shot.end_ms) for shot in merged] == [
        (0, 3000),
        (3000, 4000),
        (4000, 9000),
    ]


def test_run_of_short_shots_merges_into_previous() -> None:
    shots = _shots([(0, 3000), (3000, 4000), (4000, 5000), (5000, 9000)])

    merged = merge_short_bursts(shots, 1500)

    assert [(shot.start_ms, shot.end_ms) for shot in merged] == [(0, 5000), (5000, 9000)]
    assert [shot.shot_idx for shot in merged] == [0, 1]


def test_short_burst_at_start_merges_into_next() -> None:
    shots = _shots([(0, 1000), (1000, 2000), (2000, 6000)])

    merged = merge_short_bursts(shots, 1500)

    assert [(shot.start_ms, shot.end_ms) for shot in merged] == [(0, 6000)]


def test_zero_threshold_disables_burst_merge() -> None:
    shots = _shots([(0, 1000), (1000, 2000), (2000, 6000)])

    assert merge_short_bursts(shots, 0) == shots
