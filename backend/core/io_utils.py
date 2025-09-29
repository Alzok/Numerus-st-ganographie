from __future__ import annotations

import imghdr
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError
from PIL import Image

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SIDE = 4096
MAX_PDF_PAGES = 10

SUPPORTED_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
LOSSY_EXTENSIONS = {"jpg", "jpeg", "webp"}


class ImageValidationError(RuntimeError):
    """Raised when user input image fails validation."""


@dataclass
class LoadedMedia:
    images: List[np.ndarray]
    metadata: dict
    mime: str
    is_pdf: bool


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    if not name:
        return "upload"
    return name


def detect_format(data: bytes) -> str | None:
    kind = imghdr.what(None, data)
    if kind == "jpeg":
        return "jpg"
    return kind


def _ensure_supported(mime_type: str | None, data: bytes) -> str:
    if mime_type and mime_type in SUPPORTED_MIME:
        return SUPPORTED_MIME[mime_type]
    detected = detect_format(data)
    if detected in SUPPORTED_MIME.values():
        return detected  # type: ignore[return-value]
    raise ImageValidationError("Unsupported image format. Use PNG, JPEG or WebP.")


def _ensure_size(data: bytes) -> None:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageValidationError("Image exceeds 10 MB upload limit.")


def load_image_bytes(
    data: bytes,
    *,
    filename: str = "upload",
    mime_type: str | None = None,
    max_side: int = MAX_SIDE,
) -> Tuple[np.ndarray, dict]:
    """Decode user-provided bytes into a BGR image with validation."""

    _ensure_size(data)
    ext = _ensure_supported(mime_type, data)

    if ext == "pdf":
        return _load_pdf(data, filename=filename, max_side=max_side)

    return _load_image(data, filename=filename, ext=ext, max_side=max_side)


def encode_png(image: np.ndarray) -> bytes:
    success, buffer = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Failed to encode PNG output.")
    return buffer.tobytes()


def is_lossy_extension(ext: str | None) -> bool:
    if not ext:
        return False
    return ext.lower() in LOSSY_EXTENSIONS


def images_to_pdf(images: List[np.ndarray]) -> bytes:
    if not images:
        raise ValueError("No images provided for PDF encoding")
    pil_pages = []
    for img in images:
        if img.ndim != 3:
            raise ValueError("Expected color image for PDF export")
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_pages.append(Image.fromarray(rgb))

    output = BytesIO()
    pil_pages[0].save(
        output,
        format="PDF",
        save_all=True,
        append_images=pil_pages[1:],
        resolution=200.0,
    )
    return output.getvalue()


def _resize_if_needed(image: np.ndarray, max_side: int) -> tuple[np.ndarray, bool]:
    h, w = image.shape[:2]
    if h == 0 or w == 0:
        raise ImageValidationError("Image has invalid dimensions.")

    scale = 1.0
    max_dim = max(h, w)
    if max_dim > max_side:
        scale = max_side / max_dim
        new_size = (int(w * scale), int(h * scale))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
        return image, True
    return image, False


def _load_image(data: bytes, *, filename: str, ext: str, max_side: int) -> LoadedMedia:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ImageValidationError("Could not decode image data.")

    image, resized = _resize_if_needed(image, max_side)
    meta = {
        "original_filename": sanitize_filename(filename),
        "original_extension": ext,
        "was_resized": resized,
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "page_count": 1,
    }
    return LoadedMedia(images=[image], metadata=meta, mime="image/png", is_pdf=False)


def _load_pdf(data: bytes, *, filename: str, max_side: int) -> LoadedMedia:
    try:
        pages = convert_from_bytes(
            data,
            dpi=200,
            fmt="png",
            use_cropbox=False,
            first_page=1,
            last_page=None,
        )
    except PDFInfoNotInstalledError:
        raise
    except Exception as exc:  # pragma: no cover
        raise ImageValidationError(f"Could not decode PDF: {exc}") from exc

    if not pages:
        raise ImageValidationError("PDF appears to have no pages.")
    if len(pages) > MAX_PDF_PAGES:
        raise ImageValidationError(
            f"PDF has too many pages (>{MAX_PDF_PAGES}). Provide a smaller document."
        )

    images: List[np.ndarray] = []
    resized_any = False
    sizes = []
    for page in pages:
        arr = np.array(page.convert("RGB"))  # RGB
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        bgr, resized = _resize_if_needed(bgr, max_side)
        images.append(bgr)
        resized_any = resized_any or resized
        sizes.append((bgr.shape[1], bgr.shape[0]))

    width, height = sizes[0]
    meta = {
        "original_filename": sanitize_filename(filename),
        "original_extension": "pdf",
        "was_resized": resized_any,
        "width": int(width),
        "height": int(height),
        "page_count": len(images),
    }
    return LoadedMedia(
        images=images, metadata=meta, mime="application/pdf", is_pdf=True
    )


def load_media_bytes(
    data: bytes,
    *,
    filename: str = "upload",
    mime_type: str | None = None,
    max_side: int = MAX_SIDE,
) -> LoadedMedia:
    _ensure_size(data)
    ext = _ensure_supported(mime_type, data)
    return (
        _load_image(data, filename=filename, ext=ext, max_side=max_side)
        if ext != "pdf"
        else _load_pdf(data, filename=filename, max_side=max_side)
    )
