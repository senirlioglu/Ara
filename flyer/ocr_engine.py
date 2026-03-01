"""Google Cloud Vision OCR engine with DB caching.

NEW: Extracts text at BLOCK and PARAGRAPH level (not word level).
Returns list of block dicts: [{text, x0, y0, x1, y1, level}, ...]
Coordinates are in pixels (original image dimensions).

Also stores the full Vision API annotation JSON for re-processing
without re-calling the API.

Authentication (supports both):
  1. GOOGLE_APPLICATION_CREDENTIALS env var pointing to JSON key file
  2. GOOGLE_CREDENTIALS_JSON env var containing the JSON content directly
     (for Railway/Heroku where you can't upload files)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Optional

from flyer.db import get_ocr_cache, save_ocr_cache

log = logging.getLogger(__name__)


def _get_vision_client():
    """Create Vision client, handling file-based, env-based, and Streamlit secrets."""
    from google.cloud import vision

    # Already configured? Skip re-setup.
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return vision.ImageAnnotatorClient()

    # Try sources in order: env var → Streamlit secrets
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

    if not creds_json:
        try:
            import streamlit as st
            creds_json = st.secrets.get("GOOGLE_CREDENTIALS_JSON", "")
        except Exception:
            pass

    if creds_json and creds_json.strip().startswith("{"):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(creds_json)
        tmp.close()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
        log.info("Vision credentials loaded from GOOGLE_CREDENTIALS_JSON")

    return vision.ImageAnnotatorClient()


# ---------------------------------------------------------------------------
# Block / Paragraph extraction from Vision API response
# ---------------------------------------------------------------------------

def _extract_blocks_from_annotation(annotation) -> list[dict]:
    """Extract PARAGRAPH-level text chunks from full_text_annotation.

    Each paragraph becomes one candidate with its bounding box and
    concatenated word text.  Falls back to BLOCK level if a block
    has no paragraph children.

    Returns:
        [{text, x0, y0, x1, y1, level}, ...]
        level is 'paragraph' or 'block'.
    """
    blocks: list[dict] = []

    for page in annotation.pages:
        for block in page.blocks:
            paragraphs = list(block.paragraphs)

            if not paragraphs:
                # Fallback: use the block itself
                text = ""
                for p in block.paragraphs:
                    for w in p.words:
                        text += "".join(s.text for s in w.symbols) + " "
                text = text.strip()
                if not text:
                    continue
                verts = block.bounding_box.vertices
                xs = [v.x for v in verts]
                ys = [v.y for v in verts]
                blocks.append({
                    "text": text,
                    "x0": min(xs),
                    "y0": min(ys),
                    "x1": max(xs),
                    "y1": max(ys),
                    "level": "block",
                })
                continue

            for para in paragraphs:
                words_text = []
                for word in para.words:
                    word_text = "".join(s.text for s in word.symbols)
                    if word_text.strip():
                        words_text.append(word_text)

                text = " ".join(words_text).strip()
                if not text:
                    continue

                verts = para.bounding_box.vertices
                xs = [v.x for v in verts]
                ys = [v.y for v in verts]
                blocks.append({
                    "text": text,
                    "x0": min(xs),
                    "y0": min(ys),
                    "x1": max(xs),
                    "y1": max(ys),
                    "level": "paragraph",
                })

    return blocks


def _vision_ocr_blocks(image_bytes: bytes) -> list[dict]:
    """Call Google Cloud Vision DOCUMENT_TEXT_DETECTION.

    Returns list of {text, x0, y0, x1, y1, level} at paragraph/block level.
    """
    from google.cloud import vision

    client = _get_vision_client()
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    if not response.full_text_annotation or not response.full_text_annotation.pages:
        return []

    return _extract_blocks_from_annotation(response.full_text_annotation)


# ---------------------------------------------------------------------------
# Legacy word-level extraction (kept for backward compat with old cache)
# ---------------------------------------------------------------------------

def _vision_ocr_words(image_bytes: bytes) -> list[dict]:
    """Call Google Cloud Vision DOCUMENT_TEXT_DETECTION — word level.

    Returns list of {text, x0, y0, x1, y1} for each word.
    """
    from google.cloud import vision

    client = _get_vision_client()
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    words: list[dict] = []

    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join(s.text for s in word.symbols)
                    if not text.strip():
                        continue
                    verts = word.bounding_box.vertices
                    xs = [v.x for v in verts]
                    ys = [v.y for v in verts]
                    words.append({
                        "text": text,
                        "x0": min(xs),
                        "y0": min(ys),
                        "x1": max(xs),
                        "y1": max(ys),
                    })

    return words


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ocr(flyer_id: int, image_bytes: bytes, force: bool = False) -> list[dict]:
    """Run OCR with caching. Returns block/paragraph list.

    If cached result exists and force=False, returns cached.
    Otherwise runs Vision OCR and saves to cache.

    Returns:
        [{text, x0, y0, x1, y1, level}, ...]
    """
    if not force:
        cached = get_ocr_cache(flyer_id)
        if cached is not None:
            log.info(f"OCR cache hit for flyer {flyer_id}: {len(cached)} items")
            # Detect old word-level cache (no 'level' field) → re-run
            if cached and "level" not in cached[0]:
                log.info("Old word-level cache detected, re-running at block level")
            else:
                return cached

    log.info(f"Running Vision OCR (block/paragraph) for flyer {flyer_id}...")
    blocks = _vision_ocr_blocks(image_bytes)
    log.info(f"OCR done: {len(blocks)} blocks/paragraphs found")

    # Cache to DB
    save_ocr_cache(flyer_id, blocks)

    return blocks
