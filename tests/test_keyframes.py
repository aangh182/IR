from __future__ import annotations

from pathlib import Path

import av
import numpy as np
from PIL import Image

from ir.config import KeyframeConfig
from ir.ingest.keyframes import extract_keyframes
from ir.types import Shot


def _make_video(path: Path) -> None:
    rng = np.random.default_rng(0)
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=25)
    stream.width = 64
    stream.height = 64
    stream.pix_fmt = "yuv420p"
    for _ in range(50):
        array = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(array, format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_extracts_one_keyframe_per_shot(tmp_path) -> None:
    video_path = tmp_path / "sample.mp4"
    _make_video(video_path)
    shots = [
        Shot(video_id="sample", shot_idx=0, start_ms=0, end_ms=1000),
        Shot(video_id="sample", shot_idx=1, start_ms=1000, end_ms=2000),
    ]
    cfg = KeyframeConfig(short_side=32)

    keyframes = extract_keyframes(str(video_path), "sample", shots, cfg, tmp_path, generation=1)

    assert len(keyframes) == 2
    for keyframe in keyframes:
        shot = shots[keyframe.shot_idx]
        assert shot.start_ms <= keyframe.ts_ms < shot.end_ms
        assert keyframe.generation == 1
        image_path = tmp_path / keyframe.path
        assert image_path.exists()
        with Image.open(image_path) as image:
            assert min(image.size) == 32
