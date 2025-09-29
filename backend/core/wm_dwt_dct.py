from __future__ import annotations

import textwrap
from io import BytesIO
from typing import Dict, List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

PAYLOAD_OVERHEAD_BYTES = 0
OVERLAY_ALPHA = 4  # 0-255, keep extremely low opacity
TEXT_STEP_Y = 160
TEXT_PADDING = 24
TEXT_FONT_SIZE = 6
TEXT_MARKER_PREFIX = "__WM_START__"
TEXT_MARKER_SUFFIX = "__WM_END__"


class WatermarkingError(RuntimeError):
    """Raised when watermark embedding/extraction fails."""


def _normalize_message(message: str) -> str:
    # No hard limit: rely on downstream metadata capacity and caller validation.
    return message


def _pattern(message: str) -> str:
    return f"{TEXT_MARKER_PREFIX}{message}{TEXT_MARKER_SUFFIX}"


def _build_overlay_tile(marker: str, width: int) -> str:
    wrap_width = max(32, width // 8)
    return textwrap.fill(marker, width=wrap_width)


def embed_image(
    img_bgr: np.ndarray,
    message: str,
) -> Tuple[np.ndarray, Dict]:
    normalized = _normalize_message(message)
    height, width = img_bgr.shape[:2]

    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    base = Image.fromarray(rgba)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    stamped = _pattern(normalized)
    tile = _build_overlay_tile(stamped, width)

    for y in range(0, height + TEXT_STEP_Y, TEXT_STEP_Y):
        draw.text(
            (TEXT_PADDING, y + TEXT_PADDING),
            tile,
            fill=(255, 255, 255, OVERLAY_ALPHA),
            font=font,
        )

    combined = Image.alpha_composite(base, overlay).convert("RGB")
    watermarked = cv2.cvtColor(np.array(combined), cv2.COLOR_RGB2BGR)

    return watermarked, {
        "pattern": stamped,
        "overlay_opacity_percent": round(OVERLAY_ALPHA / 255 * 100, 3),
        "overlay_line_spacing": TEXT_STEP_Y,
        "overlay_padding": TEXT_PADDING,
    }


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


def embed_pdf(
    frames: List[np.ndarray],
    message: str,
) -> Tuple[bytes, Dict]:
    normalized = _normalize_message(message)
    doc = fitz.open()
    meta_overlay: Dict | None = None

    for frame in frames:
        watermarked, overlay_meta = embed_image(frame, normalized)
        meta_overlay = overlay_meta

        height, width = watermarked.shape[:2]
        page = doc.new_page(width=width, height=height)

        success, png_bytes = cv2.imencode(".png", watermarked)
        if not success:
            raise WatermarkingError("Impossible de traiter l'image de la page.")

        rect = fitz.Rect(0, 0, width, height)
        page.insert_image(rect, stream=png_bytes.tobytes())

    marker = (meta_overlay or {}).get("pattern", _pattern(normalized))
    metadata = doc.metadata or {}
    metadata.update({"keywords": marker, "subject": marker})
    doc.set_metadata(metadata)

    buffer = BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue(), meta_overlay or {
        "pattern": marker,
        "overlay_opacity_percent": round(OVERLAY_ALPHA / 255 * 100, 3),
        "overlay_line_spacing": TEXT_STEP_Y,
        "overlay_padding": TEXT_PADDING,
    }


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


def extract(message: bytes, *args, **kwargs):
    raise NotImplementedError("Legacy extract method is no longer supported.")


def embed(*args, **kwargs):
    raise NotImplementedError("Legacy embed method is no longer supported.")
