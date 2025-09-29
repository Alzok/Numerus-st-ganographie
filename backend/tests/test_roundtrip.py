from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np

from backend.core import io_utils, wm_dwt_dct


def build_base_image() -> np.ndarray:
    h, w = 512, 512
    x = np.linspace(0, 255, w, dtype=np.float32)
    y = np.linspace(0, 255, h, dtype=np.float32)
    xv, yv = np.meshgrid(x, y)
    gradient = 0.6 * xv + 0.4 * yv
    gradient = np.clip(gradient, 0, 255).astype(np.uint8)
    return cv2.merge([gradient, np.flipud(gradient), gradient])


def test_png_overlay_roundtrip() -> None:
    image = build_base_image()
    message = "Compétences: Python, Vision, NLP"

    watermarked, meta = wm_dwt_dct.embed_image(image, message)
    png_bytes = io_utils.encode_png(watermarked, text=message, pattern=meta.get("pattern"))

    recovered = wm_dwt_dct.extract_from_png_bytes(png_bytes)
    assert recovered == message


def test_pdf_overlay_roundtrip() -> None:
    image = build_base_image()
    message = "Expérience senior – data & IA"

    pdf_bytes = wm_dwt_dct.embed_pdf([image, image], message)
    recovered = wm_dwt_dct.extract_from_pdf_bytes(pdf_bytes)
    assert recovered == message


def test_capacity_estimation_sane_values() -> None:
    image = build_base_image()
    info = wm_dwt_dct.estimate_capacity(image, block_size=8)
    assert info["capacity_bits"] > 0
    assert info["max_message_bytes"] <= wm_dwt_dct.MAX_MESSAGE_BYTES
