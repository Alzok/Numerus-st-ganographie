from __future__ import annotations

import cv2
import pytest
import numpy as np

from pdf2image.exceptions import PDFInfoNotInstalledError

from backend.core import io_utils

from backend.core import metrics, wm_dwt_dct


@pytest.fixture()
def base_image() -> np.ndarray:
    h, w = 512, 512
    x = np.linspace(0, 255, w, dtype=np.float32)
    y = np.linspace(0, 255, h, dtype=np.float32)
    xv, yv = np.meshgrid(x, y)
    gradient = 0.6 * xv + 0.4 * yv
    gradient = np.clip(gradient, 0, 255).astype(np.uint8)
    image = cv2.merge([gradient, np.flipud(gradient), gradient])
    return image


def apply_jpeg(image: np.ndarray, quality: int = 85) -> np.ndarray:
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(".jpg", image, encode_params)
    if not success:
        raise RuntimeError("JPEG compression failed during test setup")
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("JPEG decode failed during test setup")
    return decoded


def test_roundtrip_clean(base_image: np.ndarray) -> None:
    message = "Les données de test voyagent en toute discrétion." * 2
    seed = 12345
    strength = 0.6

    marked, metadata = wm_dwt_dct.embed(
        base_image,
        message.encode("utf-8"),
        seed=seed,
        strength=strength,
        block_size=8,
    )
    assert metadata["bits_embedded"] > 0

    recovered, info = wm_dwt_dct.extract(marked, seed=seed, block_size=8)
    assert recovered.decode("utf-8") == message
    assert info.get("crc_ok", True)

    score = metrics.psnr(base_image, marked)
    assert score >= 38.0


def test_roundtrip_after_jpeg(base_image: np.ndarray) -> None:
    message = "payload-qualite-robuste-" * 4
    seed = 9876
    strength = 0.9

    marked, _ = wm_dwt_dct.embed(
        base_image,
        message.encode("utf-8"),
        seed=seed,
        strength=strength,
        block_size=8,
    )

    attacked = apply_jpeg(marked, quality=85)
    recovered, _ = wm_dwt_dct.extract(attacked, seed=seed, block_size=8)

    accuracy = metrics.bit_accuracy(message.encode("utf-8"), recovered)
    assert accuracy >= 0.9


def test_pdf_roundtrip(base_image: np.ndarray) -> None:
    message = "PDF secret payload"
    seed = 4242
    strength = 0.7

    # Build a simple 2-page PDF from the base image
    from PIL import Image
    from io import BytesIO

    rgb = cv2.cvtColor(base_image, cv2.COLOR_BGR2RGB)
    pil_page = Image.fromarray(rgb)
    buffer = BytesIO()
    pil_page.save(buffer, format="PDF", save_all=True, append_images=[pil_page])
    pdf_bytes = buffer.getvalue()

    try:
        media = io_utils.load_media_bytes(
            pdf_bytes, filename="synthetic.pdf", mime_type="application/pdf"
        )
    except PDFInfoNotInstalledError:  # pragma: no cover - environment dependent
        pytest.skip("Poppler (pdftoppm) is required for PDF tests")
    assert media.is_pdf
    assert len(media.images) == 2

    watermarked_frames = []
    for frame in media.images:
        marked, _ = wm_dwt_dct.embed(
            frame,
            message.encode("utf-8"),
            seed=seed,
            strength=strength,
            block_size=8,
        )
        watermarked_frames.append(marked)

    pdf_out = io_utils.images_to_pdf(watermarked_frames)
    media_out = io_utils.load_media_bytes(
        pdf_out, filename="out.pdf", mime_type="application/pdf"
    )

    recovered = None
    for frame in media_out.images:
        try:
            candidate, meta = wm_dwt_dct.extract(frame, seed=seed, block_size=8)
        except Exception:
            continue
        if candidate:
            recovered = candidate.decode("utf-8")
            break

    assert recovered == message


def test_capacity_estimation_respects_overhead(base_image: np.ndarray) -> None:
    info = wm_dwt_dct.estimate_capacity(base_image, block_size=8)
    assert info["capacity_bits"] > 0
    assert info["max_message_bytes"] <= wm_dwt_dct.MAX_MESSAGE_BYTES

    used_bits = (info["max_message_bytes"] + wm_dwt_dct.PAYLOAD_OVERHEAD_BYTES) * 8
    assert used_bits <= info["capacity_bits"]


def test_capacity_estimation_handles_tiny_images() -> None:
    tiny = np.zeros((32, 32, 3), dtype=np.uint8)
    info = wm_dwt_dct.estimate_capacity(tiny, block_size=16)
    assert info["max_message_bytes"] == 0
