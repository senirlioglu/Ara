"""Hotspot generation from PDF using PyMuPDF (fitz).

Eşleşmiş poster_items için PDF sayfasında needle arar (model kodu, 4-haneli kod,
marka+kategori) ve bbox'ı normalize ederek (0..1) kaydeder.
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

def _clean_code(x: str) -> str:
    if not x:
        return ""
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _best_rect(rects: list[fitz.Rect]) -> Optional[fitz.Rect]:
    """En büyük alanlı rect'i seç."""
    if not rects:
        return None
    return max(rects, key=lambda r: r.get_area())


def _expand_rect(rect: fitz.Rect, page_w: float, page_h: float,
                 pad_x: float = 60, pad_y: float = 80) -> fitz.Rect:
    """Rect'i padding ile genişlet (ürün kartını kapsaması için)."""
    x0 = max(0, rect.x0 - pad_x)
    y0 = max(0, rect.y0 - pad_y)
    x1 = min(page_w, rect.x1 + pad_x)
    y1 = min(page_h, rect.y1 + pad_y)
    return fitz.Rect(x0, y0, x1, y1)


def _normalize_rect(rect: fitz.Rect, page_w: float, page_h: float) -> tuple:
    """Absolute rect → normalize (0..1) koordinatlar."""
    return (
        round(rect.x0 / page_w, 6),
        round(rect.y0 / page_h, 6),
        round(rect.x1 / page_w, 6),
        round(rect.y1 / page_h, 6),
    )


def _build_needles_for_item(item: dict) -> list[str]:
    """Bir poster_item için PDF'de aranacak needle listesi oluştur.

    Öncelik sırası:
      1. urun_aciklamasi içindeki model kodu (6+ char, harf+rakam karışık)
      2. urun_aciklamasi içindeki 4 haneli kodlar
      3. urun_kodu (Excel ÜRÜN KODU)
      4. Açıklamadaki ilk anlamlı kelime (marka vs)
    """
    needles: list[str] = []
    desc = (item.get("urun_aciklamasi") or "").upper()
    code = _clean_code(item.get("urun_kodu") or "").upper()

    combined = f"{code} {desc}"

    # Model kodları (harf+rakam karışık, 6+ karakter)
    models = re.findall(r"\b[A-Z0-9]{6,}\b", combined)
    for m in models:
        if re.search(r"[A-Z]", m) and re.search(r"\d", m):
            needles.append(m)

    # 4 haneli sayısal kodlar (aksesuar kodları)
    code4s = re.findall(r"\b\d{4}\b", combined)
    needles.extend(code4s)

    # Excel ÜRÜN KODU kendisi (uzun sayısal kodlar - düşük öncelik)
    if code and code not in needles:
        needles.append(code)

    return needles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_hotspots_for_poster(
    poster_id: int,
    pdf_bytes: bytes,
    pad_x: float = 60,
    pad_y: float = 80,
) -> dict:
    """Eşleşmiş poster_items için PDF'de hotspot üret.

    Her item için:
      1. Açıklamadan needle'lar çıkar (model kodu, 4-haneli kod)
      2. PDF sayfalarında needle'ı ara
      3. Bulunan bbox'ı genişlet ve normalize kaydet

    Args:
        poster_id: İşlenecek afiş.
        pdf_bytes: PDF dosyası içeriği.
        pad_x / pad_y: Bbox genişletme (PDF pt).

    Returns:
        {found, missing, total, page_count}
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

    # Sadece matched/review olanları işle (unmatched'ların hotspot'u olmaz)
    active_items = [
        it for it in items
        if it.get("status") in ("matched", "review", "pending")
    ]

    stats = {"found": 0, "missing": 0, "total": len(active_items), "page_count": page_count}

    for item in active_items:
        item_id = item["id"]
        item_page = item.get("page_no")  # May be None

        # Needle'ları oluştur
        needles = _build_needles_for_item(item)
        if not needles:
            stats["missing"] += 1
            continue

        # Hangi sayfalarda arayacağız
        if item_page and 1 <= item_page <= page_count:
            pages_to_search = [item_page - 1]  # 0-indexed
        else:
            pages_to_search = list(range(page_count))

        found = False

        for page_idx in pages_to_search:
            if found:
                break
            page = doc[page_idx]
            pw, ph = page.rect.width, page.rect.height

            for needle in needles:
                if not needle or len(needle) < 3:
                    continue
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

                    # Sayfa numarası bilinmiyorsa kaydet
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
    """PDF sayfasını PNG image olarak render et.

    Args:
        pdf_bytes: PDF dosyası içeriği.
        page_no: 1-based sayfa numarası.
        dpi: Çözünürlük (varsayılan 150).

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
    """PDF'deki sayfa sayısını döndür."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
