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


_model = None
_model_device: str | None = None


def _resolve_device(preference: str) -> str:
    if preference != "auto":
        return preference
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _get_model(device: str):
    global _model, _model_device
    if _model is None or _model_device != device:
        from transnetv2_pytorch import TransNetV2

        _model = TransNetV2(device=device)
        _model_device = device
    return _model


def _read_frames_48x27(video_path: str):
    import av
    import numpy as np

    frames = []
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            frames.append(frame.reformat(width=48, height=27, format="rgb24").to_ndarray())
    if not frames:
        raise ValueError(f"no decodable frames: {video_path}")
    return np.stack(frames)


def _transnetv2_scenes(video_path: str, cfg: ShotConfig) -> list[Scene]:
    import torch

    model = _get_model(_resolve_device(cfg.device))
    frames = torch.from_numpy(_read_frames_48x27(video_path))
    single_frame_predictions, _ = model.predict_frames(frames, quiet=True)
    scenes = model.predictions_to_scenes_with_data(
        single_frame_predictions.cpu().numpy(), threshold=cfg.threshold
    )
    return [
        (int(scene["start_frame"]), int(scene["end_frame"]), float(scene["probability"]))
        for scene in scenes
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
    scenes: list[Scene] | None = None

    if cfg.backend == "transnetv2":
        try:
            scenes = _transnetv2_scenes(video_path, cfg)
        except Exception:
            if cfg.fallback != "pyscenedetect":
                raise

    if scenes is None:
        scenes = _pyscenedetect_scenes(video_path, cfg)

    return build_shots(video_id, scenes, fps, duration_ms, cfg.min_shot_sec)
