"""PDF → JPEG conversion for flyer pipeline.

Uses PyMuPDF (fitz) to render each PDF page as a high-resolution JPEG image.
Each page becomes a separate flyer entry in the pipeline.
"""

from __future__ import annotations

import logging
from io import BytesIO

import fitz  # PyMuPDF
from PIL import Image

log = logging.getLogger(__name__)


def pdf_page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count


def pdf_page_to_jpeg(pdf_bytes: bytes, page_no: int, dpi: int = 200) -> bytes:
    """Render a single PDF page to JPEG bytes.

    Args:
        pdf_bytes: Raw PDF file content.
        page_no: 1-based page number.
        dpi: Resolution (default 200 — good balance of quality vs size).

    Returns:
        JPEG image bytes.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_idx = page_no - 1
    if page_idx < 0 or page_idx >= len(doc):
        doc.close()
        raise ValueError(f"Sayfa {page_no} bulunamadı (toplam {len(doc)} sayfa)")

    page = doc[page_idx]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    # Convert to JPEG via PIL for better compression
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    jpeg_bytes = buf.getvalue()

    doc.close()
    return jpeg_bytes


def pdf_to_jpegs(pdf_bytes: bytes, dpi: int = 200) -> list[tuple[str, bytes]]:
    """Convert all pages of a PDF to JPEG images.

    Args:
        pdf_bytes: Raw PDF file content.
        dpi: Resolution for rendering.

    Returns:
        List of (page_label, jpeg_bytes) tuples.
        page_label is like "s1", "s2", etc.
    """
    count = pdf_page_count(pdf_bytes)
    results = []
    for page_no in range(1, count + 1):
        jpeg = pdf_page_to_jpeg(pdf_bytes, page_no, dpi=dpi)
        label = f"s{page_no}"
        results.append((label, jpeg))
        log.info(f"PDF page {page_no}/{count} → JPEG ({len(jpeg):,} bytes)")
    return results
