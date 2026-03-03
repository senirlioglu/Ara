import io
import json
import logging
import os
import tempfile
from typing import Dict

import streamlit as st
from google.cloud import vision
from PIL import Image

logger = logging.getLogger(__name__)


def init_gcp_credentials() -> str:
    """Initialize Google credentials from Streamlit secrets JSON string."""
    creds_json_str = st.secrets["gcp_service_account_json"]
    creds_obj = json.loads(creds_json_str)
    temp_path = os.path.join(tempfile.gettempdir(), "gcp_sa.json")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(creds_obj, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path
    print("GCP creds ready")
    logger.info("GCP creds ready")
    return temp_path


def _to_pixel_bbox(bbox_norm: Dict[str, float], img_w: int, img_h: int):
    x0 = int(max(0.0, min(1.0, bbox_norm["x0"])) * img_w)
    y0 = int(max(0.0, min(1.0, bbox_norm["y0"])) * img_h)
    x1 = int(max(0.0, min(1.0, bbox_norm["x1"])) * img_w)
    y1 = int(max(0.0, min(1.0, bbox_norm["y1"])) * img_h)
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    if right <= left:
        right = min(img_w, left + 1)
    if bottom <= top:
        bottom = min(img_h, top + 1)
    return left, top, right, bottom


def ocr_crop(png_bytes: bytes, bbox_norm: Dict[str, float], img_w: int, img_h: int) -> str:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    crop_box = _to_pixel_bbox(bbox_norm, img_w, img_h)
    cropped = image.crop(crop_box)

    crop_buffer = io.BytesIO()
    cropped.save(crop_buffer, format="PNG")
    crop_content = crop_buffer.getvalue()

    client = vision.ImageAnnotatorClient()
    response = client.document_text_detection(image=vision.Image(content=crop_content))

    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text.strip()
    return ""
