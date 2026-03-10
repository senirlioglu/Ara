"""Supabase persistence for flyer bbox-product mappings and poster pages.

All poster images are stored in Supabase Storage ('poster-images' bucket).
Metadata + mappings live in Supabase PostgreSQL tables.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase client (singleton)
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    """Return cached Supabase client."""
    global _client
    if _client is not None:
        return _client
    try:
        from supabase import create_client
        import streamlit as st
        url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        if not url or not key:
            log.error("SUPABASE_URL or SUPABASE_KEY not set")
            return None
        _client = create_client(url, key)
        return _client
    except Exception as e:
        log.error("Supabase client error: %s", e)
        return None


BUCKET = "poster-images"


def _ensure_bucket():
    """Create the storage bucket if it doesn't exist (idempotent)."""
    sb = _get_client()
    if not sb:
        return
    try:
        sb.storage.get_bucket(BUCKET)
    except Exception:
        try:
            sb.storage.create_bucket(BUCKET, options={"public": True})
        except Exception as e:
            # Bucket might already exist with different casing, etc.
            log.warning("Bucket create: %s", e)


# ---------------------------------------------------------------------------
# Helper — no-op init_db (kept for backward compat, tables created via SQL)
# ---------------------------------------------------------------------------

def init_db(db_path=None):
    """No-op — tables are created via Supabase migration SQL."""
    _ensure_bucket()


# ============================================================================
# MAPPINGS CRUD
# ============================================================================

def save_mapping(m: dict, db_path=None) -> int:
    """Insert a mapping and return its ID."""
    sb = _get_client()
    row = {
        "week_id": m["week_id"],
        "flyer_filename": m["flyer_filename"],
        "page_no": m["page_no"],
        "x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
        "urun_kodu": m.get("urun_kodu"),
        "urun_aciklamasi": m.get("urun_aciklamasi"),
        "afis_fiyat": m.get("afis_fiyat"),
        "ocr_text": m.get("ocr_text"),
        "source": m.get("source", "suggested"),
        "status": m.get("status", "matched"),
        "created_at": m.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    res = sb.table("mappings").insert(row).execute()
    return res.data[0]["mapping_id"]


def list_mappings(
    week_id: str, flyer_filename: str, page_no: int, db_path=None,
) -> list[dict]:
    """Return all mappings for a given page."""
    sb = _get_client()
    res = (
        sb.table("mappings")
        .select("*")
        .eq("week_id", week_id)
        .eq("flyer_filename", flyer_filename)
        .eq("page_no", page_no)
        .order("mapping_id")
        .execute()
    )
    return res.data or []


def all_mappings_for_page(
    week_id: str, flyer_filename: str, page_no: int, db_path=None,
) -> list[dict]:
    """Alias for list_mappings."""
    return list_mappings(week_id, flyer_filename, page_no, db_path)


def update_mapping(mapping_id: int, fields: dict, db_path=None):
    """Update specific fields of a mapping by ID."""
    allowed = {"urun_kodu", "urun_aciklamasi", "afis_fiyat", "source",
               "status", "x0", "y0", "x1", "y1"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    sb = _get_client()
    sb.table("mappings").update(to_set).eq("mapping_id", mapping_id).execute()


def delete_mapping(mapping_id: int, db_path=None):
    """Delete a single mapping by ID."""
    sb = _get_client()
    sb.table("mappings").delete().eq("mapping_id", mapping_id).execute()


def delete_page_mappings(
    week_id: str, flyer_filename: str, page_no: int, db_path=None,
):
    """Delete ALL mappings for a specific page."""
    sb = _get_client()
    (
        sb.table("mappings")
        .delete()
        .eq("week_id", week_id)
        .eq("flyer_filename", flyer_filename)
        .eq("page_no", page_no)
        .execute()
    )


def get_last_mapping_id(week_id: str, db_path=None) -> int | None:
    """Return the most recent mapping_id for a week, or None."""
    sb = _get_client()
    res = (
        sb.table("mappings")
        .select("mapping_id")
        .eq("week_id", week_id)
        .order("mapping_id", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["mapping_id"] if res.data else None


def get_max_sort_order(week_id: str, db_path=None) -> int:
    """Return the maximum sort_order for a week's poster pages."""
    sb = _get_client()
    res = (
        sb.table("poster_pages")
        .select("sort_order")
        .eq("week_id", week_id)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["sort_order"] if res.data else 0


# ============================================================================
# POSTER PAGES — images in Supabase Storage, metadata in DB
# ============================================================================

def _upload_image(week_id: str, flyer_filename: str, page_no: int,
                  image_bytes: bytes) -> str:
    """Upload image to Supabase Storage and return the path."""
    sb = _get_client()
    # Deterministic path so upsert works
    safe_name = flyer_filename.replace(" ", "_").replace("/", "_")
    path = f"{week_id}/{safe_name}_p{page_no}.jpg"
    try:
        sb.storage.from_(BUCKET).upload(
            path, image_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
    except Exception as e:
        # If file exists, update
        log.warning("Upload fallback: %s", e)
        try:
            sb.storage.from_(BUCKET).update(
                path, image_bytes,
                file_options={"content-type": "image/jpeg"},
            )
        except Exception as e2:
            log.error("Upload failed: %s", e2)
    return path


def _get_image_url(path: str) -> str:
    """Get public URL for an image in Storage."""
    sb = _get_client()
    return sb.storage.from_(BUCKET).get_public_url(path)


def _download_image(path: str) -> bytes:
    """Download image bytes from Storage."""
    sb = _get_client()
    return sb.storage.from_(BUCKET).download(path)


def save_poster_page(
    week_id: str, flyer_filename: str, page_no: int,
    png_data: bytes, title: str = "", sort_order: int = 0,
    db_path=None,
):
    """Save or replace a poster page image."""
    image_path = _upload_image(week_id, flyer_filename, page_no, png_data)
    sb = _get_client()
    sb.table("poster_pages").upsert({
        "week_id": week_id,
        "flyer_filename": flyer_filename,
        "page_no": page_no,
        "image_path": image_path,
        "title": title,
        "sort_order": sort_order,
    }, on_conflict="week_id,flyer_filename,page_no").execute()


def save_poster_pages_bulk(pages: list[dict], db_path=None):
    """Save multiple poster pages at once."""
    sb = _get_client()
    _ensure_bucket()
    rows = []
    for pg in pages:
        image_path = _upload_image(
            pg["week_id"], pg["flyer_filename"], pg["page_no"],
            pg["png_data"],
        )
        rows.append({
            "week_id": pg["week_id"],
            "flyer_filename": pg["flyer_filename"],
            "page_no": pg["page_no"],
            "image_path": image_path,
            "title": pg.get("title", ""),
            "sort_order": pg.get("sort_order", 0),
        })
    if rows:
        sb.table("poster_pages").upsert(
            rows, on_conflict="week_id,flyer_filename,page_no"
        ).execute()


def get_poster_pages(week_id: str, db_path=None) -> list[dict]:
    """Return all poster pages for a week, ordered by sort_order then page_no.

    Downloads images from Storage and adds 'png_data' key for backward compat.
    """
    sb = _get_client()
    res = (
        sb.table("poster_pages")
        .select("id, week_id, flyer_filename, page_no, image_path, title, sort_order")
        .eq("week_id", week_id)
        .order("sort_order")
        .order("flyer_filename")
        .order("page_no")
        .execute()
    )
    pages = []
    for r in (res.data or []):
        try:
            img_bytes = _download_image(r["image_path"])
        except Exception as e:
            log.error("Image download failed for %s: %s", r["image_path"], e)
            img_bytes = b""
        pages.append({
            "id": r["id"],
            "week_id": r["week_id"],
            "flyer_filename": r["flyer_filename"],
            "page_no": r["page_no"],
            "png_data": img_bytes,
            "title": r.get("title", ""),
            "sort_order": r.get("sort_order", 0),
        })
    return pages


def update_poster_page(page_id: int, fields: dict, db_path=None):
    """Update title or sort_order of a poster page."""
    allowed = {"title", "sort_order"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    sb = _get_client()
    sb.table("poster_pages").update(to_set).eq("id", page_id).execute()


def delete_poster_page(page_id: int, db_path=None):
    """Delete a poster page by ID, including its mappings and storage image."""
    sb = _get_client()
    # Get page info
    res = (
        sb.table("poster_pages")
        .select("week_id, flyer_filename, page_no, image_path")
        .eq("id", page_id)
        .execute()
    )
    if res.data:
        row = res.data[0]
        # Delete associated mappings
        (
            sb.table("mappings")
            .delete()
            .eq("week_id", row["week_id"])
            .eq("flyer_filename", row["flyer_filename"])
            .eq("page_no", row["page_no"])
            .execute()
        )
        # Delete image from storage
        if row.get("image_path"):
            try:
                sb.storage.from_(BUCKET).remove([row["image_path"]])
            except Exception as e:
                log.warning("Storage delete: %s", e)
    # Delete page record
    sb.table("poster_pages").delete().eq("id", page_id).execute()


def delete_week(week_id: str, db_path=None):
    """Delete all data for a given week: pages, mappings, products, metadata, images."""
    sb = _get_client()
    # Get all image paths for this week
    res = (
        sb.table("poster_pages")
        .select("image_path")
        .eq("week_id", week_id)
        .execute()
    )
    paths = [r["image_path"] for r in (res.data or []) if r.get("image_path")]
    if paths:
        try:
            sb.storage.from_(BUCKET).remove(paths)
        except Exception as e:
            log.warning("Bulk storage delete: %s", e)

    sb.table("poster_pages").delete().eq("week_id", week_id).execute()
    sb.table("mappings").delete().eq("week_id", week_id).execute()
    sb.table("week_products").delete().eq("week_id", week_id).execute()
    sb.table("poster_weeks").delete().eq("week_id", week_id).execute()


# ============================================================================
# WEEK PRODUCTS — product queue from Excel
# ============================================================================

def save_week_products(week_id: str, products: list[dict], db_path=None):
    """Bulk save products for a week."""
    sb = _get_client()
    # Clear existing
    sb.table("week_products").delete().eq("week_id", week_id).execute()
    # Insert in batches of 100
    rows = []
    for i, p in enumerate(products):
        rows.append({
            "week_id": week_id,
            "urun_kodu": p.get("urun_kodu", ""),
            "urun_aciklamasi": p.get("urun_aciklamasi", ""),
            "afis_fiyat": p.get("afis_fiyat", ""),
            "source_row": i + 1,
            "is_mapped": False,
        })
    for batch_start in range(0, len(rows), 100):
        batch = rows[batch_start:batch_start + 100]
        sb.table("week_products").upsert(
            batch, on_conflict="week_id,urun_kodu"
        ).execute()


def get_week_products(week_id: str, db_path=None) -> list[dict]:
    """Return all products for a week, ordered by source_row."""
    sb = _get_client()
    res = (
        sb.table("week_products")
        .select("*")
        .eq("week_id", week_id)
        .order("source_row")
        .execute()
    )
    return res.data or []


def mark_product_mapped(week_id: str, urun_kodu: str, db_path=None):
    """Mark a product as mapped in the queue."""
    sb = _get_client()
    (
        sb.table("week_products")
        .update({"is_mapped": True})
        .eq("week_id", week_id)
        .eq("urun_kodu", urun_kodu)
        .execute()
    )


def unmark_product_mapped(week_id: str, urun_kodu: str, db_path=None):
    """Unmark a product (e.g. when mapping deleted)."""
    sb = _get_client()
    (
        sb.table("week_products")
        .update({"is_mapped": False})
        .eq("week_id", week_id)
        .eq("urun_kodu", urun_kodu)
        .execute()
    )


def get_mapped_product_codes(week_id: str, db_path=None) -> set[str]:
    """Return set of all urun_kodu that have at least one mapping in this week."""
    sb = _get_client()
    res = (
        sb.table("mappings")
        .select("urun_kodu")
        .eq("week_id", week_id)
        .not_.is_("urun_kodu", "null")
        .execute()
    )
    return {r["urun_kodu"] for r in (res.data or [])}


# ============================================================================
# POSTER WEEKS — week metadata & status
# ============================================================================

def save_week(week_id: str, week_name: str = "", start_date: str = "",
              end_date: str = "", status: str = "draft", db_path=None):
    """Create or update a week record."""
    sb = _get_client()
    sb.table("poster_weeks").upsert({
        "week_id": week_id,
        "week_name": week_name,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="week_id").execute()


def get_week(week_id: str, db_path=None) -> dict | None:
    """Return week metadata or None."""
    sb = _get_client()
    res = (
        sb.table("poster_weeks")
        .select("*")
        .eq("week_id", week_id)
        .execute()
    )
    return res.data[0] if res.data else None


def update_week_status(week_id: str, status: str, db_path=None):
    """Update week status (draft/published/archived)."""
    sb = _get_client()
    sb.table("poster_weeks").update({"status": status}).eq("week_id", week_id).execute()


def list_weeks_with_meta(db_path=None) -> list[dict]:
    """Return all weeks with metadata and stats."""
    sb = _get_client()
    # Get weeks
    weeks_res = sb.table("poster_weeks").select("*").order("created_at", desc=True).execute()
    weeks = weeks_res.data or []

    result = []
    for w in weeks:
        wid = w["week_id"]
        # Count pages
        pg_res = sb.table("poster_pages").select("id", count="exact").eq("week_id", wid).execute()
        # Count mappings
        mp_res = sb.table("mappings").select("mapping_id", count="exact").eq("week_id", wid).execute()
        # Count products
        pr_res = sb.table("week_products").select("id", count="exact").eq("week_id", wid).execute()
        result.append({
            **w,
            "page_count": pg_res.count or 0,
            "mapping_count": mp_res.count or 0,
            "product_count": pr_res.count or 0,
        })
    return result


# ============================================================================
# Frontend viewer helpers
# ============================================================================

def list_all_weeks(db_path=None) -> list[str]:
    """Return all distinct week_ids that have poster pages, most recent first."""
    sb = _get_client()
    res = (
        sb.table("poster_pages")
        .select("week_id")
        .order("week_id", desc=True)
        .execute()
    )
    # Deduplicate while preserving order
    seen = set()
    result = []
    for r in (res.data or []):
        wid = r["week_id"]
        if wid not in seen:
            seen.add(wid)
            result.append(wid)
    return result


def list_mappings_for_week(
    week_id: str, flyer_filename: str, page_no: int, db_path=None,
) -> list[dict]:
    """Alias — same as list_mappings, used by frontend viewer."""
    return list_mappings(week_id, flyer_filename, page_no, db_path)
