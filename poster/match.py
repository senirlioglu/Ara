"""Auto-match poster items against the product master (stok_gunluk).

Strategy:
  1. Exact match by urun_kodu
  2. Fuzzy match by normalized description tokens
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd

from poster.db import get_supabase, update_poster_item, get_poster_items


# ---------------------------------------------------------------------------
# Text normalisation (mirrors temizle_ve_kok_bul from main app)
# ---------------------------------------------------------------------------

_TR_MAP = {
    "İ": "i", "I": "i", "ı": "i",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ş": "s", "ş": "s",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
}


def _normalize(text: str) -> str:
    if not text:
        return ""
    result = text
    for tr, asc in _TR_MAP.items():
        result = result.replace(tr, asc)
    result = unicodedata.normalize("NFKD", result)
    result = "".join(c for c in result if not unicodedata.combining(c))
    result = result.lower()
    result = result.replace("makinasi", "makine").replace("makinesi", "makine").replace("makina", "makine")
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _extract_tokens(text: str) -> set[str]:
    """Extract meaningful tokens (brand, size, keywords) from a description."""
    norm = _normalize(text)
    # Remove common filler words
    stopwords = {"ve", "ile", "icin", "adet", "li", "lu", "set", "takimi", "tl"}
    tokens = {t for t in norm.split() if len(t) >= 2 and t not in stopwords}
    return tokens


def _fuzzy_score(desc_a: str, desc_b: str) -> float:
    """Return 0-1 similarity between two product descriptions."""
    norm_a = _normalize(desc_a)
    norm_b = _normalize(desc_b)
    if not norm_a or not norm_b:
        return 0.0

    # Token overlap (Jaccard)
    tok_a = _extract_tokens(desc_a)
    tok_b = _extract_tokens(desc_b)
    if tok_a and tok_b:
        jaccard = len(tok_a & tok_b) / len(tok_a | tok_b)
    else:
        jaccard = 0.0

    # Sequence ratio
    seq = SequenceMatcher(None, norm_a, norm_b).ratio()

    # Weighted combination
    return 0.6 * jaccard + 0.4 * seq


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_code(x: str) -> str:
    """Normalise product code – strip whitespace, fix Excel float artefacts."""
    if not x:
        return ""
    s = str(x).strip()
    # Excel bazen "9035.0" gibi float string döndürür
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


# ---------------------------------------------------------------------------
# Master product fetch – only for the codes we actually need
# ---------------------------------------------------------------------------

def _load_master_for_codes(codes: list[str]) -> pd.DataFrame:
    """Fetch (urun_kod, urun_ad) from stok_gunluk only for the given codes.

    Bu yaklaşım olmayan bir RPC'ye bağımlılığı ortadan kaldırır ve
    sadece ihtiyaç duyulan kodları çeker (200'lik batch'ler halinde).
    """
    client = get_supabase()
    if not client:
        return pd.DataFrame(columns=["urun_kod", "urun_ad"])

    codes = [_clean_code(c) for c in codes if _clean_code(c)]
    codes = list(dict.fromkeys(codes))  # unique, preserve order
    if not codes:
        return pd.DataFrame(columns=["urun_kod", "urun_ad"])

    rows: list[dict] = []
    BATCH = 200  # Supabase .in_() için güvenli üst sınır
    for i in range(0, len(codes), BATCH):
        batch = codes[i : i + BATCH]
        try:
            res = (
                client.table("stok_gunluk")
                .select("urun_kod, urun_ad")
                .in_("urun_kod", batch)
                .limit(50000)
                .execute()
            )
            if res.data:
                rows.extend(res.data)
        except Exception:
            pass

    if not rows:
        return pd.DataFrame(columns=["urun_kod", "urun_ad"])

    df = pd.DataFrame(rows)
    df["urun_kod"] = df["urun_kod"].fillna("").astype(str).str.strip()
    df["urun_ad"] = df["urun_ad"].fillna("").astype(str).str.strip()
    # stok_gunluk mağaza bazlı tekrarlar içerebilir → tekilleştir
    df = df.drop_duplicates(subset=["urun_kod"])
    return df


# ---------------------------------------------------------------------------
# Main matching routine
# ---------------------------------------------------------------------------

def run_auto_match(poster_id: int) -> dict:
    """Match poster_items against product master.

    Returns dict with counts: {matched, review, unmatched, total}.
    """
    items = get_poster_items(poster_id)
    if not items:
        return {"matched": 0, "review": 0, "unmatched": 0, "total": 0}

    # Sadece Excel'den gelen kodları DB'den iste (RPC gerektirmez)
    codes = [_clean_code(it.get("urun_kodu") or "") for it in items]
    master = _load_master_for_codes(codes)
    if master.empty:
        # Mark all unmatched
        for it in items:
            update_poster_item(it["id"], {
                "status": "unmatched",
                "match_confidence": 0,
            })
        return {"matched": 0, "review": 0, "unmatched": len(items), "total": len(items)}

    # Build lookup: kod → urun_ad
    kod_to_ad = {}
    for _, row in master.iterrows():
        kod = row["urun_kod"]
        if kod:
            kod_to_ad[kod] = row["urun_ad"]

    stats = {"matched": 0, "review": 0, "unmatched": 0, "total": len(items)}

    for item in items:
        item_id = item["id"]
        urun_kodu = _clean_code(item.get("urun_kodu") or "")
        urun_aciklamasi = (item.get("urun_aciklamasi") or "").strip()

        best_match: Optional[dict] = None

        # --- Strategy 1: exact code match ---
        if urun_kodu and urun_kodu in kod_to_ad:
            best_match = {
                "match_sku_id": urun_kodu,
                "search_term": urun_kodu,
                "match_confidence": 1.0,
                "status": "matched",
            }

        # --- Strategy 2: code prefix/contains match ---
        if not best_match and urun_kodu and len(urun_kodu) >= 5:
            candidates = [
                (k, v) for k, v in kod_to_ad.items()
                if k.startswith(urun_kodu) or urun_kodu in k
            ]
            if len(candidates) == 1:
                best_match = {
                    "match_sku_id": candidates[0][0],
                    "search_term": candidates[0][0],
                    "match_confidence": 0.85,
                    "status": "matched",
                }
            elif candidates:
                # Multiple candidates – take best fuzzy if description available
                if urun_aciklamasi:
                    scored = [
                        (k, v, _fuzzy_score(urun_aciklamasi, v))
                        for k, v in candidates
                    ]
                    scored.sort(key=lambda x: x[2], reverse=True)
                    top = scored[0]
                    conf = round(top[2] * 0.85, 2)
                    best_match = {
                        "match_sku_id": top[0],
                        "search_term": top[0],
                        "match_confidence": conf,
                        "status": "matched" if conf >= 0.6 else "review",
                    }
                else:
                    # Ambiguous – mark for review
                    best_match = {
                        "match_sku_id": candidates[0][0],
                        "search_term": candidates[0][0],
                        "match_confidence": 0.4,
                        "status": "review",
                    }

        # --- Strategy 3: fuzzy by description ---
        if not best_match and urun_aciklamasi:
            best_score = 0.0
            best_kod = ""
            best_ad = ""

            for _, row in master.iterrows():
                score = _fuzzy_score(urun_aciklamasi, row["urun_ad"])
                if score > best_score:
                    best_score = score
                    best_kod = row["urun_kod"]
                    best_ad = row["urun_ad"]

            if best_score >= 0.55:
                status = "matched" if best_score >= 0.75 else "review"
                best_match = {
                    "match_sku_id": best_kod,
                    "search_term": best_kod if best_kod else _normalize(urun_aciklamasi),
                    "match_confidence": round(best_score, 2),
                    "status": status,
                }

        # --- No match ---
        if not best_match:
            # Fallback search_term: use code if exists, else first 3 words of description
            fallback_term = urun_kodu
            if not fallback_term and urun_aciklamasi:
                words = urun_aciklamasi.split()[:3]
                fallback_term = " ".join(words)

            best_match = {
                "match_sku_id": None,
                "search_term": fallback_term or None,
                "match_confidence": 0,
                "status": "unmatched",
            }

        update_poster_item(item_id, best_match)
        stats[best_match["status"]] = stats.get(best_match["status"], 0) + 1

    return stats
