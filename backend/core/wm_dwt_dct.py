from __future__ import annotations

import logging
import math
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import pywt

logger = logging.getLogger(__name__)

try:  # Optional dependency
    from imwatermark import WatermarkDecoder, WatermarkEncoder

    _IMW_AVAILABLE = True
except Exception:  # pragma: no cover - optional path
    WatermarkDecoder = None  # type: ignore
    WatermarkEncoder = None  # type: ignore
    _IMW_AVAILABLE = False

DEFAULT_BLOCK_SIZE = 8
MAX_MESSAGE_BYTES = 4096
PAYLOAD_OVERHEAD_BYTES = 8  # 4 bytes length + 4 bytes checksum
REPLICATION_FACTOR = 3


@dataclass
class WatermarkPayload:
    message: bytes
    payload_bytes: bytes
    bits: np.ndarray


class WatermarkingError(RuntimeError):
    """Raised when watermark embedding/extraction fails."""


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _build_payload(message: bytes) -> WatermarkPayload:
    if len(message) > MAX_MESSAGE_BYTES:
        raise WatermarkingError(
            f"Message too long. Max supported size is {MAX_MESSAGE_BYTES} bytes."
        )
    length_bytes = len(message).to_bytes(4, "big", signed=False)
    checksum = zlib.crc32(message) & 0xFFFFFFFF
    payload = length_bytes + message + checksum.to_bytes(4, "big")
    bit_array = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    return WatermarkPayload(
        message=message, payload_bytes=payload, bits=bit_array.astype(np.uint8)
    )


def _pad_to_block(
    arr: np.ndarray, block_size: int
) -> Tuple[np.ndarray, Tuple[int, int]]:
    h, w = arr.shape
    pad_h = (block_size - (h % block_size)) % block_size
    pad_w = (block_size - (w % block_size)) % block_size
    padded = np.pad(arr, ((0, pad_h), (0, pad_w)), mode="edge")
    return padded, (pad_h, pad_w)


def _pad_to_even(arr: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
    h, w = arr.shape
    pad_h = h % 2
    pad_w = w % 2
    if pad_h or pad_w:
        arr = np.pad(arr, ((0, pad_h), (0, pad_w)), mode="edge")
    return arr, (pad_h, pad_w)


def _unpad(arr: np.ndarray, pad: Tuple[int, int]) -> np.ndarray:
    pad_h, pad_w = pad
    if pad_h:
        arr = arr[:-pad_h, :]
    if pad_w:
        arr = arr[:, :-pad_w]
    return arr


def _embed_bit_in_block(
    block: np.ndarray,
    bit: int,
    strength: float,
) -> np.ndarray:
    dct = cv2.dct(block.astype(np.float32))
    a_pos = (0, 1)
    b_pos = (1, 0)
    coef_a = dct[a_pos]
    coef_b = dct[b_pos]

    energy = float(np.mean(np.abs(dct))) + 1e-6
    margin = max(strength * 4.0, strength * 0.25 * energy, 3.0)
    if bit == 1:
        if coef_a <= coef_b:
            delta = (coef_b - coef_a) + margin
            coef_a += delta / 2.0
            coef_b -= delta / 2.0
    else:
        if coef_a >= coef_b:
            delta = (coef_a - coef_b) + margin
            coef_a -= delta / 2.0
            coef_b += delta / 2.0

    dct[a_pos] = coef_a
    dct[b_pos] = coef_b
    modified = cv2.idct(dct)
    return modified


def _extract_bit_from_block(block: np.ndarray) -> Tuple[int, float]:
    dct = cv2.dct(block.astype(np.float32))
    coef_a = dct[0, 1]
    coef_b = dct[1, 0]
    bit = int(coef_a > coef_b)
    margin = float(abs(coef_a - coef_b))
    return bit, margin


# ---------------------------------------------------------------------------
# Fallback implementation
# ---------------------------------------------------------------------------


def _select_replication(bit_count: int, capacity: int) -> int:
    if bit_count <= 0:
        raise WatermarkingError("No watermark payload to embed.")
    max_replication = max(1, capacity // bit_count)
    return max(1, min(REPLICATION_FACTOR, max_replication))


def _compute_capacity_metrics(num_blocks: int) -> Dict[str, Any]:
    capacity_bits = int(num_blocks)
    base_bytes = capacity_bits // 8 - PAYLOAD_OVERHEAD_BYTES
    max_message_bytes = max(0, min(MAX_MESSAGE_BYTES, base_bytes))

    per_replication: Dict[int, int] = {}
    for replication in range(1, REPLICATION_FACTOR + 1):
        slots = capacity_bits // replication
        slots_bytes = slots // 8 - PAYLOAD_OVERHEAD_BYTES
        per_replication[replication] = max(0, min(MAX_MESSAGE_BYTES, slots_bytes))

    return {
        "capacity_bits": capacity_bits,
        "max_message_bytes": max_message_bytes,
        "max_message_bytes_per_replication": per_replication,
    }


def estimate_capacity(
    img_bgr: np.ndarray,
    block_size: int,
) -> Dict[str, Any]:
    if img_bgr.dtype != np.uint8:
        raise WatermarkingError("Expected uint8 BGR image for capacity estimation.")

    ycbcr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y_channel = ycbcr[:, :, 0].astype(np.float32)
    y_even, even_pad = _pad_to_even(y_channel)

    if y_even.shape[0] < block_size or y_even.shape[1] < block_size:
        raise WatermarkingError("Image too small for watermark embedding.")

    LL, (cH, cV, cD) = pywt.dwt2(y_even, "haar", mode="periodization")
    LL_padded, _ = _pad_to_block(LL, block_size)

    blocks_h = LL_padded.shape[0] // block_size
    blocks_w = LL_padded.shape[1] // block_size
    num_blocks = blocks_h * blocks_w

    metrics = _compute_capacity_metrics(num_blocks)
    metrics.update(
        {
            "block_size": int(block_size),
            "width": int(img_bgr.shape[1]),
            "height": int(img_bgr.shape[0]),
            "even_width": int(y_even.shape[1]),
            "even_height": int(y_even.shape[0]),
            "pad_added": {"h": int(even_pad[0]), "w": int(even_pad[1])},
        }
    )
    return metrics


def _embed_fallback(
    img_bgr: np.ndarray,
    payload: WatermarkPayload,
    seed: int,
    strength: float,
    block_size: int,
) -> Tuple[np.ndarray, Dict]:
    if img_bgr.dtype != np.uint8:
        raise WatermarkingError("Expected uint8 BGR image for embedding.")

    ycbcr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y_channel = ycbcr[:, :, 0].astype(np.float32)
    y_even, even_pad = _pad_to_even(y_channel)

    if y_even.shape[0] < block_size or y_even.shape[1] < block_size:
        raise WatermarkingError("Image too small for watermark embedding.")

    LL, (cH, cV, cD) = pywt.dwt2(y_even, "haar", mode="periodization")
    LL_padded, pad = _pad_to_block(LL, block_size)

    blocks_h = LL_padded.shape[0] // block_size
    blocks_w = LL_padded.shape[1] // block_size
    num_blocks = blocks_h * blocks_w

    bits = payload.bits
    replication = _select_replication(bits.size, num_blocks)
    total_slots = bits.size * replication
    if total_slots > num_blocks:
        raise WatermarkingError(
            "Message too large for host image. Try reducing message size or using a larger image."
        )

    rng = np.random.default_rng(seed)
    indices = np.arange(num_blocks)
    rng.shuffle(indices)

    LL_embed = LL_padded.copy()
    strength = max(0.05, min(strength, 5.0))

    selected = indices[:total_slots]
    selected = selected.reshape(bits.size, replication)

    for bit, block_group in zip(bits, selected):
        for index in block_group:
            row = index // blocks_w
            col = index % blocks_w
            y0 = row * block_size
            x0 = col * block_size
            block = LL_embed[y0 : y0 + block_size, x0 : x0 + block_size]
            modified = _embed_bit_in_block(block, int(bit), strength)
            LL_embed[y0 : y0 + block_size, x0 : x0 + block_size] = modified

    LL_embed = _unpad(LL_embed, pad)
    y_reconstructed_even = pywt.idwt2(
        (LL_embed, (cH, cV, cD)), "haar", mode="periodization"
    )
    y_reconstructed = _unpad(y_reconstructed_even, even_pad)
    y_reconstructed = np.clip(y_reconstructed, 0, 255).astype(np.uint8)

    ycbcr_out = ycbcr.copy()
    ycbcr_out[:, :, 0] = y_reconstructed
    result = cv2.cvtColor(ycbcr_out, cv2.COLOR_YCrCb2BGR)

    metadata = {
        "backend": "fallback",
        "bits_embedded": int(bits.size),
        "capacity": int(num_blocks),
        "block_size": int(block_size),
        "replication": replication,
    }
    return result, metadata


def _extract_with_replication(
    img_bgr: np.ndarray,
    seed: int,
    block_size: int,
    replication: int,
) -> Tuple[bytes, Dict]:
    if img_bgr.dtype != np.uint8:
        raise WatermarkingError("Expected uint8 BGR image for extraction.")

    ycbcr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y_channel = ycbcr[:, :, 0].astype(np.float32)
    y_even, even_pad = _pad_to_even(y_channel)

    if y_even.shape[0] < block_size or y_even.shape[1] < block_size:
        raise WatermarkingError("Image too small to contain replicated watermark data.")

    LL, (cH, cV, cD) = pywt.dwt2(y_even, "haar", mode="periodization")
    LL_padded, pad = _pad_to_block(LL, block_size)

    blocks_h = LL_padded.shape[0] // block_size
    blocks_w = LL_padded.shape[1] // block_size
    num_blocks = blocks_h * blocks_w

    rng = np.random.default_rng(seed)
    indices = np.arange(num_blocks)
    rng.shuffle(indices)

    bits: List[int] = []
    margins: List[float] = []
    expected_total_bits: int | None = None

    usable_length = (num_blocks // replication) * replication
    if usable_length == 0:
        raise WatermarkingError("Image too small to contain replicated watermark data.")
    groups = indices[:usable_length].reshape(-1, replication)

    for group in groups:
        votes = []
        group_margins = []
        for index in group:
            row = index // blocks_w
            col = index % blocks_w
            y0 = row * block_size
            x0 = col * block_size
            block = LL_padded[y0 : y0 + block_size, x0 : x0 + block_size]
            bit, margin = _extract_bit_from_block(block)
            votes.append(bit)
            group_margins.append(margin)

        threshold = (replication // 2) + 1
        majority = int(sum(votes) >= threshold)
        bits.append(majority)
        margins.append(float(np.mean(group_margins)))

        if expected_total_bits is None and len(bits) >= 32:
            header_bits = np.array(bits[:32], dtype=np.uint8)
            header_bytes = np.packbits(header_bits).tobytes()
            message_len = int.from_bytes(header_bytes, "big", signed=False)
            if message_len < 0 or message_len > MAX_MESSAGE_BYTES:
                raise WatermarkingError("Decoded watermark length is out of bounds.")
            expected_total_bits = 8 * (4 + message_len + 4)

        if expected_total_bits is not None and len(bits) >= expected_total_bits:
            break

    if expected_total_bits is None:
        raise WatermarkingError("Failed to recover watermark header.")

    if len(bits) < expected_total_bits:
        raise WatermarkingError("Insufficient data to recover embedded message.")

    bit_array = np.array(bits[:expected_total_bits], dtype=np.uint8)
    payload_bytes = np.packbits(bit_array).tobytes()

    message_length = int.from_bytes(payload_bytes[:4], "big", signed=False)
    message_bytes = payload_bytes[4 : 4 + message_length]
    checksum = int.from_bytes(
        payload_bytes[4 + message_length : 8 + message_length], "big"
    )

    crc_ok = (zlib.crc32(message_bytes) & 0xFFFFFFFF) == checksum

    avg_margin = float(np.mean(margins)) if margins else 0.0
    raw_vote_accuracy = (
        float(np.mean(margins) / (np.max(margins) + 1e-6)) if margins else 0.0
    )
    confidence = 1.0 if crc_ok else float(1.0 / (1.0 + math.exp(-avg_margin / 10.0)))

    metadata = {
        "backend": "fallback",
        "bits_read": int(expected_total_bits),
        "crc_ok": bool(crc_ok),
        "confidence": float(confidence),
        "message_length": int(message_length),
        "replication": replication,
        "avg_margin": avg_margin,
        "vote_quality": raw_vote_accuracy,
    }
    return message_bytes, metadata


# ---------------------------------------------------------------------------
# Public API (with optional imwatermark acceleration)
# ---------------------------------------------------------------------------


def embed(
    img_bgr: np.ndarray,
    message: bytes,
    seed: int,
    strength: float,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> Tuple[np.ndarray, Dict]:
    payload = _build_payload(message)

    if _IMW_AVAILABLE and WatermarkEncoder is not None:
        try:  # pragma: no cover - relies on optional dependency
            encoder = WatermarkEncoder()
            encoder.set_watermark("bytes", payload.payload_bytes)
            watermarked = encoder.encode(
                img_bgr,
                "dwtDct",
                seed=seed,
                strength=strength,
                block_shape=(block_size, block_size),
            )
            metadata = {
                "backend": "imwatermark",
                "bits_embedded": int(payload.bits.size),
            }
            return watermarked, metadata
        except Exception as exc:
            logger.warning("imwatermark encode failed, using fallback: %s", exc)

    return _embed_fallback(img_bgr, payload, seed, strength, block_size)


def extract(
    img_bgr: np.ndarray,
    seed: int,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> Tuple[bytes, Dict]:
    if _IMW_AVAILABLE and WatermarkDecoder is not None:
        try:  # pragma: no cover - optional dependency
            decoder = WatermarkDecoder(
                "bytes", MAX_MESSAGE_BYTES + PAYLOAD_OVERHEAD_BYTES
            )
            recovered = decoder.decode(
                img_bgr,
                "dwtDct",
                seed=seed,
                block_shape=(block_size, block_size),
            )
            if not recovered:
                raise WatermarkingError("No watermark recovered.")
            payload_bytes = bytes(recovered)
            if len(payload_bytes) < 8:
                raise WatermarkingError("Recovered payload too small.")
            message_length = int.from_bytes(payload_bytes[:4], "big")
            message_bytes = payload_bytes[4 : 4 + message_length]
            checksum = int.from_bytes(
                payload_bytes[4 + message_length : 8 + message_length], "big"
            )
            crc_ok = (zlib.crc32(message_bytes) & 0xFFFFFFFF) == checksum
            metadata = {
                "backend": "imwatermark",
                "crc_ok": bool(crc_ok),
                "message_length": int(message_length),
                "confidence": 1.0 if crc_ok else 0.0,
            }
            return message_bytes, metadata
        except Exception as exc:
            logger.warning("imwatermark decode failed, using fallback: %s", exc)

    last_error: Exception | None = None
    for replication in range(REPLICATION_FACTOR, 0, -1):
        try:
            return _extract_with_replication(img_bgr, seed, block_size, replication)
        except WatermarkingError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise WatermarkingError("Failed to recover watermark.")
