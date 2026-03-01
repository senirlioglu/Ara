"""Match flyer clusters to weekly Excel products.

Weighted scoring: model code > 4-digit code > brand + fuzzy description.
Returns top-N candidates per cluster, best match auto-selected.
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


# ---------------------------------------------------------------------------
# Score a single Excel row against a cluster
# ---------------------------------------------------------------------------

def _score_row(
    row_code: str,
    row_desc: str,
    cluster_text: str,
    cluster_keys: dict,
) -> float:
    """Score an Excel row against a cluster.

    Scoring:
        model code exact match:    +100
        4-digit code match:         +80
        brand match:                +20
        fuzzy description match:    +0..40 (scaled)
    """
    row_combined = f"{row_code} {row_desc}".upper()
    cluster_upper = cluster_text.upper()

    score = 0.0

    # Model code match (strongest signal)
    for m in cluster_keys.get("model_codes", []):
        if m in row_combined:
            score += 100

    # 4-digit code match
    for c in cluster_keys.get("code4", []):
        if c in row_combined:
            score += 80

    # Brand match
    for b in cluster_keys.get("brands", []):
        if b in row_combined:
            score += 20

    # Fuzzy description match (if rapidfuzz available)
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

        # Score all Excel rows
        scored = []
        for erow in excel_rows:
            s = _score_row(
                erow["urun_kodu"],
                erow["urun_aciklamasi"],
                ocr_text,
                keys,
            )
            if s > 0:
                scored.append({
                    "urun_kodu": erow["urun_kodu"],
                    "urun_aciklamasi": erow["urun_aciklamasi"],
                    "afis_fiyat": erow["afis_fiyat"],
                    "score": s,
                })

        # Sort descending by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        candidates = scored[:top_n]

        # Determine best match + status
        if candidates and candidates[0]["score"] >= 80:
            best = candidates[0]
            status = "matched"
            confidence = min(1.0, best["score"] / 100.0)
        elif candidates and candidates[0]["score"] >= 40:
            best = candidates[0]
            status = "review"
            confidence = best["score"] / 100.0
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
