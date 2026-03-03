"""Suggest Excel matches for OCR text — token scoring + fuzzy."""

from __future__ import annotations

import pandas as pd

from utils_text import normalize_tr, extract_tokens

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


def top_k_candidates(
    ocr_text: str,
    excel_df: pd.DataFrame,
    k: int = 5,
) -> list[dict]:
    """Return top-k Excel rows scored against OCR text.

    Returns:
        [{urun_kodu, urun_aciklamasi, afis_fiyat, score}, ...]
        Sorted descending by score.
    """
    if not ocr_text or excel_df is None or excel_df.empty:
        return []

    ocr_norm = normalize_tr(ocr_text)
    ocr_tokens = extract_tokens(ocr_text)

    scored: list[dict] = []

    for _, row in excel_df.iterrows():
        kod = str(row.get("urun_kodu") or row.get("ÜRÜN KODU") or "").strip()
        aciklama = str(
            row.get("urun_aciklamasi") or row.get("ÜRÜN AÇIKLAMASI") or ""
        ).strip()
        fiyat = str(row.get("afis_fiyat") or row.get("AFIS_FIYAT") or "").strip()

        if not kod and not aciklama:
            continue

        row_text = normalize_tr(f"{kod} {aciklama}")
        score = 0.0

        # Model token exact match (+100 each)
        for m in ocr_tokens["model"]:
            if m in row_text:
                score += 100

        # 4-digit code match (+80 each)
        for c in ocr_tokens["code4"]:
            if c in row_text:
                score += 80

        # Brand match (+30)
        for b in ocr_tokens["brand"]:
            if normalize_tr(b) in row_text:
                score += 30

        # Size match (+20)
        for s in ocr_tokens["size"]:
            nums = [n for n in s.split() if n.isdigit()]
            for n in nums:
                if n in row_text:
                    score += 20
                    break

        # Fuzzy score (+0..30)
        if fuzz and aciklama:
            ratio = fuzz.token_set_ratio(ocr_norm, row_text)
            score += int(ratio * 0.30)

        if score > 0:
            scored.append({
                "urun_kodu": kod,
                "urun_aciklamasi": aciklama,
                "afis_fiyat": fiyat or None,
                "score": round(score, 1),
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]
