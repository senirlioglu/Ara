"""PDF & image rendering — each page to optimised JPEG."""

from __future__ import annotations

import io

import fitz  # PyMuPDF
from PIL import Image


# --- Upload validation limits ---
MAX_PDF_BYTES = 50 * 1024 * 1024       # 50 MB
MAX_IMAGE_BYTES = 20 * 1024 * 1024     # 20 MB
MAX_MEGAPIXELS = 100                    # decompression bomb koruması
MAX_PDF_PAGES = 100                     # DoS koruması
_PDF_MAGIC = b"%PDF"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails validation."""


def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes:
        raise UploadValidationError("Boş PDF dosyası")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise UploadValidationError(
            f"PDF çok büyük ({len(pdf_bytes)/1024/1024:.1f} MB). "
            f"Limit: {MAX_PDF_BYTES // 1024 // 1024} MB"
        )
    # PDF imzası dosyanın ilk 1 KB'ında olmalı (bazı PDF'ler whitespace ile başlar)
    if _PDF_MAGIC not in pdf_bytes[:1024]:
        raise UploadValidationError("Geçersiz PDF imzası")


def _validate_image_bytes(image_bytes: bytes) -> None:
    if not image_bytes:
        raise UploadValidationError("Boş görsel dosyası")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise UploadValidationError(
            f"Görsel çok büyük ({len(image_bytes)/1024/1024:.1f} MB). "
            f"Limit: {MAX_IMAGE_BYTES // 1024 // 1024} MB"
        )
    head = image_bytes[:16]
    if not (head.startswith(_JPEG_MAGIC) or head.startswith(_PNG_MAGIC)):
        raise UploadValidationError("Geçersiz görsel imzası (yalnızca JPEG/PNG)")


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

    Raises:
        UploadValidationError: PDF geçersizse / çok büyükse / çok sayfalıysa.

    Returns:
        [{page_no: int, png_bytes: bytes, w: int, h: int}, ...]
        page_no is 1-based.  Key is still ``png_bytes`` for backwards compat.
    """
    _validate_pdf_bytes(pdf_bytes)
    # Aşırı zoom → memory exhaustion. Çağrılar default 2.0 geçiyor; defense in depth.
    zoom = max(0.5, min(float(zoom), 5.0))
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if len(doc) > MAX_PDF_PAGES:
            raise UploadValidationError(
                f"PDF çok fazla sayfa içeriyor ({len(doc)}). "
                f"Limit: {MAX_PDF_PAGES}"
            )
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
        return pages
    finally:
        doc.close()


def render_image_bytes_to_page(
    image_bytes: bytes, filename: str, page_no: int = 1,
    max_width: int = 2400, jpeg_quality: int = 85,
) -> dict:
    """Convert a single image file (JPEG/PNG) to an optimised JPEG page dict.

    Raises:
        UploadValidationError: görsel geçersizse / çok büyükse / çok çözünürlüklüyse.

    Returns:
        {page_no: int, png_bytes: bytes, w: int, h: int}
    """
    _validate_image_bytes(image_bytes)
    pil = Image.open(io.BytesIO(image_bytes))
    # Decompression bomb koruması — megapixel sınırı
    w0, h0 = pil.size
    if w0 * h0 > MAX_MEGAPIXELS * 1_000_000:
        raise UploadValidationError(
            f"Görsel çözünürlüğü çok yüksek ({w0 * h0 / 1_000_000:.1f} MP). "
            f"Limit: {MAX_MEGAPIXELS} MP"
        )
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
