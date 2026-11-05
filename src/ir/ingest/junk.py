from __future__ import annotations

import numpy as np

from ..config import KeyframeFilterConfig

_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def to_gray(rgb: np.ndarray) -> np.ndarray:
    return rgb.astype(np.float32) @ _LUMA


def laplacian_variance(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    laplacian = (
        -4.0 * gray
        + np.roll(gray, 1, axis=0)
        + np.roll(gray, -1, axis=0)
        + np.roll(gray, 1, axis=1)
        + np.roll(gray, -1, axis=1)
    )
    return float(laplacian[1:-1, 1:-1].var())


def is_junk(rgb: np.ndarray, cfg: KeyframeFilterConfig) -> tuple[bool, float]:
    gray = to_gray(rgb)
    mean = float(gray.mean())
    std = float(gray.std())
    sharpness = laplacian_variance(gray)

    if std < cfg.min_std:
        return True, sharpness
    if mean < cfg.min_brightness and std < cfg.min_std * 2:
        return True, sharpness
    if mean > cfg.max_brightness and std < cfg.min_std * 2:
        return True, sharpness
    if sharpness < cfg.min_sharpness:
        return True, sharpness
    return False, sharpness


def _sample_grid(gray: np.ndarray, rows: int, cols: int) -> np.ndarray:
    ys = np.linspace(0, gray.shape[0] - 1, rows).astype(np.intp)
    xs = np.linspace(0, gray.shape[1] - 1, cols).astype(np.intp)
    return gray[np.ix_(ys, xs)]


def dhash(rgb: np.ndarray, size: int = 8) -> int:
    small = _sample_grid(to_gray(rgb), size, size + 1)
    bits = (small[:, 1:] > small[:, :-1]).reshape(-1)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()
