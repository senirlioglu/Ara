"""Flyer processing pipeline — orchestrates OCR → Cluster → Match → Save.

Single entry point: process_flyer(week_id, flyer_id, image_bytes, excel_df)
"""

from __future__ import annotations

import logging
from io import BytesIO

import pandas as pd
from PIL import Image

from flyer.db import (
    delete_clusters_for_flyer,
    batch_insert_clusters,
    batch_insert_matches,
    get_ocr_cache,
)
from flyer.ocr_engine import run_ocr
from flyer.clustering import cluster_words
from flyer.matching import match_clusters_to_excel

log = logging.getLogger(__name__)


def get_image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) of an image."""
    img = Image.open(BytesIO(image_bytes))
    return img.size  # (w, h)


def process_flyer(
    flyer_id: int,
    image_bytes: bytes,
    img_w: int,
    img_h: int,
    excel_df: pd.DataFrame,
    eps: float = 80.0,
    min_samples: int = 2,
    force_ocr: bool = False,
) -> dict:
    """Full pipeline for a single flyer.

    1. OCR (cached unless force_ocr)
    2. DBSCAN clustering
    3. Match clusters to Excel
    4. Save clusters + matches to DB

    Returns:
        {ocr_words, clusters_count, matched, review, unmatched, total}
    """
    # 1. OCR
    words = run_ocr(flyer_id, image_bytes, force=force_ocr)

    # 2. Cluster
    clusters = cluster_words(
        words, img_w, img_h,
        eps=eps, min_samples=min_samples,
    )

    # 3. Save clusters to DB (delete old first for re-cluster support)
    delete_clusters_for_flyer(flyer_id)
    saved_clusters = batch_insert_clusters(flyer_id, clusters)

    if not saved_clusters:
        return {
            "ocr_word_count": len(words),
            "clusters_count": 0,
            "matched": 0,
            "review": 0,
            "unmatched": 0,
            "total": 0,
        }

    # 4. Match clusters to Excel
    match_results = match_clusters_to_excel(saved_clusters, excel_df)

    # 5. Save matches to DB (batch)
    match_rows = []
    stats = {"matched": 0, "review": 0, "unmatched": 0}

    for mr in match_results:
        best = mr["best_match"]
        match_rows.append({
            "cluster_id": mr["cluster_id"],
            "urun_kodu": best.get("urun_kodu"),
            "urun_aciklamasi": best.get("urun_aciklamasi"),
            "afis_fiyat": best.get("afis_fiyat"),
            "confidence": best.get("confidence", 0),
            "status": best.get("status", "unmatched"),
        })
        stats[best.get("status", "unmatched")] += 1

    batch_insert_matches(match_rows)

    return {
        "ocr_word_count": len(words),
        "clusters_count": len(saved_clusters),
        "matched": stats["matched"],
        "review": stats["review"],
        "unmatched": stats["unmatched"],
        "total": len(saved_clusters),
    }


def recluster_flyer(
    flyer_id: int,
    img_w: int,
    img_h: int,
    excel_df: pd.DataFrame,
    eps: float = 80.0,
    min_samples: int = 2,
) -> dict:
    """Re-cluster using cached OCR (no re-OCR). For eps tuning.

    Returns same stats dict as process_flyer.
    """
    # Get cached OCR
    words = get_ocr_cache(flyer_id)
    if words is None:
        return {"error": "OCR cache not found. Run full process first."}

    # Re-cluster with new eps
    clusters = cluster_words(
        words, img_w, img_h,
        eps=eps, min_samples=min_samples,
    )

    # Save clusters (delete old)
    delete_clusters_for_flyer(flyer_id)
    saved_clusters = batch_insert_clusters(flyer_id, clusters)

    if not saved_clusters:
        return {
            "ocr_word_count": len(words),
            "clusters_count": 0,
            "matched": 0, "review": 0, "unmatched": 0, "total": 0,
        }

    # Re-match
    match_results = match_clusters_to_excel(saved_clusters, excel_df)

    match_rows = []
    stats = {"matched": 0, "review": 0, "unmatched": 0}
    for mr in match_results:
        best = mr["best_match"]
        match_rows.append({
            "cluster_id": mr["cluster_id"],
            "urun_kodu": best.get("urun_kodu"),
            "urun_aciklamasi": best.get("urun_aciklamasi"),
            "afis_fiyat": best.get("afis_fiyat"),
            "confidence": best.get("confidence", 0),
            "status": best.get("status", "unmatched"),
        })
        stats[best.get("status", "unmatched")] += 1

    batch_insert_matches(match_rows)

    return {
        "ocr_word_count": len(words),
        "clusters_count": len(saved_clusters),
        **stats,
        "total": len(saved_clusters),
    }
