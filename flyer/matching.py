"""Match flyer clusters to weekly Excel products.

Weighted scoring with structured key matching:
  1. Model code exact match   → +100
  2. 4-digit code match       → +80
  3. Brand match              → +20
  4. Size match               → +15
  5. Price proximity match    → +10
  6. Fuzzy description match  → +0..40

Returns top-N candidates per cluster, best match auto-selected.
Clusters with no product signal are marked as "skip" (noise).
"""

from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # Fallback to basic matching


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_code(x) -> str:
    if not x or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _parse_keys(keys_json) -> dict:
    """Parse keys_json from DB (could be str or dict)."""
    if isinstance(keys_json, str):
        try:
            return json.loads(keys_json)
        except Exception:
            return {}
    return keys_json or {}


def _normalize_price(price_str: str) -> Optional[float]:
    """Parse Turkish price format to float. '42.999' → 42999, '1.299,00' → 1299."""
    if not price_str:
        return None
    # Remove TL suffix and whitespace
    s = re.sub(r"[TLtl\s]", "", price_str.strip())
    # Handle '1.299,00' format
    s = re.sub(r",\d{2}$", "", s)
    # Remove dot thousands separators
    s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_model_codes_from_text(text: str) -> list[str]:
    """Extract potential model codes from text (6+ chars, mixed alnum)."""
    upper = text.upper()
    raw = set(re.findall(r"\b[A-Z0-9\-]{6,}\b", upper))
    return [m for m in raw if re.search(r"[A-Z]", m) and re.search(r"\d", m)]


def _cluster_has_signal(keys: dict) -> bool:
    """Check if cluster has enough structured info for meaningful matching."""
    return bool(
        keys.get("model_codes")
        or keys.get("prices")
        or keys.get("brands")
        or keys.get("code4")
    )


# ---------------------------------------------------------------------------
# Score a single Excel row against a cluster
# ---------------------------------------------------------------------------

def _score_row(
    row_code: str,
    row_desc: str,
    row_price: str,
    cluster_text: str,
    cluster_keys: dict,
) -> float:
    """Score an Excel row against a cluster.

    Scoring:
        model code exact match:    +100
        4-digit code match:         +80
        brand match:                +20
        size match:                 +15
        price proximity:            +10
        fuzzy description match:    +0..40 (scaled)
    """
    row_combined = f"{row_code} {row_desc}".upper()
    cluster_upper = cluster_text.upper()

    score = 0.0

    # --- Model code match (strongest signal) ---
    for m in cluster_keys.get("model_codes", []):
        if m in row_combined:
            score += 100

    # --- 4-digit code match ---
    for c in cluster_keys.get("code4", []):
        if c in row_combined:
            score += 80

    # --- Brand match ---
    for b in cluster_keys.get("brands", []):
        if b in row_combined:
            score += 20

    # --- Size match ---
    cluster_sizes = cluster_keys.get("sizes", [])
    if cluster_sizes:
        # Extract just the numeric part
        for sz in cluster_sizes:
            nums = re.findall(r"\d{2,3}", sz)
            for n in nums:
                if n in row_combined:
                    score += 15
                    break

    # --- Price proximity ---
    cluster_prices = cluster_keys.get("prices", [])
    if cluster_prices and row_price:
        row_pv = _normalize_price(row_price)
        if row_pv:
            for cp in cluster_prices:
                cpv = _normalize_price(cp)
                if cpv and abs(cpv - row_pv) / max(cpv, 1) < 0.05:
                    score += 10
                    break

    # --- Fuzzy description match (if rapidfuzz available) ---
    if fuzz and row_desc:
        ratio = fuzz.token_set_ratio(cluster_upper, row_combined)
        score += (ratio / 100.0) * 40  # Scale: 0..40

    return score


# ---------------------------------------------------------------------------
# Match all clusters against Excel
# ---------------------------------------------------------------------------

def match_clusters_to_excel(
    clusters: list[dict],
    excel_df: pd.DataFrame,
    top_n: int = 5,
) -> list[dict]:
    """Match clusters to Excel rows, return best match + top candidates per cluster.

    Args:
        clusters: list of {cluster_id, ocr_text, keys_json, ...}
        excel_df: Weekly Excel DataFrame with urun_kodu, urun_aciklamasi, afis_fiyat.
        top_n: Number of candidates to return per cluster.

    Returns:
        list of {
            cluster_id, best_match: {urun_kodu, urun_aciklamasi, afis_fiyat, confidence, status},
            candidates: [{urun_kodu, urun_aciklamasi, score}, ...]
        }
    """
    # Pre-process Excel rows once
    excel_rows = []
    for _, row in excel_df.iterrows():
        kod = _clean_code(row.get("urun_kodu", ""))
        aciklama = str(row.get("urun_aciklamasi", "") or "").strip()
        fiyat = str(row.get("afis_fiyat", "") or "").strip()
        if not kod and not aciklama:
            continue
        excel_rows.append({
            "urun_kodu": kod,
            "urun_aciklamasi": aciklama,
            "afis_fiyat": fiyat,
            "combined_upper": f"{kod} {aciklama}".upper(),
        })

    results = []

    for cluster in clusters:
        cid = cluster.get("cluster_id")
        ocr_text = cluster.get("ocr_text", "")
        keys = _parse_keys(cluster.get("keys_json", {}))

        # --- Skip low-information clusters ---
        if not _cluster_has_signal(keys):
            text_words = len(ocr_text.split())
            if text_words < 4:
                results.append({
                    "cluster_id": cid,
                    "candidates": [],
                    "status": "skip",
                    "best_match": {
                        "urun_kodu": None,
                        "urun_aciklamasi": None,
                        "afis_fiyat": None,
                        "confidence": 0,
                        "status": "skip",
                    },
                })
                continue

        # Score all Excel rows
        scored = []
        for erow in excel_rows:
            s = _score_row(
                erow["urun_kodu"],
                erow["urun_aciklamasi"],
                erow["afis_fiyat"],
                ocr_text,
                keys,
            )
            if s > 0:
                scored.append({
                    "urun_kodu": erow["urun_kodu"],
                    "urun_aciklamasi": erow["urun_aciklamasi"],
                    "afis_fiyat": erow["afis_fiyat"],
                    "score": round(s, 1),
                })

        # Sort descending by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        candidates = scored[:top_n]

        # Determine best match + status
        if candidates and candidates[0]["score"] >= 80:
            best = candidates[0]
            status = "matched"
            confidence = min(1.0, best["score"] / 150.0)  # Normalized for new scale
        elif candidates and candidates[0]["score"] >= 40:
            best = candidates[0]
            status = "review"
            confidence = best["score"] / 150.0
        else:
            best = candidates[0] if candidates else None
            status = "unmatched"
            confidence = 0.0

        result = {
            "cluster_id": cid,
            "candidates": candidates,
            "status": status,
        }

        if best:
            result["best_match"] = {
                "urun_kodu": best["urun_kodu"],
                "urun_aciklamasi": best["urun_aciklamasi"],
                "afis_fiyat": best["afis_fiyat"],
                "confidence": round(confidence, 2),
                "status": status,
            }
        else:
            result["best_match"] = {
                "urun_kodu": None,
                "urun_aciklamasi": None,
                "afis_fiyat": None,
                "confidence": 0,
                "status": "unmatched",
            }

        results.append(result)

    return results
