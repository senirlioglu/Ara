"""PDF rendering via PyMuPDF — each page to high-quality PNG."""

from __future__ import annotations

import fitz  # PyMuPDF


def render_pdf_bytes_to_pages(pdf_bytes: bytes, zoom: float = 3.5) -> list[dict]:
    """Render every page of a PDF to PNG.

    Returns:
        [{page_no: int, png_bytes: bytes, w: int, h: int}, ...]
        page_no is 1-based.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    mat = fitz.Matrix(zoom, zoom)
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(matrix=mat, alpha=False)
        pages.append({
            "page_no": i + 1,
            "png_bytes": pix.tobytes("png"),
            "w": pix.width,
            "h": pix.height,
        })
    doc.close()
    return pages
