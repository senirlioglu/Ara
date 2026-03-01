"""Spatial clustering of OCR words using DBSCAN.

Input: list of {text, x0, y0, x1, y1} in pixel coords + image dimensions.
Output: list of cluster dicts with normalized bboxes (0..1) and combined text.
"""

from __future__ import annotations

import re

import numpy as np
from sklearn.cluster import DBSCAN


# ---------------------------------------------------------------------------
# Key extraction from cluster text
# ---------------------------------------------------------------------------

BRANDS = {
    "SAMSUNG", "LG", "SONY", "PHILIPS", "VESTEL", "TOSHIBA", "BEKO", "ARCELIK",
    "ARÇELIK", "ONVO", "NORDMENDE", "SEG", "GRUNDIG", "PIRANHA", "XIAOMI",
    "TCL", "HISENSE", "BOSCH", "SIEMENS", "REGAL", "ALTUS", "PROFILO",
    "FAKIR", "ARZUM", "SINBO", "KARACA", "KUMTEL", "LUXELL", "HOMEND",
    "KING", "FANTOM",
}


def _extract_keys(text: str) -> dict:
    """Extract matching keys from cluster OCR text."""
    upper = text.upper()

    # Model codes: 6+ chars, must mix letters + digits
    raw = set(re.findall(r"\b[A-Z0-9]{6,}\b", upper))
    model_codes = [m for m in raw if re.search(r"[A-Z]", m) and re.search(r"\d", m)]

    # 4-digit codes (accessory codes like 9035)
    code4 = list(set(re.findall(r"\b\d{4}\b", upper)))

    # Brands
    brands = [b for b in BRANDS if b in upper]

    # Size tokens (e.g., 70", 55", 43 cm)
    sizes = re.findall(r"\b\d{2,3}\s*(?:\"|\"|cm|CM|inç|inch)\b", upper, re.IGNORECASE)

    # Price tokens (e.g., 42.999, 1.299)
    prices = re.findall(r"\b\d{1,3}\.\d{3}\b", text)

    return {
        "model_codes": model_codes,
        "code4": code4,
        "brands": brands,
        "sizes": sizes,
        "prices": prices,
    }


# ---------------------------------------------------------------------------
# DBSCAN clustering
# ---------------------------------------------------------------------------

def cluster_words(
    words: list[dict],
    img_w: int,
    img_h: int,
    eps: float = 80.0,
    min_samples: int = 2,
    pad_x: float = 20.0,
    pad_y: float = 20.0,
) -> list[dict]:
    """Cluster OCR words spatially and return cluster descriptors.

    Args:
        words: [{text, x0, y0, x1, y1}, ...] in pixel coords.
        img_w, img_h: Original image dimensions in pixels.
        eps: DBSCAN epsilon (pixel distance).
        min_samples: DBSCAN min_samples.
        pad_x, pad_y: Padding around cluster bbox (pixels).

    Returns:
        list of {x0, y0, x1, y1, ocr_text, keys_json} with normalized coords.
    """
    if not words or img_w <= 0 or img_h <= 0:
        return []

    # Word center points for clustering
    centers = np.array([
        [(w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2]
        for w in words
    ])

    db = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
    labels = db.fit_predict(centers)

    # Group words by cluster label (-1 = noise, skip)
    clusters_map: dict[int, list[dict]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        clusters_map.setdefault(label, []).append(words[idx])

    # Build cluster descriptors
    clusters = []
    for label, group in sorted(clusters_map.items()):
        # Bounding box = union of all word boxes in cluster
        all_x0 = min(w["x0"] for w in group)
        all_y0 = min(w["y0"] for w in group)
        all_x1 = max(w["x1"] for w in group)
        all_y1 = max(w["y1"] for w in group)

        # Add padding and clamp
        all_x0 = max(0, all_x0 - pad_x)
        all_y0 = max(0, all_y0 - pad_y)
        all_x1 = min(img_w, all_x1 + pad_x)
        all_y1 = min(img_h, all_y1 + pad_y)

        # Normalize to 0..1
        nx0 = round(all_x0 / img_w, 6)
        ny0 = round(all_y0 / img_h, 6)
        nx1 = round(all_x1 / img_w, 6)
        ny1 = round(all_y1 / img_h, 6)

        # Sort words top-to-bottom, left-to-right for readable text
        group_sorted = sorted(group, key=lambda w: (w["y0"], w["x0"]))
        ocr_text = " ".join(w["text"] for w in group_sorted)

        keys = _extract_keys(ocr_text)

        clusters.append({
            "x0": nx0,
            "y0": ny0,
            "x1": nx1,
            "y1": ny1,
            "ocr_text": ocr_text,
            "keys_json": keys,
        })

    return clusters
