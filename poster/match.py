"""PDF-first auto-match: PDF text → needles → score Excel rows → match.

Akış:
  1. PDF sayfalarından ayırt edici anahtarlar çıkar (model kodları, 4-haneli kodlar,
     marka isimleri, kategori kelimeleri)
  2. Her Excel (poster_items) satırını bu needles'a karşı skorla
  3. Yüksek skor → matched, orta → review, düşük → unmatched
  4. search_term olarak Excel ÜRÜN KODU kullan (DB araması için)
"""

from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF

from poster.db import get_supabase, update_poster_item, get_poster_items


# ---------------------------------------------------------------------------
# Bilinen marka ve kategori sözlükleri
# ---------------------------------------------------------------------------

BRANDS = [
    "SAMSUNG", "LG", "SONY", "PHILIPS", "VESTEL", "TOSHIBA", "BEKO", "ARCELIK",
    "ONVO", "NORDMENDE", "SEG", "GRUNDIG", "PIRANHA", "XIAOMI", "TCL", "HISENSE",
    "BOSCH", "SIEMENS", "REGAL", "ALTUS", "PROFILO", "FAKIR", "ARZUM", "SINBO",
    "KARACA", "KUMTEL", "LUXELL", "HOMEND", "KING", "FANTOM",
]

CATEGORIES = [
    "TV", "TELEVIZYON", "QLED", "OLED", "UHD", "ANDROID", "GOOGLE", "SMART",
    "POWERBANK", "MOUSE", "KULAKLIK", "KULAKICI", "BLUETOOTH", "KABLOSUZ",
    "UZATMA", "KABLO", "TYPE-C", "USB", "STAND", "TABLET", "TELEFON",
    "MAGSAFE", "PRIZ", "TARAFTAR", "FRAMELESS", "4K",
    "CAMASIR", "BULASIK", "BUZDOLABI", "KLIMA", "ASPIRATOR", "SUPURGE",
    "FIRIN", "MIKRODALGA", "TOST", "WAFFLE", "BLENDER", "MIKSER",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_code(x: str) -> str:
    """Normalise product code – strip whitespace, fix Excel float artefacts."""
    if not x:
        return ""
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


# ---------------------------------------------------------------------------
# STEP 1: PDF'den needle çıkarma
# ---------------------------------------------------------------------------

def extract_needles_from_pdf(pdf_bytes: bytes) -> dict:
    """PDF'nin tüm sayfalarından eşleşme anahtarlarını çıkar.

    Returns:
        {
            "model_codes": ["70U8000F", "65VQ90F3UA", ...],
            "code4": ["9035", "7658", ...],
            "brands": ["SAMSUNG", "ONVO", ...],
            "categories": ["TV", "POWERBANK", ...],
            "page_texts": {1: "PAGE 1 FULL TEXT...", ...},  # 1-based
        }
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    all_text_upper = ""
    page_texts: dict[int, str] = {}

    for i in range(len(doc)):
        text = doc[i].get_text()
        page_texts[i + 1] = text.upper()
        all_text_upper += " " + text.upper()

    doc.close()

    # Model kodları: 6+ karakter, en az 1 harf + en az 1 rakam karışık
    raw_model = set(re.findall(r"\b[A-Z0-9]{6,}\b", all_text_upper))
    model_codes = sorted(
        m for m in raw_model
        if re.search(r"[A-Z]", m) and re.search(r"\d", m)
    )

    # 4 haneli sayısal kodlar (aksesuar kodları: 9035, 7658 vs.)
    code4 = sorted(set(re.findall(r"\b\d{4}\b", all_text_upper)))

    # Bilinen markalar
    brands = [b for b in BRANDS if b in all_text_upper]

    # Bilinen kategoriler
    categories = [c for c in CATEGORIES if c in all_text_upper]

    return {
        "model_codes": model_codes,
        "code4": code4,
        "brands": brands,
        "categories": categories,
        "page_texts": page_texts,
    }


# ---------------------------------------------------------------------------
# STEP 2: Excel satırını needles'a karşı skorla
# ---------------------------------------------------------------------------

def _score_item(urun_kodu: str, urun_aciklamasi: str, needles: dict) -> int:
    """Bir Excel satırını PDF needle'larına karşı skorla.

    Skor tablosu:
      model kodu eşleşmesi:  +100
      4-haneli kod eşleşmesi: +90
      marka eşleşmesi:        +30
      kategori eşleşmesi:     +10 (her biri)
    """
    desc_upper = (urun_aciklamasi or "").upper()
    code_upper = (urun_kodu or "").upper()
    combined = f"{code_upper} {desc_upper}"

    score = 0

    # Model kodu (en güçlü sinyal)
    for m in needles["model_codes"]:
        if m in combined:
            score += 100

    # 4 haneli kod
    for c in needles["code4"]:
        if c in combined:
            score += 90

    # Marka
    for b in needles["brands"]:
        if b in combined:
            score += 30

    # Kategori kelimeleri
    for k in needles["categories"]:
        if k in combined:
            score += 10

    return score


def _find_best_needle(urun_kodu: str, urun_aciklamasi: str, needles: dict) -> str:
    """Bu item için PDF'de aranacak en iyi needle'ı bul.

    Hotspot bbox bulma sırasında kullanılacak.
    Öncelik: model kodu > 4-haneli kod > marka.
    """
    desc_upper = (urun_aciklamasi or "").upper()
    code_upper = (urun_kodu or "").upper()
    combined = f"{code_upper} {desc_upper}"

    # Model kodu eşleşmesi
    for m in needles["model_codes"]:
        if m in combined:
            return m

    # 4 haneli kod
    for c in needles["code4"]:
        if c in combined:
            return c

    # Marka (son çare)
    for b in needles["brands"]:
        if b in combined:
            return b

    return ""


# ---------------------------------------------------------------------------
# STEP 3: Ana eşleştirme rutini
# ---------------------------------------------------------------------------

def run_auto_match(poster_id: int, pdf_bytes: bytes) -> dict:
    """PDF-first match: PDF'den needle çıkar → Excel satırlarını skorla.

    Args:
        poster_id: İşlenecek afişin ID'si.
        pdf_bytes: PDF dosyasının raw içeriği.

    Returns:
        dict with counts: {matched, review, unmatched, total, needles}.
    """
    items = get_poster_items(poster_id)
    if not items:
        return {"matched": 0, "review": 0, "unmatched": 0, "total": 0}

    # PDF'den anahtarları çıkar
    needles = extract_needles_from_pdf(pdf_bytes)

    stats = {"matched": 0, "review": 0, "unmatched": 0, "total": len(items)}

    for item in items:
        item_id = item["id"]
        urun_kodu = _clean_code(item.get("urun_kodu") or "")
        urun_aciklamasi = (item.get("urun_aciklamasi") or "").strip()

        score = _score_item(urun_kodu, urun_aciklamasi, needles)
        best_needle = _find_best_needle(urun_kodu, urun_aciklamasi, needles)

        # search_term: DB araması için Excel ÜRÜN KODU kullan
        search_term = urun_kodu or None

        if score >= 90:
            status = "matched"
            confidence = min(1.0, score / 100.0)
        elif score >= 60:
            status = "review"
            confidence = score / 100.0
        else:
            status = "unmatched"
            confidence = score / 100.0 if score > 0 else 0

        updates = {
            "match_sku_id": urun_kodu or None,
            "search_term": search_term,
            "match_confidence": round(confidence, 2),
            "status": status,
        }

        # best_needle'ı search_term'e yedek olarak kaydet (hotspot_gen kullanacak)
        # Ama asıl arama terimi hep urun_kodu olsun
        if not search_term and best_needle:
            updates["search_term"] = best_needle

        update_poster_item(item_id, updates)
        stats[status] = stats.get(status, 0) + 1

    # needles'ı da dön ki hotspot_gen kullansın
    stats["needles"] = needles
    return stats
