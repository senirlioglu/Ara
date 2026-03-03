"""Google Cloud Vision OCR — credentials init + crop OCR."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import tempfile

import streamlit as st
from PIL import Image

log = logging.getLogger(__name__)

_CREDS_READY = False


def init_gcp_credentials() -> str | None:
    """Read GCP service-account JSON from Streamlit secrets, write to temp file,
    set GOOGLE_APPLICATION_CREDENTIALS env var. Returns path or None."""
    global _CREDS_READY
    if _CREDS_READY:
        return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    # Try multiple secret key names
    sa_json = None
    for key in ("gcp_service_account_json", "GOOGLE_CREDENTIALS_JSON"):
        val = st.secrets.get(key)
        if val:
            sa_json = val if isinstance(val, str) else json.dumps(dict(val))
            break

    # Also check env var pointing to existing file
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing and os.path.isfile(existing):
        _CREDS_READY = True
        log.info("GCP creds ready (existing file: %s)", existing)
        return existing

    if not sa_json:
        log.warning("No GCP credentials found in secrets")
        return None

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="gcp_sa_", delete=False,
    )
    tmp.write(sa_json)
    tmp.close()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
    _CREDS_READY = True
    log.info("GCP creds ready (%s)", tmp.name)
    return tmp.name


def ocr_crop(
    png_bytes: bytes,
    bbox_norm: dict,
    img_w: int,
    img_h: int,
) -> str:
    """Crop image by normalized bbox and run Vision DOCUMENT_TEXT_DETECTION.

    Args:
        png_bytes: Full page PNG.
        bbox_norm: {x0, y0, x1, y1} normalized 0..1.
        img_w, img_h: Page pixel dimensions.

    Returns:
        Detected text string (may be empty).
    """
    init_gcp_credentials()

    from google.cloud import vision

    img = Image.open(io.BytesIO(png_bytes))
    # Crop
    x0 = int(bbox_norm["x0"] * img_w)
    y0 = int(bbox_norm["y0"] * img_h)
    x1 = int(bbox_norm["x1"] * img_w)
    y1 = int(bbox_norm["y1"] * img_h)
    crop = img.crop((x0, y0, x1, y1))

    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    crop_bytes = buf.getvalue()

    client = vision.ImageAnnotatorClient()
    response = client.document_text_detection(
        image=vision.Image(content=crop_bytes),
    )
    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text.strip()
    return ""


def make_ocr_cache_key(png_bytes: bytes, bbox_norm: dict) -> str:
    """Deterministic cache key from image + bbox."""
    b = (
        f"{bbox_norm['x0']:.4f},{bbox_norm['y0']:.4f},"
        f"{bbox_norm['x1']:.4f},{bbox_norm['y1']:.4f}"
    ).encode()
    h = hashlib.sha1(png_bytes + b).hexdigest()[:16]
    return h
