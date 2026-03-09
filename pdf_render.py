"""PDF & image rendering — each page to optimised JPEG."""

from __future__ import annotations

import io

import fitz  # PyMuPDF
from PIL import Image


def _pixmap_to_jpeg(pix, quality: int = 85) -> bytes:
    """Convert a PyMuPDF Pixmap to compressed JPEG bytes via Pillow."""
    pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def render_pdf_bytes_to_pages(
    pdf_bytes: bytes, zoom: float = 2.0, jpeg_quality: int = 85,
) -> list[dict]:
    """Render every page of a PDF to JPEG.

    Returns:
        [{page_no: int, png_bytes: bytes, w: int, h: int}, ...]
        page_no is 1-based.  Key is still ``png_bytes`` for backwards compat.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    mat = fitz.Matrix(zoom, zoom)
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(matrix=mat, alpha=False)
        jpeg_data = _pixmap_to_jpeg(pix, quality=jpeg_quality)
        pages.append({
            "page_no": i + 1,
            "png_bytes": jpeg_data,  # kept as "png_bytes" for compat
            "w": pix.width,
            "h": pix.height,
        })
    doc.close()
    return pages


def render_image_bytes_to_page(
    image_bytes: bytes, filename: str, page_no: int = 1,
    max_width: int = 2400, jpeg_quality: int = 85,
) -> dict:
    """Convert a single image file (JPEG/PNG) to an optimised JPEG page dict.

    Returns:
        {page_no: int, png_bytes: bytes, w: int, h: int}
    """
    pil = Image.open(io.BytesIO(image_bytes))
    if pil.mode in ("RGBA", "P", "LA"):
        pil = pil.convert("RGB")

    # Resize if wider than max_width (keep aspect ratio)
    w, h = pil.size
    if w > max_width:
        scale = max_width / w
        pil = pil.resize((max_width, int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    jpeg_data = buf.getvalue()
    final_w, final_h = pil.size
    return {
        "page_no": page_no,
        "png_bytes": jpeg_data,
        "w": final_w,
        "h": final_h,
    }
