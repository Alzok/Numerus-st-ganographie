from __future__ import annotations

import asyncio
import base64
import logging
from logging.config import dictConfig
from pathlib import Path
from typing import Any, Callable
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
PUBLIC_SEED = 123_456
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


def _ensure_seed(value: int | None) -> int:
    if value is None:
        return PUBLIC_SEED
    if value < 0:
        raise HTTPException(status_code=422, detail="seed must be non-negative")
    return value & 0xFFFFFFFF

def _friendly_error(exc: WatermarkingError) -> str:
    message = str(exc)
    if "Decoded watermark length" in message or "CRC" in message:
        return (
            "Impossible de récupérer un filigrane valide. Assurez-vous que le fichier provient bien de l'outil d'intégration et qu'il n'a pas été trop altéré."
        )
    if "No watermark recovered" in message:
        return "Aucun filigrane n'a été détecté dans ce fichier."
    return message


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

    if not capacities:
        raise HTTPException(
            status_code=400, detail="Aucune image disponible pour estimer la capacité."
        )

    capacity_bits = min(item.get("capacity_bits", 0) for item in capacities)
    max_message_bytes = min(item.get("max_message_bytes", 0) for item in capacities)
    per_replication = capacities[0].get("max_message_bytes_per_replication", {})

    sample = capacities[0]
    return {
        "capacity_bits": int(capacity_bits),
        "max_message_bytes": int(max_message_bytes),
        "max_message_bytes_by_replication": {str(k): int(v) for k, v in per_replication.items()},
        "replication_factor": len(per_replication) or 1,
        "payload_overhead_bytes": 0,
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
    seed: int | None = Form(None),
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
    _ensure_block_size(block_size)
    _ensure_seed(seed)

    message = message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Le message à intégrer ne peut pas être vide.")

    if media.is_pdf:
        try:
            pdf_bytes = await asyncio.get_running_loop().run_in_executor(
                None, wm_dwt_dct.embed_pdf, media.images, message
            )
        except WatermarkingError as exc:
            logger.exception("embed_failed", extra={"error": str(exc)})
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        accept = request.headers.get("accept", "")
        filename = f"{Path(media.metadata['original_filename']).stem}_watermarked.pdf"
        response_payload = {
            "psnr": None,
            "width": int(media.images[0].shape[1]),
            "height": int(media.images[0].shape[0]),
            "backend": "overlay_pdf",
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
            "X-Backend": str(response_payload["backend"]),
        }
        return Response(content=pdf_bytes, media_type=RESPONSE_PDF_MIME, headers=headers)

    try:
        watermarked, meta_overlay = await asyncio.get_running_loop().run_in_executor(
            None, wm_dwt_dct.embed_image, media.images[0], message
        )
    except WatermarkingError as exc:
        logger.exception("embed_failed", extra={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    png_bytes = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: io_utils.encode_png(
            watermarked,
            text=message,
            pattern=meta_overlay.get("pattern") if meta_overlay else None,
        ),
    )
    psnr_value = metrics.psnr(media.images[0], watermarked)

    accept = request.headers.get("accept", "")
    response_payload = {
        "psnr": round(psnr_value, 2),
        "width": int(watermarked.shape[1]),
        "height": int(watermarked.shape[0]),
        "backend": "overlay_image",
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
    seed: int | None = Form(None),
    block_size: int = Form(DEFAULT_BLOCK_SIZE),
):
    contents = await image.read()
    _ensure_block_size(block_size)
    _ensure_seed(seed)

    mime = image.content_type or ""
    filename = image.filename or ""

    if "pdf" in mime or filename.lower().endswith(".pdf"):
        try:
            message_text = await asyncio.get_running_loop().run_in_executor(
                None, wm_dwt_dct.extract_from_pdf_bytes, contents
            )
        except WatermarkingError as exc:
            raise HTTPException(status_code=400, detail=_friendly_error(exc)) from exc
        return {
            "message": message_text,
            "confidence": 1.0,
            "page_index": 0,
        }

    try:
        message_text = await asyncio.get_running_loop().run_in_executor(
            None, wm_dwt_dct.extract_from_png_bytes, contents
        )
    except WatermarkingError as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc)) from exc

    return {
        "message": message_text,
        "confidence": 1.0,
        "page_index": 0,
    }
