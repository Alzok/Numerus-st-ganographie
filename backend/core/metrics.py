from __future__ import annotations

import math

import cv2
import numpy as np


def psnr(original: np.ndarray, compared: np.ndarray) -> float:
    if original.shape != compared.shape:
        raise ValueError("Images must share the same shape for PSNR calculation")

    mse = float(np.mean((original.astype(np.float32) - compared.astype(np.float32)) ** 2))
    if mse == 0:
        return float("inf")
    max_pixel = 255.0
    return 10 * math.log10((max_pixel**2) / mse)


def bit_accuracy(expected: bytes, actual: bytes) -> float:
    if not expected:
        return 1.0 if not actual else 0.0

    expected_bits = np.unpackbits(np.frombuffer(expected, dtype=np.uint8))
    actual_bits = np.unpackbits(np.frombuffer(actual.ljust(len(expected), b"\x00"), dtype=np.uint8))
    count = min(expected_bits.size, actual_bits.size)
    if count == 0:
        return 0.0
    return float(np.mean(expected_bits[:count] == actual_bits[:count]))
