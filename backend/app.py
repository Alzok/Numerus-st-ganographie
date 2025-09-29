from __future__ import annotations

import asyncio
import base64
import logging
from logging.config import dictConfig
from pathlib import Path
from typing import Any, Callable

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pdf2image.exceptions import PDFInfoNotInstalledError

from .core import io_utils, metrics, wm_dwt_dct
from .core.io_utils import ImageValidationError
from .core.wm_dwt_dct import WatermarkingError

# ---------------------------------------------------------------------------
# Logging setup (JSON structured output)
# ---------------------------------------------------------------------------

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "backend.core.logging_utils.JSONLogFormatter",
        }
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO"},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "watermark": {"handlers": ["default"], "level": "INFO"},
    },
}

# The custom formatter is defined inside core/logging_utils.py.
# dictConfig expects the module to be importable at configuration time, so we
# defer configuration until after the custom class becomes available.
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("watermark")

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

ALLOWED_STRENGTH_RANGE = (0.1, 2.0)
REQUEST_TIMEOUT_SECONDS = 15.0
DEFAULT_BLOCK_SIZE = wm_dwt_dct.DEFAULT_BLOCK_SIZE
RESPONSE_IMAGE_MIME = "image/png"
RESPONSE_PDF_MIME = "application/pdf"

app = FastAPI(title="Watermark Tool", default_response_class=JSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


async def _run_with_timeout(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, lambda: func(*args, **kwargs)),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _ensure_strength(value: float) -> float:
    low, high = ALLOWED_STRENGTH_RANGE
    if not (low <= value <= high):
        raise HTTPException(
            status_code=422,
            detail=f"strength must be between {low} and {high}",
        )
    return value


def _ensure_block_size(value: int) -> int:
    if value <= 1 or value % 2 != 0:
        raise HTTPException(
            status_code=422, detail="block_size must be an even integer > 1"
        )
    return value


def _ensure_seed(value: int) -> int:
    if value < 0:
        raise HTTPException(status_code=422, detail="seed must be non-negative")
    return value & 0xFFFFFFFF


def _bgr_to_png_bytes(image: np.ndarray) -> bytes:
    return io_utils.encode_png(image)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/healthz")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ui", response_class=HTMLResponse)
def serve_ui() -> HTMLResponse:
    return HTMLResponse(
        content="""
        <html lang=\"fr\">
          <head><meta charset=\"utf-8\" /><title>Watermark Tool</title></head>
          <body style=\"font-family: system-ui; background:#0f172a; color:#e2e8f0; display:flex; align-items:center; justify-content:center; height:100vh;\">
            <div style=\"max-width:640px; text-align:center;\">
              <h1 style=\"font-size:2.25rem; margin-bottom:1rem;\">Interface disponible</h1>
              <p style=\"font-size:1rem; line-height:1.6; opacity:0.85;\">
                L'interface graphique est désormais servie par l'application Next.js sur <strong>http://localhost:3000</strong>.
                Utilisez cette URL pour intégrer ou extraire vos filigranes.
              </p>
            </div>
          </body>
        </html>
        """
    )


@app.post("/embed/capacity")
async def embed_capacity_endpoint(
    image: UploadFile = File(...),
    block_size: int = Form(DEFAULT_BLOCK_SIZE),
) -> dict:
    contents = await image.read()
    try:
        media = io_utils.load_media_bytes(
            contents,
            filename=image.filename or "upload",
            mime_type=image.content_type,
        )
    except PDFInfoNotInstalledError as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF support requires poppler-utils (pdftoppm) to be installed.",
        ) from exc
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    block_size = _ensure_block_size(block_size)

    try:
        capacities = [
            wm_dwt_dct.estimate_capacity(frame, block_size)
            for frame in media.images
        ]
    except WatermarkingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    capacity_bits = min(item["capacity_bits"] for item in capacities)
    max_message_bytes = min(item["max_message_bytes"] for item in capacities)

    per_replication = {}
    for replication in range(1, wm_dwt_dct.REPLICATION_FACTOR + 1):
        per_replication[str(replication)] = min(
            item["max_message_bytes_per_replication"].get(replication, 0)
            for item in capacities
        )

    sample = capacities[0]
    return {
        "capacity_bits": int(capacity_bits),
        "max_message_bytes": int(max_message_bytes),
        "max_message_bytes_by_replication": per_replication,
        "replication_factor": wm_dwt_dct.REPLICATION_FACTOR,
        "payload_overhead_bytes": wm_dwt_dct.PAYLOAD_OVERHEAD_BYTES,
        "max_message_limit_bytes": wm_dwt_dct.MAX_MESSAGE_BYTES,
        "width": int(sample.get("even_width", media.images[0].shape[1])),
        "height": int(sample.get("even_height", media.images[0].shape[0])),
        "page_count": int(media.metadata.get("page_count", 1)),
        "was_resized": bool(media.metadata.get("was_resized")),
        "mime": media.mime,
    }


@app.post("/embed")
async def embed_endpoint(
    request: Request,
    image: UploadFile = File(...),
    message: str = Form(...),
    seed: int = Form(...),
    strength: float = Form(0.5),
    block_size: int = Form(DEFAULT_BLOCK_SIZE),
):
    contents = await image.read()
    try:
        media = io_utils.load_media_bytes(
            contents,
            filename=image.filename or "upload",
            mime_type=image.content_type,
        )
    except PDFInfoNotInstalledError as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF support requires poppler-utils (pdftoppm) to be installed.",
        ) from exc
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _ensure_strength(strength)
    block_size = _ensure_block_size(block_size)
    seed = _ensure_seed(seed)

    message_bytes = message.encode("utf-8")

    async def _embed_single(frame: np.ndarray) -> tuple[np.ndarray, dict]:
        return await _run_with_timeout(
            wm_dwt_dct.embed,
            frame,
            message_bytes,
            seed,
            strength,
            block_size,
        )

    tasks = [_embed_single(frame) for frame in media.images]
    try:
        results = await asyncio.gather(*tasks)
    except WatermarkingError as exc:
        logger.exception("embed_failed", extra={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    watermarked_frames = [frame for frame, _meta in results]
    wm_meta = results[0][1]

    if media.is_pdf:

        def _frames_to_pdf() -> bytes:
            return io_utils.images_to_pdf(watermarked_frames)

        pdf_bytes = await asyncio.get_running_loop().run_in_executor(
            None, _frames_to_pdf
        )
        accept = request.headers.get("accept", "")
        filename = f"{Path(media.metadata['original_filename']).stem}_watermarked.pdf"
        response_payload = {
            "psnr": round(metrics.psnr(media.images[0], watermarked_frames[0]), 2),
            "width": int(watermarked_frames[0].shape[1]),
            "height": int(watermarked_frames[0].shape[0]),
            "backend": wm_meta.get("backend"),
            "was_resized": media.metadata.get("was_resized"),
            "page_count": media.metadata.get("page_count", 1),
            "mime": RESPONSE_PDF_MIME,
        }

        if "application/json" in accept:
            b64_doc = base64.b64encode(pdf_bytes).decode("ascii")
            response_payload["file_base64"] = b64_doc
            response_payload["filename"] = filename
            return JSONResponse(content=response_payload)

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-PSNR": str(response_payload["psnr"]),
            "X-Backend": str(response_payload["backend"]),
        }
        return Response(
            content=pdf_bytes, media_type=RESPONSE_PDF_MIME, headers=headers
        )

    watermarked = watermarked_frames[0]
    png_bytes = await asyncio.get_running_loop().run_in_executor(
        None, _bgr_to_png_bytes, watermarked
    )
    psnr_value = metrics.psnr(media.images[0], watermarked)

    accept = request.headers.get("accept", "")
    response_payload = {
        "psnr": round(psnr_value, 2),
        "width": int(watermarked.shape[1]),
        "height": int(watermarked.shape[0]),
        "backend": wm_meta.get("backend"),
        "was_resized": media.metadata.get("was_resized"),
        "page_count": media.metadata.get("page_count", 1),
        "mime": RESPONSE_IMAGE_MIME,
    }

    if "application/json" in accept:
        b64_image = base64.b64encode(png_bytes).decode("ascii")
        response_payload["file_base64"] = b64_image
        response_payload["filename"] = (
            f"{Path(media.metadata['original_filename']).stem}_watermarked.png"
        )
        return JSONResponse(content=response_payload)

    filename = f"{Path(media.metadata['original_filename']).stem}_watermarked.png"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PSNR": str(response_payload["psnr"]),
        "X-Backend": str(response_payload["backend"]),
    }
    return Response(content=png_bytes, media_type=RESPONSE_IMAGE_MIME, headers=headers)


@app.post("/extract")
async def extract_endpoint(
    image: UploadFile = File(...),
    seed: int = Form(...),
    block_size: int = Form(DEFAULT_BLOCK_SIZE),
):
    contents = await image.read()
    try:
        media = io_utils.load_media_bytes(
            contents,
            filename=image.filename or "upload",
            mime_type=image.content_type,
        )
    except PDFInfoNotInstalledError as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF support requires poppler-utils (pdftoppm) to be installed.",
        ) from exc
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    block_size = _ensure_block_size(block_size)
    seed = _ensure_seed(seed)

    async def _extract_single(frame: np.ndarray, page_index: int) -> dict:
        try:
            message_bytes, metadata = await _run_with_timeout(
                wm_dwt_dct.extract, frame, seed, block_size
            )
            message = message_bytes.decode("utf-8", errors="replace")
            metadata.update({"page_index": page_index, "message": message})
            return metadata
        except Exception as exc:  # pragma: no cover - extraction can fail per page
            logger.warning("extract_failed", extra={"error": str(exc)})
            raise

    if media.is_pdf:
        tasks = [
            _extract_single(frame, idx)
            for idx, frame in enumerate(media.images)
        ]
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                return result
            except Exception:
                continue
        raise HTTPException(status_code=400, detail="Failed to recover watermark.")

    result = await _extract_single(media.images[0], 0)
    return result
