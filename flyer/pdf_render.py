"""PDF → PNG rendering for flyer pipeline.

Uses PyMuPDF (fitz) with configurable zoom factor.
Default zoom=3.5 produces high-res images suitable for Vision OCR.
"""

from __future__ import annotations

import logging
from io import BytesIO

import fitz  # PyMuPDF
from PIL import Image

log = logging.getLogger(__name__)


def page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    n = len(doc)
    doc.close()
    return n


def render_page(
    pdf_bytes: bytes,
    page_no: int,
    zoom: float = 3.5,
) -> tuple[bytes, int, int]:
    """Render a single PDF page to PNG bytes.

    Args:
        pdf_bytes: Raw PDF file content.
        page_no: 1-based page number.
        zoom: Zoom factor (3.5 → ~252 DPI for A4).

    Returns:
        (png_bytes, width, height) in pixels.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_idx = page_no - 1
    if page_idx < 0 or page_idx >= len(doc):
        doc.close()
        raise ValueError(f"Sayfa {page_no} bulunamadı (toplam {len(doc)} sayfa)")

    page = doc[page_idx]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    w, h = pix.width, pix.height
    doc.close()
    log.info(f"Rendered page {page_no} at zoom={zoom}: {w}x{h} ({len(png_bytes):,} bytes)")
    return png_bytes, w, h


def render_all_pages(
    pdf_bytes: bytes,
    zoom: float = 3.5,
) -> list[tuple[int, bytes, int, int]]:
    """Render all pages of a PDF.

    Returns:
        List of (page_no, png_bytes, width, height).
        page_no is 1-based.
    """
    n = page_count(pdf_bytes)
    results = []
    for p in range(1, n + 1):
        png, w, h = render_page(pdf_bytes, p, zoom=zoom)
        results.append((p, png, w, h))
    return results
