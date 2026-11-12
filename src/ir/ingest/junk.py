from __future__ import annotations

import numpy as np
from PIL import Image

from ..config import KeyframeFilterConfig

_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def to_gray(rgb: np.ndarray) -> np.ndarray:
    return rgb.astype(np.float32) @ _LUMA


def metric_gray(rgb: np.ndarray, width: int) -> np.ndarray:
    image = Image.fromarray(rgb)
    if width > 0 and image.width > width:
        height = max(1, round(image.height * width / image.width))
        image = image.resize((width, height), Image.Resampling.BOX)
    return to_gray(np.asarray(image))


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


def is_hard_junk(gray: np.ndarray, cfg: KeyframeFilterConfig) -> bool:
    mean = float(gray.mean())
    std = float(gray.std())

    if std < cfg.min_std:
        return True
    if mean < cfg.min_brightness and std < cfg.min_std * 2:
        return True
    if mean > cfg.max_brightness and std < cfg.min_std * 2:
        return True
    return False


def dhash_gray(gray: np.ndarray, size: int = 8) -> int:
    image = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8))
    small = np.asarray(image.resize((size + 1, size), Image.Resampling.BOX), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).reshape(-1)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def dhash(rgb: np.ndarray, size: int = 8) -> int:
    return dhash_gray(to_gray(rgb), size)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()
