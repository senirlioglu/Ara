"""Hotspot generation from PDF using PyMuPDF (fitz).

For each poster_item, searches the PDF page for text (product code, model code,
or price) and creates a bounding-box hotspot with normalised coordinates (0..1).
"""

from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF

from poster.db import (
    get_supabase,
    get_poster_items,
    upsert_hotspot,
    update_poster_item,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _price_digits(price_str: str) -> Optional[str]:
    """Extract digits from a price string for text search.

    '42.999 TL' → '42999'
    '1.299,00 ₺' → '1299'
    """
    if not price_str:
        return None
    digits = re.sub(r"[^\d]", "", price_str)
    # Remove trailing zeros (e.g. '129900' → '1299')
    digits = digits.rstrip("0") or digits
    return digits if len(digits) >= 3 else None


def _best_rect(rects: list[fitz.Rect]) -> Optional[fitz.Rect]:
    """Pick the best rect – prefer largest area, first on page as tiebreaker."""
    if not rects:
        return None
    return max(rects, key=lambda r: r.get_area())


def _expand_rect(rect: fitz.Rect, page_w: float, page_h: float,
                 pad_x: float = 60, pad_y: float = 80) -> fitz.Rect:
    """Expand rect by padding to cover the product card area.

    Padding values are in PDF points (~1/72 inch).
    """
    x0 = max(0, rect.x0 - pad_x)
    y0 = max(0, rect.y0 - pad_y)
    x1 = min(page_w, rect.x1 + pad_x)
    y1 = min(page_h, rect.y1 + pad_y)
    return fitz.Rect(x0, y0, x1, y1)


def _normalize_rect(rect: fitz.Rect, page_w: float, page_h: float) -> tuple:
    """Convert absolute rect to normalised (0..1) coordinates."""
    return (
        round(rect.x0 / page_w, 6),
        round(rect.y0 / page_h, 6),
        round(rect.x1 / page_w, 6),
        round(rect.y1 / page_h, 6),
    )


# ---------------------------------------------------------------------------
# Core: search text in a page
# ---------------------------------------------------------------------------

def _find_text_on_page(page: fitz.Page, needle: str) -> Optional[fitz.Rect]:
    """Search for needle text on a page. Returns expanded rect or None."""
    if not needle or len(needle) < 2:
        return None

    rects = page.search_for(needle)
    chosen = _best_rect(rects)
    if not chosen:
        return None

    pw, ph = page.rect.width, page.rect.height
    return _expand_rect(chosen, pw, ph)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_hotspots_for_poster(
    poster_id: int,
    pdf_bytes: bytes,
    pad_x: float = 60,
    pad_y: float = 80,
) -> dict:
    """Generate hotspots for all poster_items from the PDF.

    Args:
        poster_id: The poster to process.
        pdf_bytes: Raw PDF content.
        pad_x / pad_y: Bounding box expansion in PDF points.

    Returns:
        dict with counts: {found, missing, total, page_count}.
    """
    items = get_poster_items(poster_id)
    if not items:
        return {"found": 0, "missing": 0, "total": 0, "page_count": 0}

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)

    # Update poster page_count
    client = get_supabase()
    if client:
        client.table("posters").update({"page_count": page_count}).eq("poster_id", poster_id).execute()

    stats = {"found": 0, "missing": 0, "total": len(items), "page_count": page_count}

    for item in items:
        item_id = item["id"]
        urun_kodu = (item.get("urun_kodu") or "").strip()
        afis_fiyat = (item.get("afis_fiyat") or "").strip()
        item_page = item.get("page_no")  # May be None

        # Determine which pages to search
        if item_page and 1 <= item_page <= page_count:
            pages_to_search = [item_page - 1]  # 0-indexed
        else:
            pages_to_search = list(range(page_count))

        # Build needle list (ordered by priority)
        needles = []
        if urun_kodu:
            needles.append(urun_kodu)
        # Price digits as fallback
        price_digits = _price_digits(afis_fiyat)
        if price_digits:
            needles.append(price_digits)

        found = False

        for page_idx in pages_to_search:
            if found:
                break
            page = doc[page_idx]
            pw, ph = page.rect.width, page.rect.height

            for needle in needles:
                rects = page.search_for(needle)
                chosen = _best_rect(rects)
                if chosen:
                    expanded = _expand_rect(chosen, pw, ph, pad_x, pad_y)
                    x0, y0, x1, y1 = _normalize_rect(expanded, pw, ph)

                    upsert_hotspot(
                        poster_item_id=item_id,
                        page_no=page_idx + 1,  # 1-based
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        source="auto",
                    )

                    # Update item page_no if it was unknown
                    if not item_page:
                        update_poster_item(item_id, {"page_no": page_idx + 1})

                    found = True
                    stats["found"] += 1
                    break

        if not found:
            stats["missing"] += 1

    doc.close()
    return stats


def render_page_image(pdf_bytes: bytes, page_no: int, dpi: int = 150) -> bytes:
    """Render a PDF page as PNG image bytes.

    Args:
        pdf_bytes: Raw PDF file content.
        page_no: 1-based page number.
        dpi: Resolution (default 150 for good quality/speed balance).

    Returns:
        PNG image bytes.
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
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
