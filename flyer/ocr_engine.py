"""Google Cloud Vision OCR engine with DB caching.

Returns list of word dicts: [{text, x0, y0, x1, y1}, ...]
Coordinates are in pixels (original image dimensions).
"""

from __future__ import annotations

import logging
from typing import Optional

from flyer.db import get_ocr_cache, save_ocr_cache

log = logging.getLogger(__name__)


def _vision_ocr(image_bytes: bytes) -> list[dict]:
    """Call Google Cloud Vision DOCUMENT_TEXT_DETECTION.

    Returns list of {text, x0, y0, x1, y1} for each word.
    Requires GOOGLE_APPLICATION_CREDENTIALS env var or
    google-cloud-vision library with default credentials.
    """
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
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


def run_ocr(flyer_id: int, image_bytes: bytes, force: bool = False) -> list[dict]:
    """Run OCR with caching. Returns word list.

    If cached result exists and force=False, returns cached.
    Otherwise runs Vision OCR and saves to cache.
    """
    if not force:
        cached = get_ocr_cache(flyer_id)
        if cached is not None:
            log.info(f"OCR cache hit for flyer {flyer_id}: {len(cached)} words")
            return cached

    log.info(f"Running Vision OCR for flyer {flyer_id}...")
    words = _vision_ocr(image_bytes)
    log.info(f"OCR done: {len(words)} words found")

    # Cache to DB
    save_ocr_cache(flyer_id, words)

    return words
