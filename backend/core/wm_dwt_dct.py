from __future__ import annotations

import textwrap
from io import BytesIO
from typing import Dict, List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

DEFAULT_BLOCK_SIZE = 8
MAX_MESSAGE_BYTES = 4096
OVERLAY_ALPHA = 12  # 0-255
TEXT_STEP_Y = 120
TEXT_PADDING = 36
TEXT_MARKER_PREFIX = "__WM_START__"
TEXT_MARKER_SUFFIX = "__WM_END__"


class WatermarkingError(RuntimeError):
    """Raised when watermark embedding/extraction fails."""


def _normalize_message(message: str) -> str:
    data = message.encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise WatermarkingError(
            f"Message trop long ({len(data)} octets). Limite : {MAX_MESSAGE_BYTES} octets."
        )
    return message


def _pattern(message: str) -> str:
    return f"{TEXT_MARKER_PREFIX}{message}{TEXT_MARKER_SUFFIX}"


def embed_image(img_bgr: np.ndarray, message: str) -> Tuple[np.ndarray, Dict]:
    normalized = _normalize_message(message)
    height, width = img_bgr.shape[:2]

    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    base = Image.fromarray(rgba)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    stamped = _pattern(normalized)
    tile = textwrap.fill(stamped, width=120)

    for y in range(0, height, TEXT_STEP_Y):
        draw.text((TEXT_PADDING, y + TEXT_PADDING), tile, fill=(255, 255, 255, OVERLAY_ALPHA), font=font)

    combined = Image.alpha_composite(base, overlay).convert("RGB")
    watermarked = cv2.cvtColor(np.array(combined), cv2.COLOR_RGB2BGR)

    return watermarked, {"pattern": stamped}


def encode_png_with_message(img_bgr: np.ndarray, message: str) -> bytes:
    normalized = _normalize_message(message)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(img_rgb)
    buffer = BytesIO()
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("wm_message", normalized)
    pnginfo.add_text("wm_pattern", _pattern(normalized))
    image.save(buffer, format="PNG", pnginfo=pnginfo)
    return buffer.getvalue()


def extract_from_png_bytes(data: bytes) -> str:
    try:
        image = Image.open(BytesIO(data))
    except Exception as exc:  # pragma: no cover - corrupted input
        raise WatermarkingError("Image invalide ou non supportée.") from exc

    info = image.info or {}
    for key in ("wm_message", "wm_pattern"):
        value = info.get(key)
        if value:
            if key == "wm_pattern":
                extracted = _extract_from_marker(value)
                if extracted:
                    return extracted
            else:
                return value
    raise WatermarkingError("Aucune donnée cachée trouvée dans cette image.")


def embed_pdf(frames: List[np.ndarray], message: str) -> bytes:
    normalized = _normalize_message(message)
    doc = fitz.open()
    marker = _pattern(normalized)

    for frame in frames:
        height, width = frame.shape[:2]
        page = doc.new_page(width=width, height=height)

        success, png_bytes = cv2.imencode(".png", frame)
        if not success:
            raise WatermarkingError("Impossible de traiter l'image de la page.")

        rect = fitz.Rect(0, 0, width, height)
        page.insert_image(rect, stream=png_bytes.tobytes())

        box = fitz.Rect(TEXT_PADDING, TEXT_PADDING, width - TEXT_PADDING, height - TEXT_PADDING)
        page.insert_textbox(
            box,
            marker,
            fontsize=12,
            color=(1, 1, 1),
            overlay=True,
            render_mode=0,
            align=fitz.TEXT_ALIGN_LEFT,
            opacity=0.02,
        )

    metadata = doc.metadata or {}
    metadata.update({"keywords": marker, "subject": marker})
    doc.set_metadata(metadata)

    buffer = BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def extract_from_pdf_bytes(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # pragma: no cover - corrupted input
        raise WatermarkingError("Document PDF invalide.") from exc

    try:
        metadata = doc.metadata or {}
        for key in ("keywords", "subject", "title"):
            candidate = metadata.get(key)
            if candidate:
                extracted = _extract_from_marker(candidate)
                if extracted:
                    return extracted

        for page in doc:
            text = page.get_text()
            extracted = _extract_from_marker(text)
            if extracted:
                return extracted
    finally:
        doc.close()

    raise WatermarkingError("Aucun texte caché n'a été trouvé dans ce PDF.")


def _extract_from_marker(text: str | None) -> str | None:
    if not text:
        return None
    start = text.find(TEXT_MARKER_PREFIX)
    if start == -1:
        return None
    end = text.find(TEXT_MARKER_SUFFIX, start + len(TEXT_MARKER_PREFIX))
    if end == -1:
        return None
    return text[start + len(TEXT_MARKER_PREFIX) : end].strip()


def estimate_capacity(img_bgr: np.ndarray, _block_size: int) -> Dict[str, int]:
    height, width = img_bgr.shape[:2]
    approx_chars = (width * height) // 32
    max_bytes = min(MAX_MESSAGE_BYTES, max(128, approx_chars))
    return {
        "capacity_bits": max_bytes * 8,
        "max_message_bytes": max_bytes,
        "max_message_bytes_per_replication": {1: max_bytes, 2: max_bytes // 2, 3: max_bytes // 3},
        "even_width": width,
        "even_height": height,
    }


def extract(message: bytes, *args, **kwargs):
    raise NotImplementedError("Legacy extract method is no longer supported.")


def embed(*args, **kwargs):
    raise NotImplementedError("Legacy embed method is no longer supported.")
