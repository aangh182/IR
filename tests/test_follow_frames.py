from __future__ import annotations

from pathlib import Path

import av
import numpy as np

from ir.config import FollowConfig, KeyframeConfig
from ir.ingest.follow import extract_follow_frames, follow_requests
from ir.types import Keyframe, Shot


def _make_video(path: Path) -> None:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=25)
    stream.width = 64
    stream.height = 64
    stream.pix_fmt = "yuv420p"
    for index in range(50):
        rng = np.random.default_rng(index)
        blocks = rng.integers(0, 256, size=(8, 8), dtype=np.uint8)
        array = np.kron(blocks, np.ones((8, 8), dtype=np.uint8))
        frame = av.VideoFrame.from_ndarray(np.stack([array] * 3, axis=-1), format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _keyframe(ts_ms: int) -> Keyframe:
    return Keyframe(
        video_id="sample",
        shot_idx=0,
        kf_idx=0,
        ts_ms=ts_ms,
        path="keyframes/sample/g0/000000_000.jpg",
    )


def test_follow_requests_skip_short_tail() -> None:
    shot = Shot(video_id="sample", shot_idx=0, start_ms=0, end_ms=2000)
    cfg = FollowConfig(step_sec=0.5, max_frames=8)

    assert follow_requests([_keyframe(1000)], [shot], cfg) == [
        (1500, 0, 0),
    ]
    assert follow_requests([_keyframe(1900)], [shot], cfg) == []


def test_extracts_follow_frames_after_keyframe(tmp_path) -> None:
    video_path = tmp_path / "sample.mp4"
    _make_video(video_path)
    shots = [Shot(video_id="sample", shot_idx=0, start_ms=0, end_ms=2000)]
    cfg = KeyframeConfig(
        short_side=32,
        follow=FollowConfig(step_sec=0.25, max_frames=8),
    )

    frames = extract_follow_frames(
        str(video_path), "sample", [_keyframe(1000)], shots, cfg, tmp_path, generation=1
    )

    assert len(frames) == 3
    timestamps = [frame.ts_ms for frame in frames]
    assert timestamps == sorted(timestamps)
    for frame in frames:
        assert 1000 < frame.ts_ms < 2000
        assert frame.generation == 1
        assert frame.frame_idx < 3
        assert frame.path.startswith("follow_frames/sample/g1/")
        assert (tmp_path / frame.path).exists()
    assert [frame.frame_idx for frame in frames] == [0, 1, 2]
