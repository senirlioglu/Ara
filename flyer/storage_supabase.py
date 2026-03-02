"""Supabase CRUD for flyer pipeline v3 (price-anchored regions).

Tables: weeks, weekly_products, flyers, flyer_ocr, flyer_regions, flyer_matches.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import streamlit as st

log = logging.getLogger(__name__)


@st.cache_resource
def get_supabase():
    """Shared Supabase client."""
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------

def upsert_week(week_date: str) -> Optional[int]:
    client = get_supabase()
    if not client:
        return None
    existing = (
        client.table("weeks")
        .select("week_id")
        .eq("week_date", week_date)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["week_id"]
    result = client.table("weeks").insert({"week_date": week_date}).execute()
    if result.data:
        return result.data[0]["week_id"]
    return None


def get_weeks(limit: int = 20) -> list[dict]:
    client = get_supabase()
    if not client:
        return []
    result = (
        client.table("weeks")
        .select("*")
        .order("week_date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Weekly products
# ---------------------------------------------------------------------------

def batch_insert_weekly_products(week_id: int, rows: list[dict]) -> int:
    client = get_supabase()
    if not client or not rows:
        return 0
    for r in rows:
        r["week_id"] = week_id
    result = client.table("weekly_products").insert(rows).execute()
    return len(result.data) if result.data else 0


def get_weekly_products(week_id: int) -> list[dict]:
    client = get_supabase()
    if not client:
        return []
    result = (
        client.table("weekly_products")
        .select("*")
        .eq("week_id", week_id)
        .order("id")
        .execute()
    )
    return result.data or []


def delete_weekly_products(week_id: int):
    client = get_supabase()
    if not client:
        return
    client.table("weekly_products").delete().eq("week_id", week_id).execute()


# ---------------------------------------------------------------------------
# Flyers (one record per PDF page)
# ---------------------------------------------------------------------------

def insert_flyer(
    week_id: int, pdf_filename: str, page_no: int,
    image_url: str, img_w: int, img_h: int, zoom: float = 3.5,
) -> Optional[int]:
    client = get_supabase()
    if not client:
        return None
    # Try new schema first (pdf_filename, page_no, zoom columns)
    try:
        result = client.table("flyers").insert({
            "week_id": week_id,
            "filename": pdf_filename,
            "pdf_filename": pdf_filename,
            "page_no": page_no,
            "image_url": image_url,
            "img_w": img_w,
            "img_h": img_h,
            "zoom": zoom,
        }).execute()
        if result.data:
            return result.data[0]["flyer_id"]
    except Exception:
        # Fallback: old schema (only filename, no page_no/zoom)
        try:
            result = client.table("flyers").insert({
                "week_id": week_id,
                "filename": pdf_filename,
                "image_url": image_url,
                "img_w": img_w,
                "img_h": img_h,
            }).execute()
            if result.data:
                return result.data[0]["flyer_id"]
        except Exception as e:
            log.error(f"insert_flyer failed: {e}")
    return None


def get_flyers_for_week(week_id: int) -> list[dict]:
    client = get_supabase()
    if not client:
        return []
    try:
        result = (
            client.table("flyers")
            .select("*")
            .eq("week_id", week_id)
            .order("pdf_filename")
            .order("page_no")
            .execute()
        )
        return result.data or []
    except Exception:
        # Fallback: chained .order() can fail in some postgrest-py versions;
        # fetch without server-side ordering and sort in Python instead.
        try:
            result = (
                client.table("flyers")
                .select("*")
                .eq("week_id", week_id)
                .execute()
            )
            data = result.data or []
            data.sort(key=lambda f: (f.get("pdf_filename", ""), f.get("page_no", 0)))
            return data
        except Exception as exc:
            log.error("get_flyers_for_week(week_id=%s) failed: %s", week_id, exc)
            raise


def get_flyer(flyer_id: int) -> Optional[dict]:
    client = get_supabase()
    if not client:
        return None
    result = (
        client.table("flyers")
        .select("*")
        .eq("flyer_id", flyer_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_flyer(flyer_id: int, updates: dict):
    client = get_supabase()
    if not client:
        return
    client.table("flyers").update(updates).eq("flyer_id", flyer_id).execute()


# ---------------------------------------------------------------------------
# OCR cache
# ---------------------------------------------------------------------------

def save_ocr_cache(flyer_id: int, ocr_words: list[dict]):
    client = get_supabase()
    if not client:
        return
    row = {"flyer_id": flyer_id, "ocr_words": json.dumps(ocr_words, ensure_ascii=False)}
    try:
        client.table("flyer_ocr").upsert(row).execute()
    except Exception:
        client.table("flyer_ocr").delete().eq("flyer_id", flyer_id).execute()
        client.table("flyer_ocr").insert(row).execute()


def get_ocr_cache(flyer_id: int) -> Optional[list[dict]]:
    client = get_supabase()
    if not client:
        return None
    result = (
        client.table("flyer_ocr")
        .select("ocr_words")
        .eq("flyer_id", flyer_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    raw = result.data[0]["ocr_words"]
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def delete_ocr_cache(flyer_id: int):
    client = get_supabase()
    if not client:
        return
    client.table("flyer_ocr").delete().eq("flyer_id", flyer_id).execute()


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

def delete_regions_for_flyer(flyer_id: int):
    """Delete all regions (and cascade matches) for a flyer."""
    client = get_supabase()
    if not client:
        return
    try:
        client.table("flyer_regions").delete().eq("flyer_id", flyer_id).execute()
    except Exception:
        pass  # Table may not exist yet


def batch_insert_regions(flyer_id: int, regions: list[dict]) -> list[dict]:
    """Batch insert region records. Returns inserted rows with IDs."""
    client = get_supabase()
    if not client or not regions:
        return []
    rows = []
    for r in regions:
        row = {
            "flyer_id": flyer_id,
            "price_value": r.get("price_value"),
            "price_bbox": json.dumps(r["price_bbox"]) if r.get("price_bbox") else None,
            "x0": r["x0"],
            "y0": r["y0"],
            "x1": r["x1"],
            "y1": r["y1"],
            "region_text": r.get("region_text", ""),
            "keys_json": json.dumps(r.get("keys_json", {}), ensure_ascii=False),
        }
        rows.append(row)
    try:
        result = client.table("flyer_regions").insert(rows).execute()
        return result.data or []
    except Exception as e:
        log.error(f"batch_insert_regions failed: {e}")
        return []


def get_regions_for_flyer(flyer_id: int) -> list[dict]:
    client = get_supabase()
    if not client:
        return []
    try:
        result = (
            client.table("flyer_regions")
            .select("*")
            .eq("flyer_id", flyer_id)
            .order("region_id")
            .execute()
        )
        return result.data or []
    except Exception:
        # Table may not exist (pre-migration) or .order() may fail
        try:
            result = (
                client.table("flyer_regions")
                .select("*")
                .eq("flyer_id", flyer_id)
                .execute()
            )
            data = result.data or []
            data.sort(key=lambda r: r.get("region_id", 0))
            return data
        except Exception:
            # Table doesn't exist yet — return empty
            return []


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def batch_insert_matches(matches: list[dict]) -> list[dict]:
    client = get_supabase()
    if not client or not matches:
        return []
    rows = []
    for m in matches:
        row = {
            "urun_kodu": m.get("urun_kodu"),
            "urun_aciklamasi": m.get("urun_aciklamasi"),
            "afis_fiyat": m.get("afis_fiyat"),
            "confidence": m.get("confidence", 0),
            "status": m.get("status", "unmatched"),
        }
        if m.get("region_id"):
            row["region_id"] = m["region_id"]
        if m.get("cluster_id"):
            row["cluster_id"] = m["cluster_id"]
        if "candidates" in m:
            row["candidates_json"] = json.dumps(m["candidates"], ensure_ascii=False)
        rows.append(row)
    try:
        result = client.table("flyer_matches").insert(rows).execute()
        return result.data or []
    except Exception as e:
        log.error(f"batch_insert_matches failed: {e}")
        return []


def update_match(match_id: int, updates: dict):
    client = get_supabase()
    if not client:
        return
    client.table("flyer_matches").update(updates).eq("match_id", match_id).execute()


def get_regions_with_matches(flyer_id: int) -> list[dict]:
    """Return regions + their match info for a flyer (viewer/review use)."""
    client = get_supabase()
    if not client:
        return []
    regions = get_regions_for_flyer(flyer_id)
    if not regions:
        return []
    rids = [r["region_id"] for r in regions]
    try:
        matches_result = (
            client.table("flyer_matches")
            .select("*")
            .in_("region_id", rids)
            .execute()
        )
    except Exception as exc:
        log.error("get_regions_with_matches: matches query failed for flyer %s: %s", flyer_id, exc)
        matches_result = None

    match_map = {}
    if matches_result and matches_result.data:
        for m in matches_result.data:
            match_map[m["region_id"]] = m

    merged = []
    for r in regions:
        m = match_map.get(r["region_id"], {})
        merged.append({**r, "_match": m})
    return merged


# ---------------------------------------------------------------------------
# Legacy compat: old v2 clusters (read-only, for pre-migration data)
# ---------------------------------------------------------------------------

def get_clusters_with_matches(flyer_id: int) -> list[dict]:
    """Read old flyer_clusters + matches. Returns [] if table doesn't exist."""
    client = get_supabase()
    if not client:
        return []
    try:
        result = (
            client.table("flyer_clusters")
            .select("*")
            .eq("flyer_id", flyer_id)
            .order("cluster_id")
            .execute()
        )
        clusters = result.data or []
    except Exception:
        return []

    if not clusters:
        return []

    cids = [c["cluster_id"] for c in clusters]
    try:
        matches_result = (
            client.table("flyer_matches")
            .select("*")
            .in_("cluster_id", cids)
            .execute()
        )
    except Exception:
        matches_result = None

    match_map = {}
    if matches_result and matches_result.data:
        for m in matches_result.data:
            match_map[m.get("cluster_id")] = m

    merged = []
    for c in clusters:
        m = match_map.get(c["cluster_id"], {})
        merged.append({**c, "_match": m})
    return merged


# ---------------------------------------------------------------------------
# Storage bucket helpers
# ---------------------------------------------------------------------------

def upload_to_storage(
    bucket: str, path: str, data: bytes, content_type: str = "image/png",
) -> str:
    """Upload file to Supabase Storage. Returns public URL."""
    client = get_supabase()
    if not client:
        return ""
    try:
        try:
            client.storage.from_(bucket).remove([path])
        except Exception:
            pass
        client.storage.from_(bucket).upload(
            path, data,
            file_options={"content-type": content_type},
        )
        return client.storage.from_(bucket).get_public_url(path)
    except Exception:
        return ""
