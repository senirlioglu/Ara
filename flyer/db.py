"""Flyer DB helpers — Supabase client + CRUD for flyer pipeline."""

from __future__ import annotations

import json
import os
from typing import Optional

import streamlit as st


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
    """Insert or return existing week. Returns week_id."""
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
# Weekly products (Excel import — batch)
# ---------------------------------------------------------------------------

def batch_insert_weekly_products(week_id: int, rows: list[dict]) -> int:
    """Batch insert Excel rows into weekly_products. Returns count."""
    client = get_supabase()
    if not client or not rows:
        return 0
    # Tag with week_id
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
    """Remove all products for a week (re-import)."""
    client = get_supabase()
    if not client:
        return
    client.table("weekly_products").delete().eq("week_id", week_id).execute()


# ---------------------------------------------------------------------------
# Flyers
# ---------------------------------------------------------------------------

def insert_flyer(week_id: int, filename: str, image_url: str,
                 img_w: int, img_h: int) -> Optional[int]:
    """Insert a flyer record. Returns flyer_id."""
    client = get_supabase()
    if not client:
        return None
    result = client.table("flyers").insert({
        "week_id": week_id,
        "filename": filename,
        "image_url": image_url,
        "img_w": img_w,
        "img_h": img_h,
    }).execute()
    if result.data:
        return result.data[0]["flyer_id"]
    return None


def get_flyers_for_week(week_id: int) -> list[dict]:
    client = get_supabase()
    if not client:
        return []
    result = (
        client.table("flyers")
        .select("*")
        .eq("week_id", week_id)
        .order("flyer_id")
        .execute()
    )
    return result.data or []


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


# ---------------------------------------------------------------------------
# OCR cache
# ---------------------------------------------------------------------------

def save_ocr_cache(flyer_id: int, ocr_words: list[dict]):
    """Insert or update OCR cache for a flyer."""
    client = get_supabase()
    if not client:
        return
    row = {"flyer_id": flyer_id, "ocr_words": json.dumps(ocr_words)}
    # Upsert: try insert, on conflict update
    try:
        client.table("flyer_ocr").upsert(row).execute()
    except Exception:
        # Fallback: delete + insert
        client.table("flyer_ocr").delete().eq("flyer_id", flyer_id).execute()
        client.table("flyer_ocr").insert(row).execute()


def get_ocr_cache(flyer_id: int) -> Optional[list[dict]]:
    """Return cached OCR words, or None if not cached."""
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


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

def delete_clusters_for_flyer(flyer_id: int):
    """Delete all clusters (and cascade matches) for a flyer."""
    client = get_supabase()
    if not client:
        return
    client.table("flyer_clusters").delete().eq("flyer_id", flyer_id).execute()


def batch_insert_clusters(flyer_id: int, clusters: list[dict]) -> list[dict]:
    """Batch insert cluster records. Returns inserted rows with IDs."""
    client = get_supabase()
    if not client or not clusters:
        return []
    for c in clusters:
        c["flyer_id"] = flyer_id
        if "keys_json" in c and isinstance(c["keys_json"], dict):
            c["keys_json"] = json.dumps(c["keys_json"])
    result = client.table("flyer_clusters").insert(clusters).execute()
    return result.data or []


def get_clusters_for_flyer(flyer_id: int) -> list[dict]:
    client = get_supabase()
    if not client:
        return []
    result = (
        client.table("flyer_clusters")
        .select("*")
        .eq("flyer_id", flyer_id)
        .order("cluster_id")
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def batch_insert_matches(matches: list[dict]) -> list[dict]:
    """Batch insert match records. Returns inserted rows."""
    client = get_supabase()
    if not client or not matches:
        return []
    result = client.table("flyer_matches").insert(matches).execute()
    return result.data or []


def update_match(match_id: int, updates: dict):
    client = get_supabase()
    if not client:
        return
    client.table("flyer_matches").update(updates).eq("match_id", match_id).execute()


def get_matches_for_flyer(flyer_id: int) -> list[dict]:
    """Return matches with cluster info for a flyer."""
    client = get_supabase()
    if not client:
        return []
    clusters = get_clusters_for_flyer(flyer_id)
    if not clusters:
        return []
    cids = [c["cluster_id"] for c in clusters]
    cluster_map = {c["cluster_id"]: c for c in clusters}
    result = (
        client.table("flyer_matches")
        .select("*")
        .in_("cluster_id", cids)
        .execute()
    )
    merged = []
    for m in (result.data or []):
        cl = cluster_map.get(m["cluster_id"], {})
        merged.append({**m, "_cluster": cl})
    return merged


def get_clusters_with_matches(flyer_id: int) -> list[dict]:
    """Return clusters + their match info for a flyer (viewer use)."""
    client = get_supabase()
    if not client:
        return []
    clusters = get_clusters_for_flyer(flyer_id)
    if not clusters:
        return []
    cids = [c["cluster_id"] for c in clusters]
    matches_result = (
        client.table("flyer_matches")
        .select("*")
        .in_("cluster_id", cids)
        .execute()
    )
    match_map = {}
    for m in (matches_result.data or []):
        match_map[m["cluster_id"]] = m

    merged = []
    for c in clusters:
        m = match_map.get(c["cluster_id"], {})
        merged.append({**c, "_match": m})
    return merged
