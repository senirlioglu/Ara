"""PDF-first auto-match: PDF text → needles → score Excel rows → match.

Akış (hızlı, batch):
  1. Excel'i bellekte DataFrame olarak tut (DB call yok)
  2. PDF'den needle çıkar (CPU only)
  3. Bellekte tüm satırları skorla (CPU only)
  4. Sadece eşleşen satırları batch insert et (1 DB call)
  5. Ters eşleştirme: PDF needle'ları → Excel'de karşılığı olmayanları tespit et
"""

from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF
import pandas as pd


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

def _clean_code(x) -> str:
    """Normalise product code – strip whitespace, fix Excel float artefacts."""
    if not x or (isinstance(x, float) and pd.isna(x)):
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
            "model_codes": ["70U8000F", ...],
            "code4": ["9035", ...],
            "brands": ["SAMSUNG", ...],
            "categories": ["TV", ...],
        }
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    all_text_upper = ""
    for i in range(len(doc)):
        all_text_upper += " " + doc[i].get_text().upper()
    doc.close()

    # Model kodları: 6+ karakter, en az 1 harf + en az 1 rakam karışık
    raw_model = set(re.findall(r"\b[A-Z0-9]{6,}\b", all_text_upper))
    model_codes = sorted(
        m for m in raw_model
        if re.search(r"[A-Z]", m) and re.search(r"\d", m)
    )

    # 4 haneli sayısal kodlar (aksesuar kodları)
    code4 = sorted(set(re.findall(r"\b\d{4}\b", all_text_upper)))

    # Bilinen markalar ve kategoriler
    brands = [b for b in BRANDS if b in all_text_upper]
    categories = [c for c in CATEGORIES if c in all_text_upper]

    return {
        "model_codes": model_codes,
        "code4": code4,
        "brands": brands,
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# STEP 2: Bellekte skorlama (DB call yok)
# ---------------------------------------------------------------------------

def _score_row(urun_kodu: str, urun_aciklamasi: str, needles: dict) -> int:
    """Bir Excel satırını PDF needle'larına karşı skorla."""
    combined = f"{(urun_kodu or '').upper()} {(urun_aciklamasi or '').upper()}"
    score = 0
    for m in needles["model_codes"]:
        if m in combined:
            score += 100
    for c in needles["code4"]:
        if c in combined:
            score += 90
    for b in needles["brands"]:
        if b in combined:
            score += 30
    for k in needles["categories"]:
        if k in combined:
            score += 10
    return score


def _find_best_needle(urun_kodu: str, urun_aciklamasi: str, needles: dict) -> str:
    """Bu item için PDF'de aranacak en iyi needle'ı bul."""
    combined = f"{(urun_kodu or '').upper()} {(urun_aciklamasi or '').upper()}"

    for m in needles["model_codes"]:
        if m in combined:
            return m
    for c in needles["code4"]:
        if c in combined:
            return c
    for b in needles["brands"]:
        if b in combined:
            return b
    return ""


def score_excel_against_pdf(excel_df: pd.DataFrame, needles: dict) -> pd.DataFrame:
    """Excel DataFrame'in tüm satırlarını needles'a karşı skorla.

    Returns: DataFrame with __score, __status, __needle columns added.
    """
    df = excel_df.copy()

    scores = []
    statuses = []
    best_needles = []

    for _, row in df.iterrows():
        kod = _clean_code(row.get("urun_kodu", ""))
        aciklama = str(row.get("urun_aciklamasi", "") or "").strip()

        s = _score_row(kod, aciklama, needles)
        scores.append(s)

        if s >= 90:
            statuses.append("matched")
        elif s >= 60:
            statuses.append("review")
        else:
            statuses.append("unmatched")

        best_needles.append(_find_best_needle(kod, aciklama, needles))

    df["__score"] = scores
    df["__status"] = statuses
    df["__needle"] = best_needles

    return df


# ---------------------------------------------------------------------------
# STEP 3: Ters eşleştirme — PDF'de olup Excel'de olmayan ürünleri bul
# ---------------------------------------------------------------------------

def find_orphan_needles(needles: dict, excel_df: pd.DataFrame) -> list[str]:
    """PDF'deki model_codes ve code4 needle'larından Excel'de hiçbir satırla
    eşleşmeyenleri döndür.

    Bu needle'lar = PDF'de görünen ama Excel listesinde karşılığı olmayan ürünler.
    """
    # Excel'deki tüm metin havuzunu oluştur (bir kez)
    excel_text_pool = ""
    for _, row in excel_df.iterrows():
        kod = _clean_code(row.get("urun_kodu", "")).upper()
        aciklama = str(row.get("urun_aciklamasi", "") or "").upper()
        excel_text_pool += f" {kod} {aciklama}"

    orphans = []

    # Model kodları kontrol (en güçlü sinyaller)
    for m in needles["model_codes"]:
        if m not in excel_text_pool:
            orphans.append(m)

    # 4-haneli kodlar kontrol
    for c in needles["code4"]:
        if c not in excel_text_pool:
            orphans.append(c)

    return orphans


# ---------------------------------------------------------------------------
# STEP 4: Batch DB işlemleri (sadece eşleşenler)
# ---------------------------------------------------------------------------

def batch_insert_matched_items(
    poster_id: int,
    scored_df: pd.DataFrame,
    min_score: int = 60,
) -> list[dict]:
    """Skoru yeterli olan satırları poster_items'a batch insert et.

    Returns: inserted rows (with DB-assigned IDs).
    """
    from poster.db import get_supabase

    client = get_supabase()
    if not client:
        return []

    relevant = scored_df[scored_df["__score"] >= min_score].copy()
    if relevant.empty:
        return []

    # Mevcut poster_items'ı kontrol et (duplicate engeli)
    existing = (
        client.table("poster_items")
        .select("urun_kodu")
        .eq("poster_id", poster_id)
        .execute()
    )
    existing_codes = {r["urun_kodu"] for r in (existing.data or []) if r.get("urun_kodu")}

    rows_to_insert = []
    for _, row in relevant.iterrows():
        kod = _clean_code(row.get("urun_kodu", ""))
        if kod in existing_codes:
            continue  # Zaten eklenmiş

        aciklama = str(row.get("urun_aciklamasi", "") or "").strip()
        afis_fiyat = str(row.get("afis_fiyat", "") or "").strip() or None
        status = row["__status"]
        score = row["__score"]

        rows_to_insert.append({
            "poster_id": poster_id,
            "urun_kodu": kod or None,
            "urun_aciklamasi": aciklama or None,
            "afis_fiyat": afis_fiyat,
            "search_term": kod or None,
            "match_sku_id": kod or None,
            "match_confidence": round(min(1.0, score / 100.0), 2),
            "status": status,
        })

    if not rows_to_insert:
        return []

    # Batch insert (tek DB call)
    result = client.table("poster_items").insert(rows_to_insert).execute()
    return result.data or []


# ---------------------------------------------------------------------------
# STEP 5: Hızlı tek-poster pipeline
# ---------------------------------------------------------------------------

def process_single_poster(
    poster_id: int,
    pdf_bytes: bytes,
    excel_df: pd.DataFrame,
) -> dict:
    """Tek bir afiş için tam pipeline: needle çıkar → skorla → insert → hotspot.

    Returns:
        {matched, review, total_scored, items_inserted,
         hotspots_found, hotspots_missing, orphan_needles, needles}
    """
    from poster.hotspot_gen import generate_hotspots_for_poster

    # 1. PDF'den needle çıkar (CPU only)
    needles = extract_needles_from_pdf(pdf_bytes)

    # 2. Bellekte skorla (CPU only)
    scored = score_excel_against_pdf(excel_df, needles)

    matched_count = int((scored["__status"] == "matched").sum())
    review_count = int((scored["__status"] == "review").sum())

    # 3. Ters eşleştirme: PDF'de olup Excel'de olmayan ürünler (CPU only)
    orphans = find_orphan_needles(needles, excel_df)

    # 4. Sadece eşleşenleri DB'ye batch insert (1 call)
    inserted = batch_insert_matched_items(poster_id, scored, min_score=60)

    # 5. Hotspot üret (eşleşen item başına ~1 call)
    hs_stats = generate_hotspots_for_poster(poster_id, pdf_bytes)

    return {
        "matched": matched_count,
        "review": review_count,
        "total_scored": len(scored),
        "items_inserted": len(inserted),
        "hotspots_found": hs_stats.get("found", 0),
        "hotspots_missing": hs_stats.get("missing", 0),
        "orphan_needles": orphans,
        "needles": needles,
    }
