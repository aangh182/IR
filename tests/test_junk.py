from __future__ import annotations

import numpy as np

from ir.config import KeyframeFilterConfig
from ir.ingest.junk import (
    dhash,
    dhash_gray,
    hamming,
    is_hard_junk,
    laplacian_variance,
    to_gray,
)


def _checkerboard(size: int = 64) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    frame[::2, ::2] = 255
    frame[1::2, 1::2] = 255
    return frame


def test_black_and_white_frames_are_hard_junk() -> None:
    cfg = KeyframeFilterConfig()

    assert is_hard_junk(to_gray(np.zeros((64, 64, 3), dtype=np.uint8)), cfg)
    assert is_hard_junk(to_gray(np.full((64, 64, 3), 255, dtype=np.uint8)), cfg)


def test_textured_frame_is_kept() -> None:
    cfg = KeyframeFilterConfig()
    gray = to_gray(_checkerboard())

    assert is_hard_junk(gray, cfg) is False
    assert laplacian_variance(gray) > 0


def test_flat_gradient_is_not_hard_junk_but_low_detail() -> None:
    cfg = KeyframeFilterConfig()
    ramp = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
    gray = to_gray(np.repeat(ramp[:, :, None], 3, axis=2))

    assert is_hard_junk(gray, cfg) is False
    assert laplacian_variance(gray) < 10


def test_dhash_identical_and_distinct() -> None:
    noise = np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)

    assert hamming(dhash(noise), dhash(noise.copy())) == 0
    assert hamming(dhash(noise), dhash(_checkerboard())) > 5


def test_dhash_gray_matches_rgb() -> None:
    noise = np.random.default_rng(1).integers(0, 256, (64, 64, 3), dtype=np.uint8)

    assert dhash_gray(to_gray(noise)) == dhash(noise)
