"""Flyer processing pipeline — orchestrates OCR → Filter → Cluster → Match → Save.

NEW pipeline:
  1. OCR at BLOCK/PARAGRAPH level (cached)
  2. Noise filtering (drop junk text)
  3. Price-anchored clustering + DBSCAN fallback
  4. Weighted matching to Excel
  5. Save clusters + matches to DB
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
from flyer.clustering import (
    filter_noise_candidates,
    build_product_clusters_price_anchor,
    cluster_words,
)
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

    1. OCR at block/paragraph level (cached unless force_ocr)
    2. Noise filtering
    3. Price-anchored clustering + DBSCAN fallback
    4. Match clusters to Excel
    5. Save clusters + matches to DB

    Returns:
        {ocr_word_count, clusters_count, matched, review, unmatched, skipped, total}
    """
    # 1. OCR (block/paragraph level)
    blocks = run_ocr(flyer_id, image_bytes, force=force_ocr)

    # Detect format: new block-level vs old word-level
    is_block_level = blocks and "level" in blocks[0]

    if is_block_level:
        # 2. Noise filtering
        filtered = filter_noise_candidates(blocks, img_w, img_h)
        log.info(f"Noise filter: {len(blocks)} → {len(filtered)} blocks")

        # 3. Price-anchored clustering
        clusters = build_product_clusters_price_anchor(
            filtered, img_w, img_h,
            pad_x=20.0, pad_y=20.0,
        )
    else:
        # Legacy word-level path
        log.info("Using legacy word-level clustering")
        clusters = cluster_words(
            blocks, img_w, img_h,
            eps=eps, min_samples=min_samples,
        )

    # 4. Save clusters to DB (delete old first for re-cluster support)
    delete_clusters_for_flyer(flyer_id)
    saved_clusters = batch_insert_clusters(flyer_id, clusters)

    if not saved_clusters:
        return {
            "ocr_word_count": len(blocks),
            "clusters_count": 0,
            "matched": 0,
            "review": 0,
            "unmatched": 0,
            "skipped": 0,
            "total": 0,
        }

    # 5. Match clusters to Excel
    match_results = match_clusters_to_excel(saved_clusters, excel_df)

    # 6. Save matches to DB (batch)
    match_rows = []
    stats = {"matched": 0, "review": 0, "unmatched": 0, "skip": 0}

    for mr in match_results:
        best = mr["best_match"]
        st = best.get("status", "unmatched")

        # Don't save skip clusters as matches
        if st == "skip":
            stats["skip"] += 1
            continue

        match_rows.append({
            "cluster_id": mr["cluster_id"],
            "urun_kodu": best.get("urun_kodu"),
            "urun_aciklamasi": best.get("urun_aciklamasi"),
            "afis_fiyat": best.get("afis_fiyat"),
            "confidence": best.get("confidence", 0),
            "status": st,
        })
        stats[st] = stats.get(st, 0) + 1

    batch_insert_matches(match_rows)

    return {
        "ocr_word_count": len(blocks),
        "clusters_count": len(saved_clusters),
        "matched": stats["matched"],
        "review": stats["review"],
        "unmatched": stats["unmatched"],
        "skipped": stats["skip"],
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
    """Re-cluster using cached OCR (no re-OCR). For eps/parameter tuning.

    Returns same stats dict as process_flyer.
    """
    # Get cached OCR
    blocks = get_ocr_cache(flyer_id)
    if blocks is None:
        return {"error": "OCR cache not found. Run full process first."}

    is_block_level = blocks and "level" in blocks[0]

    if is_block_level:
        filtered = filter_noise_candidates(blocks, img_w, img_h)
        clusters = build_product_clusters_price_anchor(
            filtered, img_w, img_h,
            eps_factor=eps / img_w if img_w > 0 else 0.06,
            min_samples=max(2, min_samples),
        )
    else:
        clusters = cluster_words(
            blocks, img_w, img_h,
            eps=eps, min_samples=min_samples,
        )

    # Save clusters (delete old)
    delete_clusters_for_flyer(flyer_id)
    saved_clusters = batch_insert_clusters(flyer_id, clusters)

    if not saved_clusters:
        return {
            "ocr_word_count": len(blocks),
            "clusters_count": 0,
            "matched": 0, "review": 0, "unmatched": 0, "skipped": 0, "total": 0,
        }

    # Re-match
    match_results = match_clusters_to_excel(saved_clusters, excel_df)

    match_rows = []
    stats = {"matched": 0, "review": 0, "unmatched": 0, "skip": 0}
    for mr in match_results:
        best = mr["best_match"]
        st = best.get("status", "unmatched")
        if st == "skip":
            stats["skip"] += 1
            continue
        match_rows.append({
            "cluster_id": mr["cluster_id"],
            "urun_kodu": best.get("urun_kodu"),
            "urun_aciklamasi": best.get("urun_aciklamasi"),
            "afis_fiyat": best.get("afis_fiyat"),
            "confidence": best.get("confidence", 0),
            "status": st,
        })
        stats[st] = stats.get(st, 0) + 1

    batch_insert_matches(match_rows)

    return {
        "ocr_word_count": len(blocks),
        "clusters_count": len(saved_clusters),
        **stats,
        "skipped": stats["skip"],
        "total": len(saved_clusters),
    }
