from __future__ import annotations

import numpy as np

from ir.config import KeyframeFilterConfig
from ir.ingest.junk import dhash, hamming, is_junk


def _checkerboard(size: int = 64) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    frame[::2, ::2] = 255
    frame[1::2, 1::2] = 255
    return frame


def test_black_and_white_frames_are_junk() -> None:
    cfg = KeyframeFilterConfig()

    assert is_junk(np.zeros((64, 64, 3), dtype=np.uint8), cfg)[0]
    assert is_junk(np.full((64, 64, 3), 255, dtype=np.uint8), cfg)[0]


def test_sharp_frame_is_kept() -> None:
    cfg = KeyframeFilterConfig()

    junk, sharpness = is_junk(_checkerboard(), cfg)

    assert junk is False
    assert sharpness > cfg.min_sharpness


def test_soft_gradient_is_junk() -> None:
    cfg = KeyframeFilterConfig()
    ramp = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
    frame = np.repeat(ramp[:, :, None], 3, axis=2)

    assert is_junk(frame, cfg)[0] is True


def test_dhash_identical_and_distinct() -> None:
    noise = np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)

    assert hamming(dhash(noise), dhash(noise.copy())) == 0
    assert hamming(dhash(noise), dhash(_checkerboard())) > 5
