"""Match flyer regions to weekly Excel products.

Weighted scoring:
  model code exact match   → +100
  4-digit code match       → +80
  brand match              → +30
  size tokens match        → +20
  fuzzy description        → +0..30

Status thresholds:
  >= 90  → matched
  70..89 → review
  < 70   → unmatched
"""

from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


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
    if isinstance(keys_json, str):
        try:
            return json.loads(keys_json)
        except Exception:
            return {}
    return keys_json or {}


# ---------------------------------------------------------------------------
# Score a single Excel row against a region
# ---------------------------------------------------------------------------

def _score_row(
    row_code: str,
    row_desc: str,
    region_text: str,
    region_keys: dict,
) -> float:
    """Score an Excel row against a region.

    Returns:
        Numeric score (0+). Higher = better match.
    """
    row_combined = f"{row_code} {row_desc}".upper()
    region_upper = region_text.upper()
    score = 0.0

    # Model code exact match (+100)
    for m in region_keys.get("model_codes", []):
        if m in row_combined:
            score += 100

    # 4-digit code match (+80)
    for c in region_keys.get("code4", []):
        if c in row_combined:
            score += 80

    # Brand match (+30)
    for b in region_keys.get("brands", []):
        if b in row_combined:
            score += 30

    # Size tokens match (+20)
    for sz in region_keys.get("sizes", []):
        nums = re.findall(r"\d{2,3}", sz)
        for n in nums:
            if n in row_combined:
                score += 20
                break

    # Fuzzy description match (+0..120)
    # Give much higher weight to description matches so grocery items can match
    # even without electronic model codes.
    if fuzz and row_desc:
        ratio = fuzz.token_set_ratio(region_upper, row_combined)
        score += (ratio / 100.0) * 120

    return score


# ---------------------------------------------------------------------------
# Match all regions against Excel
# ---------------------------------------------------------------------------

def match_regions(
    regions: list[dict],
    excel_df: pd.DataFrame,
    top_n: int = 5,
) -> list[dict]:
    """Match regions to Excel rows.

    Args:
        regions: [{region_id, region_text, keys_json, ...}]
        excel_df: DataFrame with urun_kodu, urun_aciklamasi, afis_fiyat.
        top_n: Number of candidates to return per region.

    Returns:
        [{region_id, best_match, candidates, status}, ...]
    """
    # Pre-process Excel rows
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
        })

    results = []

    for region in regions:
        rid = region.get("region_id")
        region_text = region.get("region_text", "")
        keys = _parse_keys(region.get("keys_json", {}))

        scored = []
        for erow in excel_rows:
            s = _score_row(
                erow["urun_kodu"],
                erow["urun_aciklamasi"],
                region_text,
                keys,
            )
            if s > 0:
                scored.append({
                    "urun_kodu": erow["urun_kodu"],
                    "urun_aciklamasi": erow["urun_aciklamasi"],
                    "afis_fiyat": erow["afis_fiyat"],
                    "score": round(s, 1),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        candidates = scored[:top_n]

        if candidates and candidates[0]["score"] >= 90:
            best = candidates[0]
            status = "matched"
            confidence = min(1.0, best["score"] / 150.0)
        elif candidates and candidates[0]["score"] >= 70:
            best = candidates[0]
            status = "review"
            confidence = best["score"] / 150.0
        else:
            best = candidates[0] if candidates else None
            status = "unmatched"
            confidence = 0.0

        result = {
            "region_id": rid,
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
