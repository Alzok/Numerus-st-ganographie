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

REQUEST_TIMEOUT_SECONDS = 15.0
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


@app.post("/embed")
async def embed_endpoint(
    request: Request,
    image: UploadFile = File(...),
    message: str = Form(...),
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

    message = message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Le message à intégrer ne peut pas être vide.")

    if media.is_pdf:
        try:
            pdf_bytes, meta_overlay = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: wm_dwt_dct.embed_pdf(
                    media.images,
                    message,
                ),
            )
        except WatermarkingError as exc:
            logger.exception("embed_failed", extra={"error": str(exc)})
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        accept = request.headers.get("accept", "")
        filename = f"{Path(media.metadata['original_filename']).stem}_watermarked.pdf"
        payload = {
            "psnr": None,
            "width": int(media.images[0].shape[1]),
            "height": int(media.images[0].shape[0]),
            "backend": "overlay_pdf",
            "was_resized": media.metadata.get("was_resized"),
            "page_count": media.metadata.get("page_count", 1),
            "mime": RESPONSE_PDF_MIME,
            "file_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "filename": filename,
        }
        if "application/json" in accept:
            return JSONResponse(content=payload)

        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "X-Backend": str(payload["backend"]),
        }
        return Response(content=pdf_bytes, media_type=RESPONSE_PDF_MIME, headers=headers)

    try:
        watermarked, meta_overlay = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: wm_dwt_dct.embed_image(
                media.images[0],
                message,
            ),
        )
    except WatermarkingError as exc:
        logger.exception("embed_failed", extra={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    png_bytes = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: io_utils.encode_png(
            watermarked,
            text=message,
            pattern=(meta_overlay or {}).get("pattern"),
        ),
    )

    try:
        pdf_bytes, _ = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: wm_dwt_dct.embed_pdf(
                [media.images[0]],
                message,
            ),
        )
    except WatermarkingError:
        pdf_bytes = None

    psnr_value = metrics.psnr(media.images[0], watermarked)
    accept = request.headers.get("accept", "")
    payload = {
        "psnr": round(psnr_value, 2),
        "width": int(watermarked.shape[1]),
        "height": int(watermarked.shape[0]),
        "backend": "overlay_image",
        "was_resized": media.metadata.get("was_resized"),
        "page_count": media.metadata.get("page_count", 1),
        "mime": RESPONSE_IMAGE_MIME,
        "file_base64": base64.b64encode(png_bytes).decode("ascii"),
        "filename": f"{Path(media.metadata['original_filename']).stem}_watermarked.png",
    }

    if pdf_bytes is not None:
        payload["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
        payload["pdf_filename"] = f"{Path(media.metadata['original_filename']).stem}_watermarked.pdf"
        payload["pdf_mime"] = RESPONSE_PDF_MIME

    if "application/json" in accept:
        return JSONResponse(content=payload)

    headers = {
        "Content-Disposition": f"attachment; filename=\"{payload['filename']}\"",
        "X-PSNR": str(payload["psnr"]),
        "X-Backend": str(payload["backend"]),
    }
    return Response(content=png_bytes, media_type=RESPONSE_IMAGE_MIME, headers=headers)


async def analyze_endpoint(image: UploadFile = File(...)):
    contents = await image.read()
    if len(contents) > io_utils.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (10 Mo max).")

    mime = (image.content_type or "").lower()
    filename = (image.filename or "").lower()

    if "pdf" in mime or filename.endswith(".pdf"):
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


@app.post("/analyze")
async def analyze_endpoint_alias(image: UploadFile = File(...)):
    return await analyze_endpoint(image)


@app.post("/extract")
async def extract_legacy(image: UploadFile = File(...)):
    return await analyze_endpoint(image)
