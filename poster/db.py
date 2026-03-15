"""Poster DB helpers – Supabase client & common CRUD operations."""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st


@st.cache_resource
def get_supabase():
    """Shared Supabase client (reuses the app-level pattern)."""
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
# Poster CRUD
# ---------------------------------------------------------------------------

def upsert_poster(title: str, week_date: str, pdf_url: str = "",
                  page_count: int = 1) -> Optional[int]:
    """Insert or return existing poster. Returns poster_id."""
    client = get_supabase()
    if not client:
        return None

    # Check existing
    existing = (
        client.table("posters")
        .select("poster_id")
        .eq("title", title)
        .eq("week_date", week_date)
        .limit(1)
        .execute()
    )
    if existing.data:
        pid = existing.data[0]["poster_id"]
        client.table("posters").update({
            "pdf_url": pdf_url,
            "page_count": page_count,
        }).eq("poster_id", pid).execute()
        return pid

    result = client.table("posters").insert({
        "title": title,
        "week_date": week_date,
        "pdf_url": pdf_url,
        "page_count": page_count,
    }).execute()
    if result.data:
        return result.data[0]["poster_id"]
    return None


def get_posters(limit: int = 50) -> list[dict]:
    """Return recent posters ordered by week_date DESC."""
    client = get_supabase()
    if not client:
        return []
    result = (
        client.table("posters")
        .select("*")
        .order("week_date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_poster_items(poster_id: int) -> list[dict]:
    """Return all items for a poster."""
    client = get_supabase()
    if not client:
        return []
    result = (
        client.table("poster_items")
        .select("*")
        .eq("poster_id", poster_id)
        .order("id")
        .execute()
    )
    return result.data or []


def get_hotspots_for_page(poster_id: int, page_no: int) -> list[dict]:
    """Return hotspots for a specific poster page with item details."""
    client = get_supabase()
    if not client:
        return []

    # Get poster_item IDs for this poster
    items = (
        client.table("poster_items")
        .select("id, urun_kodu, urun_aciklamasi, afis_fiyat, search_term, status")
        .eq("poster_id", poster_id)
        .execute()
    )
    if not items.data:
        return []

    item_map = {it["id"]: it for it in items.data}
    item_ids = list(item_map.keys())

    # Get hotspots for the page
    hotspots = (
        client.table("poster_hotspots")
        .select("*")
        .in_("poster_item_id", item_ids)
        .eq("page_no", page_no)
        .execute()
    )
    if not hotspots.data:
        return []

    # Merge item info into hotspot
    merged = []
    for hs in hotspots.data:
        item = item_map.get(hs["poster_item_id"], {})
        merged.append({**hs, **item})
    return merged


def update_poster_item(item_id: int, updates: dict):
    """Update a poster_item row."""
    client = get_supabase()
    if not client:
        return
    client.table("poster_items").update(updates).eq("id", item_id).execute()


def upsert_hotspot(poster_item_id: int, page_no: int,
                   x0: float, y0: float, x1: float, y1: float,
                   source: str = "auto", updated_by: str = "system"):
    """Insert or update hotspot for a poster_item on a given page."""
    client = get_supabase()
    if not client:
        return

    existing = (
        client.table("poster_hotspots")
        .select("id")
        .eq("poster_item_id", poster_item_id)
        .eq("page_no", page_no)
        .limit(1)
        .execute()
    )

    row = {
        "poster_item_id": poster_item_id,
        "page_no": page_no,
        "x0": round(x0, 6),
        "y0": round(y0, 6),
        "x1": round(x1, 6),
        "y1": round(y1, 6),
        "source": source,
        "updated_by": updated_by,
    }

    if existing.data:
        client.table("poster_hotspots").update(row).eq("id", existing.data[0]["id"]).execute()
    else:
        client.table("poster_hotspots").insert(row).execute()
