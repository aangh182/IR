from __future__ import annotations

from ..config import ShotConfig
from ..types import Shot

Scene = tuple[int, int, float | None]


def _frame_to_ms(frame: int, fps: float) -> int:
    return int(round(frame * 1000 / fps))


def build_shots(
    video_id: str,
    scenes: list[Scene],
    fps: float,
    duration_ms: int,
    min_shot_sec: float,
) -> list[Shot]:
    if duration_ms <= 0:
        return []

    fps = fps if fps and fps > 0 else 25.0
    min_ms = int(min_shot_sec * 1000)

    spans: list[list[float | int | None]] = []
    for start_frame, end_frame, score in scenes:
        start = max(0, min(duration_ms, _frame_to_ms(start_frame, fps)))
        end = max(0, min(duration_ms, _frame_to_ms(end_frame + 1, fps)))
        if end - start <= 0:
            continue
        spans.append([start, end, score])
    if not spans:
        return [Shot(video_id=video_id, shot_idx=0, start_ms=0, end_ms=duration_ms)]

    spans.sort(key=lambda span: span[0])
    merged: list[list[float | int | None]] = []
    for start, end, score in spans:
        if merged and start < merged[-1][1]:
            start = merged[-1][1]
        if end <= start:
            continue
        merged.append([start, end, score])

    compact: list[list[float | int | None]] = []
    for start, end, score in merged:
        if compact and end - start < min_ms:
            compact[-1][1] = end
            if score is not None:
                compact[-1][2] = max(float(compact[-1][2] or 0.0), score)
        else:
            compact.append([start, end, score])
    while len(compact) > 1 and compact[0][1] - compact[0][0] < min_ms:
        compact[1][0] = compact[0][0]
        compact.pop(0)

    compact[0][0] = 0
    for index in range(1, len(compact)):
        if compact[index][0] > compact[index - 1][1]:
            compact[index - 1][1] = compact[index][0]
    compact[-1][1] = duration_ms

    shots: list[Shot] = []
    for start, end, score in compact:
        start_ms = int(start)
        end_ms = int(end)
        if end_ms <= start_ms:
            continue
        shots.append(
            Shot(
                video_id=video_id,
                shot_idx=len(shots),
                start_ms=start_ms,
                end_ms=end_ms,
                scene_score=float(score) if score is not None else None,
            )
        )
    if not shots:
        return [Shot(video_id=video_id, shot_idx=0, start_ms=0, end_ms=duration_ms)]
    return shots


def merge_short_bursts(shots: list[Shot], min_ms: int) -> list[Shot]:
    if len(shots) < 2 or min_ms <= 0:
        return shots

    spans = [[shot.start_ms, shot.end_ms] for shot in shots]
    marked = [end - start < min_ms for start, end in spans]
    merged: list[list[int]] = []
    index = 0
    while index < len(spans):
        if not marked[index]:
            merged.append(spans[index])
            index += 1
            continue
        last = index
        while last + 1 < len(spans) and marked[last + 1]:
            last += 1
        if last > index:
            if merged:
                merged[-1][1] = spans[last][1]
            elif last + 1 < len(spans):
                spans[last + 1][0] = spans[index][0]
            else:
                merged.append([spans[index][0], spans[last][1]])
            index = last + 1
        else:
            merged.append(spans[index])
            index += 1

    merged[0][0] = 0
    for position in range(1, len(merged)):
        if merged[position][0] > merged[position - 1][1]:
            merged[position - 1][1] = merged[position][0]
    merged[-1][1] = spans[-1][1]

    return [
        Shot(video_id=shots[0].video_id, shot_idx=position, start_ms=start, end_ms=end)
        for position, (start, end) in enumerate(merged)
        if end > start
    ]


def _pyscenedetect_scenes(video_path: str, cfg: ShotConfig) -> list[Scene]:
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector

    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=cfg.pyscenedetect_threshold))
    manager.detect_scenes(video, show_progress=False)
    return [
        (start.get_frames(), end.get_frames() - 1, None)
        for start, end in manager.get_scene_list()
    ]


def detect_shots(
    video_path: str,
    video_id: str,
    fps: float,
    duration_ms: int,
    cfg: ShotConfig,
) -> list[Shot]:
    scenes = _pyscenedetect_scenes(video_path, cfg)
    shots = build_shots(video_id, scenes, fps, duration_ms, cfg.min_shot_sec)
    return merge_short_bursts(shots, int(cfg.pyscenedetect_burst_merge_sec * 1000))
