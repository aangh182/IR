from __future__ import annotations

from ir.ingest.shots import build_shots


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
