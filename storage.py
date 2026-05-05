"""Supabase persistence for flyer bbox-product mappings and poster pages.

All poster images are stored in Supabase Storage ('poster-images' bucket).
Metadata + mappings live in Supabase PostgreSQL tables.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Storage path whitelist — path traversal ve kontrol karakterlerine karşı koruma
_UNSAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_path_segment(value: str, fallback: str = "file") -> str:
    """Normalize a user-provided string for use in a storage object key."""
    s = _UNSAFE_CHAR_RE.sub("_", str(value or ""))
    # Leading dots ve "." / ".." gibi path traversal formlarını önle
    s = s.lstrip(".") or fallback
    # Uzun bir path segmentini kısalt (Supabase key 1024B limit; pratik sınır)
    return s[:200]

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
        key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or st.secrets.get("SUPABASE_KEY")
        )
        if not url or not key:
            log.error("SUPABASE_URL or SUPABASE_KEY not set")
            return None
        _client = create_client(url, key)
        return _client
    except Exception as e:
        log.error("Supabase client error: %s", e)
        return None


BUCKET = "poster-images"
PRODUCT_IMG_BUCKET = "product-images"          # cropped-from-poster bbox images (.jpg)
MASTER_PRODUCT_IMG_BUCKET = "urun-resimleri"   # e-commerce master product images (.webp)


def _sb_execute_with_retry(query, retries=3, base_delay=0.5):
    """Execute a Supabase query with retry + exponential backoff.

    Catches httpx transport/protocol errors that occur under heavy
    request load (e.g. many HEAD count queries in a tight loop).
    """
    for attempt in range(retries):
        try:
            return query.execute()
        except Exception as exc:
            # Retry on httpx transport-level errors (RemoteProtocolError, etc.)
            exc_name = type(exc).__name__
            is_transport = "ProtocolError" in exc_name or "TransportError" in exc_name
            if is_transport and attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning("Supabase request failed (%s), retry %d/%d in %.1fs",
                            exc_name, attempt + 1, retries, delay)
                time.sleep(delay)
                continue
            raise


def _ensure_bucket():
    """Create the storage buckets if they don't exist (idempotent)."""
    sb = _get_client()
    if not sb:
        return
    for bucket_name in (BUCKET, PRODUCT_IMG_BUCKET):
        try:
            sb.storage.get_bucket(bucket_name)
        except Exception:
            try:
                sb.storage.create_bucket(bucket_name, options={"public": True})
            except Exception as e:
                log.warning("Bucket create %s: %s", bucket_name, e)


# ---------------------------------------------------------------------------
# Helper — no-op init_db (kept for backward compat, tables created via SQL)
# ---------------------------------------------------------------------------

def init_db(db_path=None):
    """Ensure storage bucket exists and run lightweight migrations."""
    _ensure_bucket()
    _ensure_week_sort_order()


def _ensure_week_sort_order():
    """Add sort_order column to poster_weeks if it doesn't exist yet."""
    sb = _get_client()
    if sb is None:
        return
    try:
        sb.table("poster_weeks").select("sort_order").limit(1).execute()
    except Exception:
        try:
            sb.rpc("exec_sql", {"query": "ALTER TABLE poster_weeks ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0"}).execute()
        except Exception:
            log.warning("Could not add sort_order column — run migration SQL manually")


# ============================================================================
# MAPPINGS CRUD
# ============================================================================

_MAPPING_ALLOWED_FIELDS = {
    "week_id", "flyer_filename", "page_no",
    "x0", "y0", "x1", "y1",
    "urun_kodu", "urun_aciklamasi", "afis_fiyat", "ocr_text",
    "source", "status", "created_at",
}


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
    # Mass assignment koruması — sadece whitelist alanlar DB'ye gitsin
    row = {k: v for k, v in row.items() if k in _MAPPING_ALLOWED_FIELDS}
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


def list_all_mappings_for_week(week_id: str, db_path=None) -> list[dict]:
    """Return all mappings for a week in a single query."""
    sb = _get_client()
    res = (
        sb.table("mappings")
        .select("*")
        .eq("week_id", week_id)
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


def delete_mapping(mapping_id: int, db_path=None, week_id: str = None):
    """Delete a single mapping by ID, guarded by week_id when provided.

    week_id verilmediğinde güvenlik audit log'u yazılır (IDOR riski).
    """
    sb = _get_client()
    if week_id is None:
        log.warning("delete_mapping called without week_id (ownership check atlandı): mapping_id=%s", mapping_id)
    q = sb.table("mappings").delete().eq("mapping_id", mapping_id)
    if week_id:
        q = q.eq("week_id", week_id)
    q.execute()


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
    # Deterministic path so upsert works. Hem week_id hem filename whitelist
    # ile normalize edilir (path traversal + kontrol karakterlerine karşı).
    safe_week = _safe_path_segment(week_id, fallback="week")
    safe_name = _safe_path_segment(flyer_filename, fallback="file")
    path = f"{safe_week}/{safe_name}_p{int(page_no)}.jpg"
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


def get_poster_pages_meta(week_id: str, db_path=None) -> list[dict]:
    """Return poster page metadata WITHOUT downloading images.

    Use this for admin views that only need page info (titles, sort order, counts).
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
    return [{
        "id": r["id"],
        "week_id": r["week_id"],
        "flyer_filename": r["flyer_filename"],
        "page_no": r["page_no"],
        "image_path": r.get("image_path", ""),
        "title": r.get("title", ""),
        "sort_order": r.get("sort_order", 0),
    } for r in (res.data or [])]


def update_poster_page(page_id: int, fields: dict, db_path=None):
    """Update title or sort_order of a poster page."""
    allowed = {"title", "sort_order"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    sb = _get_client()
    sb.table("poster_pages").update(to_set).eq("id", page_id).execute()


def delete_poster_page(page_id: int, db_path=None, week_id: str = None):
    """Delete a poster page by ID, including its mappings and storage image.

    week_id verilirse ownership doğrulanır; verilmezse audit log yazılır.
    """
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
        if week_id is not None and row["week_id"] != week_id:
            log.warning(
                "delete_poster_page ownership mismatch: page=%s expected_week=%s actual=%s",
                page_id, week_id, row["week_id"],
            )
            raise PermissionError(
                f"Page {page_id} does not belong to week {week_id}"
            )
        if week_id is None:
            log.warning(
                "delete_poster_page called without week_id (ownership check atlandı): page_id=%s",
                page_id,
            )
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
    # Deduplicate by urun_kodu (keep first occurrence)
    seen = set()
    rows = []
    for i, p in enumerate(products):
        code = p.get("urun_kodu", "")
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({
            "week_id": week_id,
            "urun_kodu": code,
            "urun_aciklamasi": p.get("urun_aciklamasi", ""),
            "afis_fiyat": p.get("afis_fiyat", ""),
            "source_row": i + 1,
            "is_mapped": False,
        })
    # Insert in batches of 100
    for batch_start in range(0, len(rows), 100):
        batch = rows[batch_start:batch_start + 100]
        sb.table("week_products").insert(batch).execute()


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


# ---------------------------------------------------------------------------
# Batch operations for flush (reduces N round-trips to ~3)
# ---------------------------------------------------------------------------

def save_mappings_bulk(mappings: list[dict], db_path=None) -> list[int]:
    """Insert multiple mappings in a single request. Returns new IDs."""
    if not mappings:
        return []
    sb = _get_client()
    rows = []
    for m in mappings:
        rows.append({
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
        })
    res = sb.table("mappings").insert(rows).execute()
    return [r["mapping_id"] for r in (res.data or [])]


def delete_mappings_bulk(mapping_ids: list[int], week_id: str = None, db_path=None):
    """Delete multiple mappings by ID in a single request."""
    if not mapping_ids:
        return
    sb = _get_client()
    q = sb.table("mappings").delete().in_("mapping_id", mapping_ids)
    if week_id:
        q = q.eq("week_id", week_id)
    q.execute()


def update_mappings_bulk(updates: dict[int, dict], db_path=None):
    """Apply multiple mapping updates. Groups by identical field sets for efficiency."""
    if not updates:
        return
    sb = _get_client()
    # For each mapping_id, apply update individually (Supabase doesn't support
    # batch update with different values per row without RPC)
    # But we can group updates with identical payloads
    from collections import defaultdict
    groups: dict[tuple, list[int]] = defaultdict(list)
    for mid, fields in updates.items():
        allowed = {"urun_kodu", "urun_aciklamasi", "afis_fiyat", "source",
                   "status", "x0", "y0", "x1", "y1"}
        to_set = {k: v for k, v in fields.items() if k in allowed}
        key = tuple(sorted(to_set.items()))
        groups[key].append(mid)

    for field_tuple, mids in groups.items():
        to_set = dict(field_tuple)
        if not to_set:
            continue
        sb.table("mappings").update(to_set).in_("mapping_id", mids).execute()


def mark_products_mapped_bulk(week_id: str, codes: set[str], mapped: bool = True, db_path=None):
    """Mark/unmark multiple product codes in a single request."""
    if not codes:
        return
    sb = _get_client()
    code_list = list(codes)
    sb.table("week_products").update(
        {"is_mapped": mapped}
    ).eq("week_id", week_id).in_("urun_kodu", code_list).execute()


# ============================================================================
# POSTER WEEKS — week metadata & status
# ============================================================================

def save_week(week_id: str, week_name: str = "", start_date: str = "",
              end_date: str = "", status: str = "draft", sort_order: int = 0,
              db_path=None):
    """Create or update a week record."""
    sb = _get_client()
    row = {
        "week_id": week_id,
        "week_name": week_name,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "status": status,
        "sort_order": sort_order,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sb.table("poster_weeks").upsert(row, on_conflict="week_id").execute()
    except Exception:
        # sort_order column may not exist yet — retry without it
        row.pop("sort_order", None)
        sb.table("poster_weeks").upsert(row, on_conflict="week_id").execute()


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


def update_week_sort_order(week_id: str, sort_order: int, db_path=None):
    """Update week display sort order."""
    sb = _get_client()
    try:
        sb.table("poster_weeks").update({"sort_order": sort_order}).eq("week_id", week_id).execute()
    except Exception:
        log.warning("Could not update sort_order for %s — column may not exist yet", week_id)


def list_weeks_with_meta(db_path=None) -> list[dict]:
    """Return all weeks with metadata and stats.

    Uses 3 bulk GROUP BY queries (one per table) instead of 3*N individual
    count queries. Reduces Supabase round-trips from 3N+1 to 4 total.
    """
    sb = _get_client()
    # Fetch all weeks
    try:
        weeks_res = sb.table("poster_weeks").select("*").execute()
    except Exception:
        weeks_res = sb.table("poster_weeks").select("*").order("created_at", desc=True).execute()
    weeks = weeks_res.data or []

    if not weeks:
        return []

    # Sort: sort_order>0 first (ASC, newest first as tiebreaker),
    # then sort_order=0 by newest created_at
    ordered = [w for w in weeks if (w.get("sort_order") or 0) > 0]
    unordered = [w for w in weeks if (w.get("sort_order") or 0) == 0]

    from functools import cmp_to_key
    def _cmp_ordered_weeks(a, b):
        sa, sb_ = a.get("sort_order") or 0, b.get("sort_order") or 0
        if sa != sb_:
            return -1 if sa < sb_ else 1
        ca, cb = a.get("created_at") or "", b.get("created_at") or ""
        if ca > cb:
            return -1
        if ca < cb:
            return 1
        return 0
    ordered.sort(key=cmp_to_key(_cmp_ordered_weeks))
    unordered.sort(key=lambda w: w.get("created_at") or "", reverse=True)
    weeks = ordered + unordered

    # Bulk counts: 3 queries total instead of 3*N
    page_counts: dict[str, int] = {}
    mapping_counts: dict[str, int] = {}
    product_counts: dict[str, int] = {}

    # Try RPC first (single round-trip), fall back to 3 group-by selects
    try:
        rpc_res = sb.rpc("get_week_counts", {}).execute()
        if rpc_res.data:
            for r in rpc_res.data:
                wid = r["week_id"]
                page_counts[wid] = r.get("page_count", 0)
                mapping_counts[wid] = r.get("mapping_count", 0)
                product_counts[wid] = r.get("product_count", 0)
    except Exception:
        # RPC not installed yet — use server-side HEAD count per week_id.
        # Cannot use select("week_id") fallback because PostgREST caps rows
        # (default 1000) which silently truncates counts on large tables.
        week_ids = [w["week_id"] for w in weeks]
        for wid in week_ids:
            try:
                pg = sb.table("poster_pages").select("*", count="exact", head=True).eq("week_id", wid).execute()
                page_counts[wid] = pg.count or 0
            except Exception:
                page_counts[wid] = 0
            try:
                mp = sb.table("mappings").select("*", count="exact", head=True).eq("week_id", wid).execute()
                mapping_counts[wid] = mp.count or 0
            except Exception:
                mapping_counts[wid] = 0
            try:
                pr = sb.table("week_products").select("*", count="exact", head=True).eq("week_id", wid).execute()
                product_counts[wid] = pr.count or 0
            except Exception:
                product_counts[wid] = 0

    result = []
    for w in weeks:
        wid = w["week_id"]
        result.append({
            **w,
            "page_count": page_counts.get(wid, 0),
            "mapping_count": mapping_counts.get(wid, 0),
            "product_count": product_counts.get(wid, 0),
        })
    return result


# ============================================================================
# Frontend viewer helpers
# ============================================================================

def list_all_weeks(db_path=None) -> list[str]:
    """Return all distinct week_ids that have poster pages.

    Ordering: sort_order>0 first (ASC), then sort_order=0 by newest created_at.
    """
    sb = _get_client()

    # Get week_ids from poster_pages
    pages_res = sb.table("poster_pages").select("week_id").execute()
    page_week_ids = set()
    for r in (pages_res.data or []):
        page_week_ids.add(r["week_id"])

    if not page_week_ids:
        return []

    # Get metadata from poster_weeks for ordering
    try:
        weeks_res = sb.table("poster_weeks").select("week_id,sort_order,created_at").execute()
    except Exception:
        weeks_res = sb.table("poster_weeks").select("week_id,created_at").execute()

    # Build lookup: week_id → {sort_order, created_at}
    meta = {}
    for r in (weeks_res.data or []):
        meta[r["week_id"]] = r

    # Sort: explicit sort_order>0 first (ASC), then unset (0) by newest created_at
    has_order = []
    no_order = []
    orphans = []
    for wid in page_week_ids:
        m = meta.get(wid)
        if m is None:
            orphans.append(wid)
        elif (m.get("sort_order") or 0) > 0:
            has_order.append((m["sort_order"], m.get("created_at") or "", wid))
        else:
            no_order.append((m.get("created_at") or "", wid))

    # sort_order ASC; for equal sort_order, newest created_at first
    from functools import cmp_to_key
    def _cmp_ordered(a, b):
        if a[0] != b[0]:
            return -1 if a[0] < b[0] else 1
        # Same sort_order → reverse by created_at (newest first)
        if a[1] > b[1]:
            return -1
        if a[1] < b[1]:
            return 1
        return 0
    has_order.sort(key=cmp_to_key(_cmp_ordered))
    no_order.sort(key=lambda x: x[0], reverse=True)
    orphans.sort(reverse=True)

    return [x[-1] for x in has_order] + [wid for _, wid in no_order] + orphans


def list_mappings_for_week(
    week_id: str, flyer_filename: str, page_no: int, db_path=None,
) -> list[dict]:
    """Alias — same as list_mappings, used by frontend viewer."""
    return list_mappings(week_id, flyer_filename, page_no, db_path)


# ============================================================================
# PRODUCT IMAGES — crop bbox regions from poster pages, save as {urun_kodu}.jpg
# ============================================================================

def _crop_and_encode(page_png_bytes: bytes, x0: float, y0: float,
                     x1: float, y1: float, quality: int = 85) -> bytes:
    """Crop a normalised bbox (0-1) from a page image and return JPEG bytes."""
    from PIL import Image
    img = Image.open(io.BytesIO(page_png_bytes))
    w, h = img.size
    left = int(x0 * w)
    top = int(y0 * h)
    right = int(x1 * w)
    bottom = int(y1 * h)
    cropped = img.crop((left, top, right, bottom))
    if cropped.mode == "RGBA":
        cropped = cropped.convert("RGB")
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def upload_product_image(urun_kodu: str, jpeg_bytes: bytes) -> str:
    """Upload a product image to Supabase Storage. Returns the storage path.

    Path: product-images/{urun_kodu}.jpg  (upsert — overwrites if exists)
    """
    sb = _get_client()
    if not sb:
        return ""
    safe_code = urun_kodu.replace("/", "_").replace(" ", "_")
    path = f"{safe_code}.jpg"
    try:
        sb.storage.from_(PRODUCT_IMG_BUCKET).upload(
            path, jpeg_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
    except Exception:
        try:
            sb.storage.from_(PRODUCT_IMG_BUCKET).update(
                path, jpeg_bytes,
                file_options={"content-type": "image/jpeg"},
            )
        except Exception as e:
            log.error("Product image upload failed for %s: %s", urun_kodu, e)
    return path


def get_product_image_url(urun_kodu: str) -> str:
    """Return the public URL for a product image."""
    sb = _get_client()
    if not sb:
        return ""
    safe_code = urun_kodu.replace("/", "_").replace(" ", "_")
    return sb.storage.from_(PRODUCT_IMG_BUCKET).get_public_url(f"{safe_code}.jpg")


def crop_and_upload_product_image(
    page_png_bytes: bytes, urun_kodu: str,
    x0: float, y0: float, x1: float, y1: float,
) -> str:
    """Crop bbox from page image and upload as product image. Returns path."""
    if not urun_kodu:
        return ""
    jpeg_bytes = _crop_and_encode(page_png_bytes, x0, y0, x1, y1)
    return upload_product_image(urun_kodu, jpeg_bytes)


def backfill_product_images(week_id: str, progress_callback=None) -> dict:
    """Bulk-generate product images for all mappings in a week.

    Downloads poster pages, crops each mapping's bbox, uploads as
    {urun_kodu}.jpg. Skips mappings without urun_kodu.

    Returns {"total": N, "uploaded": M, "skipped": S, "errors": E}
    """
    pages = get_poster_pages(week_id)
    mappings = list_all_mappings_for_week(week_id)

    # Build page lookup: (flyer_filename, page_no) → png_data
    page_lookup = {}
    for pg in pages:
        key = (pg["flyer_filename"], pg["page_no"])
        page_lookup[key] = pg["png_data"]

    stats = {"total": len(mappings), "uploaded": 0, "skipped": 0, "errors": 0}

    for i, m in enumerate(mappings):
        urun_kodu = m.get("urun_kodu")
        if not urun_kodu:
            stats["skipped"] += 1
            continue

        page_key = (m["flyer_filename"], m["page_no"])
        png_data = page_lookup.get(page_key)
        if not png_data:
            stats["skipped"] += 1
            continue

        try:
            crop_and_upload_product_image(
                png_data, urun_kodu,
                m["x0"], m["y0"], m["x1"], m["y1"],
            )
            stats["uploaded"] += 1
        except Exception as e:
            log.error("Backfill crop failed for %s: %s", urun_kodu, e)
            stats["errors"] += 1

        if progress_callback:
            progress_callback(i + 1, stats["total"])

    return stats
