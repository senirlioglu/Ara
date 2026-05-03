"""Supabase persistence for Halk Günü events.

Halk Günü = belirli tarihte belirli mağazalarda belirli ürünlerin indirimli
satıldığı etkinlik. Bu modül Ara'nın `storage.py` modülünü tamamlar; aynı
Supabase projesi, aynı `poster-images` ve `product-images` bucket'ları
paylaşılır. Path çakışmasını engellemek için poster yolları
`halkgunu/{event_id}/...` prefix'iyle yazılır.

Tablolar (bkz. halkgunu_schema.sql):
  halkgunu_events     — etkinlik metadata
  halkgunu_products   — Excel'den yüklenen indirimli ürün listesi
  halkgunu_pages      — afiş sayfaları
  halkgunu_mappings   — bbox-ürün eşleştirmeleri

Mağaza bilgisi `magazalar`, canlı stok `stok_gunluk` tablosundan join ile alınır.
"""

from __future__ import annotations

import logging
import pathlib
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from storage import (
    BUCKET,
    PRODUCT_IMG_BUCKET,
    _crop_and_encode,
    _get_client,
    _safe_path_segment,
    crop_and_upload_product_image,
    get_product_image_url,
    upload_product_image,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage path helpers — poster-images bucket'ı Ara ile paylaşıldığı için
# halkgunu/ prefix'i ile namespace ediyoruz.
# ---------------------------------------------------------------------------

_HALKGUNU_PREFIX = "halkgunu"


def _hg_image_path(event_id: str, flyer_filename: str, page_no: int) -> str:
    safe_event = _safe_path_segment(event_id, fallback="event")
    safe_name = _safe_path_segment(flyer_filename, fallback="file")
    return f"{_HALKGUNU_PREFIX}/{safe_event}/{safe_name}_p{int(page_no)}.jpg"


def _hg_upload_image(event_id: str, flyer_filename: str, page_no: int,
                     image_bytes: bytes) -> str:
    """Upload poster page image under halkgunu/ prefix; returns storage path."""
    sb = _get_client()
    if not sb:
        return ""
    path = _hg_image_path(event_id, flyer_filename, page_no)
    try:
        sb.storage.from_(BUCKET).upload(
            path, image_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
    except Exception as e:
        log.warning("Halk Günü upload fallback: %s", e)
        try:
            sb.storage.from_(BUCKET).update(
                path, image_bytes,
                file_options={"content-type": "image/jpeg"},
            )
        except Exception as e2:
            log.error("Halk Günü upload failed: %s", e2)
    return path


def _hg_get_image_url(path: str) -> str:
    sb = _get_client()
    if not sb:
        return ""
    return sb.storage.from_(BUCKET).get_public_url(path)


def _hg_download_image(path: str) -> bytes:
    sb = _get_client()
    return sb.storage.from_(BUCKET).download(path)


# ============================================================================
# EVENTS CRUD — halkgunu_events
# ============================================================================

def save_event(event_id: str, event_name: str, event_date: str,
               status: str = "draft", sort_order: int = 0) -> None:
    """Create or update a Halk Günü event record."""
    sb = _get_client()
    if not sb:
        return
    row = {
        "event_id": event_id,
        "event_name": event_name,
        "event_date": event_date or None,
        "status": status,
        "sort_order": sort_order,
    }
    sb.table("halkgunu_events").upsert(row, on_conflict="event_id").execute()


def get_event(event_id: str) -> dict | None:
    sb = _get_client()
    if not sb:
        return None
    res = sb.table("halkgunu_events").select("*").eq("event_id", event_id).execute()
    return res.data[0] if res.data else None


def update_event_status(event_id: str, status: str) -> None:
    sb = _get_client()
    if not sb:
        return
    sb.table("halkgunu_events").update({"status": status}).eq("event_id", event_id).execute()


def update_event_sort_order(event_id: str, sort_order: int) -> None:
    sb = _get_client()
    if not sb:
        return
    sb.table("halkgunu_events").update({"sort_order": sort_order}).eq("event_id", event_id).execute()


def update_event_meta(event_id: str, event_name: str | None = None,
                      event_date: str | None = None) -> None:
    """Update event display fields (name and/or date). Pass None to skip a field."""
    sb = _get_client()
    if not sb:
        return
    payload: dict = {}
    if event_name is not None:
        payload["event_name"] = event_name
    if event_date is not None:
        payload["event_date"] = event_date or None
    if not payload:
        return
    sb.table("halkgunu_events").update(payload).eq("event_id", event_id).execute()


def delete_event(event_id: str) -> None:
    """Delete a Halk Günü event and all related data (pages, mappings, products, images)."""
    sb = _get_client()
    if not sb:
        return
    # Collect storage paths first
    res = sb.table("halkgunu_pages").select("image_path").eq("event_id", event_id).execute()
    paths = [r["image_path"] for r in (res.data or []) if r.get("image_path")]
    if paths:
        try:
            sb.storage.from_(BUCKET).remove(paths)
        except Exception as e:
            log.warning("Halk Günü bulk storage delete: %s", e)

    # ON DELETE CASCADE handles child tables, but we trigger explicitly
    # so older Supabase deployments without FK cascade still work.
    sb.table("halkgunu_pages").delete().eq("event_id", event_id).execute()
    sb.table("halkgunu_mappings").delete().eq("event_id", event_id).execute()
    sb.table("halkgunu_products").delete().eq("event_id", event_id).execute()
    sb.table("halkgunu_events").delete().eq("event_id", event_id).execute()


def list_events_with_meta() -> list[dict]:
    """Return all events with counts (page/mapping/product/store).

    Tries get_halkgunu_counts() RPC first; falls back to per-event HEAD counts.
    """
    sb = _get_client()
    if not sb:
        return []
    try:
        events_res = sb.table("halkgunu_events").select("*").execute()
    except Exception:
        return []
    events = events_res.data or []
    if not events:
        return []

    ordered = [e for e in events if (e.get("sort_order") or 0) > 0]
    unordered = [e for e in events if (e.get("sort_order") or 0) == 0]
    ordered.sort(key=lambda e: (
        e.get("sort_order") or 0,
        -1 * _date_to_int(e.get("event_date")),
    ))
    unordered.sort(key=lambda e: e.get("event_date") or "", reverse=True)
    events = ordered + unordered

    page_counts: dict[str, int] = {}
    mapping_counts: dict[str, int] = {}
    product_counts: dict[str, int] = {}
    store_counts: dict[str, int] = {}

    try:
        rpc_res = sb.rpc("get_halkgunu_counts", {}).execute()
        if rpc_res.data:
            for r in rpc_res.data:
                eid = r["event_id"]
                page_counts[eid] = r.get("page_count", 0)
                mapping_counts[eid] = r.get("mapping_count", 0)
                product_counts[eid] = r.get("product_count", 0)
                store_counts[eid] = r.get("store_count", 0)
    except Exception:
        for e in events:
            eid = e["event_id"]
            for table, target in (
                ("halkgunu_pages", page_counts),
                ("halkgunu_mappings", mapping_counts),
                ("halkgunu_products", product_counts),
            ):
                try:
                    r = sb.table(table).select("*", count="exact", head=True).eq("event_id", eid).execute()
                    target[eid] = r.count or 0
                except Exception:
                    target[eid] = 0
            # Distinct store fallback (best effort)
            try:
                r = sb.table("halkgunu_products").select("magaza_kod").eq("event_id", eid).execute()
                store_counts[eid] = len({row["magaza_kod"] for row in (r.data or []) if row.get("magaza_kod")})
            except Exception:
                store_counts[eid] = 0

    return [
        {
            **e,
            "page_count": page_counts.get(e["event_id"], 0),
            "mapping_count": mapping_counts.get(e["event_id"], 0),
            "product_count": product_counts.get(e["event_id"], 0),
            "store_count": store_counts.get(e["event_id"], 0),
        }
        for e in events
    ]


def list_all_events() -> list[dict]:
    """Public-friendly listing for halkgunu.net (active events, sorted by date desc).

    Returns minimal fields for tab rendering.
    """
    sb = _get_client()
    if not sb:
        return []
    try:
        res = (
            sb.table("halkgunu_events")
            .select("event_id, event_name, event_date, status, sort_order")
            .eq("status", "active")
            .order("sort_order", desc=False)
            .order("event_date", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        log.error("list_all_events failed: %s", e)
        return []


def _date_to_int(d) -> int:
    """Sort helper — turn ISO date string into yyyymmdd int (0 if missing)."""
    if not d:
        return 0
    try:
        return int(str(d)[:10].replace("-", ""))
    except Exception:
        return 0


def get_max_event_sort_order() -> int:
    sb = _get_client()
    if not sb:
        return 0
    res = (
        sb.table("halkgunu_events")
        .select("sort_order")
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data[0]["sort_order"] if res.data else 0) or 0


# ============================================================================
# PAGES CRUD — halkgunu_pages
# ============================================================================

def save_page(event_id: str, flyer_filename: str, page_no: int,
              png_data: bytes, title: str = "", sort_order: int = 0) -> None:
    image_path = _hg_upload_image(event_id, flyer_filename, page_no, png_data)
    sb = _get_client()
    if not sb:
        return
    sb.table("halkgunu_pages").upsert({
        "event_id": event_id,
        "flyer_filename": flyer_filename,
        "page_no": page_no,
        "image_path": image_path,
        "title": title,
        "sort_order": sort_order,
    }, on_conflict="event_id,flyer_filename,page_no").execute()


def save_pages_bulk(pages: list[dict]) -> None:
    sb = _get_client()
    if not sb:
        return
    rows = []
    for pg in pages:
        image_path = _hg_upload_image(
            pg["event_id"], pg["flyer_filename"], pg["page_no"], pg["png_data"],
        )
        rows.append({
            "event_id": pg["event_id"],
            "flyer_filename": pg["flyer_filename"],
            "page_no": pg["page_no"],
            "image_path": image_path,
            "title": pg.get("title", ""),
            "sort_order": pg.get("sort_order", 0),
        })
    if rows:
        sb.table("halkgunu_pages").upsert(
            rows, on_conflict="event_id,flyer_filename,page_no",
        ).execute()


def get_event_pages(event_id: str) -> list[dict]:
    """Return pages for an event WITH downloaded image bytes (for previews)."""
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_pages")
        .select("id, event_id, flyer_filename, page_no, image_path, title, sort_order")
        .eq("event_id", event_id)
        .order("sort_order")
        .order("flyer_filename")
        .order("page_no")
        .execute()
    )
    pages = res.data or []
    for p in pages:
        try:
            p["png_data"] = _hg_download_image(p["image_path"])
        except Exception as e:
            log.warning("Halk Günü page download failed (%s): %s", p.get("image_path"), e)
            p["png_data"] = b""
        p["url"] = _hg_get_image_url(p["image_path"]) if p.get("image_path") else ""
    return pages


def get_event_pages_meta(event_id: str) -> list[dict]:
    """Return pages metadata WITHOUT downloading images (admin lists)."""
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_pages")
        .select("id, event_id, flyer_filename, page_no, image_path, title, sort_order")
        .eq("event_id", event_id)
        .order("sort_order")
        .order("flyer_filename")
        .order("page_no")
        .execute()
    )
    pages = res.data or []
    for p in pages:
        p["url"] = _hg_get_image_url(p["image_path"]) if p.get("image_path") else ""
    return pages


def update_page(page_id: int, fields: dict) -> None:
    allowed = {"title", "sort_order"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    sb = _get_client()
    if not sb:
        return
    sb.table("halkgunu_pages").update(to_set).eq("id", page_id).execute()


def delete_page(page_id: int, event_id: str | None = None) -> None:
    sb = _get_client()
    if not sb:
        return
    q = sb.table("halkgunu_pages").select("image_path, event_id, flyer_filename, page_no").eq("id", page_id)
    if event_id:
        q = q.eq("event_id", event_id)
    res = q.execute()
    rows = res.data or []
    if not rows:
        return
    row = rows[0]
    img = row.get("image_path")
    if img:
        try:
            sb.storage.from_(BUCKET).remove([img])
        except Exception as e:
            log.warning("Halk Günü page image delete: %s", e)
    # Cascade mappings for that page
    sb.table("halkgunu_mappings").delete().eq("event_id", row["event_id"]) \
        .eq("flyer_filename", row["flyer_filename"]) \
        .eq("page_no", row["page_no"]).execute()
    sb.table("halkgunu_pages").delete().eq("id", page_id).execute()


def get_max_page_sort_order(event_id: str) -> int:
    sb = _get_client()
    if not sb:
        return 0
    res = (
        sb.table("halkgunu_pages")
        .select("sort_order")
        .eq("event_id", event_id)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data[0]["sort_order"] if res.data else 0) or 0


# ============================================================================
# MAPPINGS CRUD — halkgunu_mappings
# ============================================================================

_MAPPING_FIELDS = {
    "event_id", "flyer_filename", "page_no",
    "x0", "y0", "x1", "y1",
    "urun_kodu", "urun_aciklamasi", "afis_fiyat", "ocr_text",
    "source", "status", "created_at",
}


def save_mapping(m: dict) -> int | None:
    sb = _get_client()
    if not sb:
        return None
    row = {
        "event_id": m["event_id"],
        "flyer_filename": m["flyer_filename"],
        "page_no": m["page_no"],
        "x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
        "urun_kodu": m.get("urun_kodu"),
        "urun_aciklamasi": m.get("urun_aciklamasi"),
        "afis_fiyat": m.get("afis_fiyat"),
        "ocr_text": m.get("ocr_text"),
        "source": m.get("source", "manual"),
        "status": m.get("status", "matched"),
        "created_at": m.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    row = {k: v for k, v in row.items() if k in _MAPPING_FIELDS}
    res = sb.table("halkgunu_mappings").insert(row).execute()
    return res.data[0]["mapping_id"] if res.data else None


def list_page_mappings(event_id: str, flyer_filename: str, page_no: int) -> list[dict]:
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_mappings")
        .select("*")
        .eq("event_id", event_id)
        .eq("flyer_filename", flyer_filename)
        .eq("page_no", page_no)
        .order("mapping_id")
        .execute()
    )
    return res.data or []


def list_event_mappings(event_id: str) -> list[dict]:
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_mappings")
        .select("*")
        .eq("event_id", event_id)
        .order("mapping_id")
        .execute()
    )
    return res.data or []


def update_mapping(mapping_id: int, fields: dict) -> None:
    allowed = {"urun_kodu", "urun_aciklamasi", "afis_fiyat", "source",
               "status", "x0", "y0", "x1", "y1"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    sb = _get_client()
    if not sb:
        return
    sb.table("halkgunu_mappings").update(to_set).eq("mapping_id", mapping_id).execute()


def delete_mapping(mapping_id: int, event_id: str | None = None) -> None:
    sb = _get_client()
    if not sb:
        return
    q = sb.table("halkgunu_mappings").delete().eq("mapping_id", mapping_id)
    if event_id:
        q = q.eq("event_id", event_id)
    q.execute()


def save_mappings_bulk(mappings: list[dict]) -> list[int]:
    if not mappings:
        return []
    sb = _get_client()
    if not sb:
        return []
    rows = []
    for m in mappings:
        rows.append({
            "event_id": m["event_id"],
            "flyer_filename": m["flyer_filename"],
            "page_no": m["page_no"],
            "x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
            "urun_kodu": m.get("urun_kodu"),
            "urun_aciklamasi": m.get("urun_aciklamasi"),
            "afis_fiyat": m.get("afis_fiyat"),
            "ocr_text": m.get("ocr_text"),
            "source": m.get("source", "manual"),
            "status": m.get("status", "matched"),
            "created_at": m.get("created_at") or datetime.now(timezone.utc).isoformat(),
        })
    res = sb.table("halkgunu_mappings").insert(rows).execute()
    return [r["mapping_id"] for r in (res.data or [])]


def delete_mappings_bulk(mapping_ids: list[int], event_id: str | None = None) -> None:
    if not mapping_ids:
        return
    sb = _get_client()
    if not sb:
        return
    q = sb.table("halkgunu_mappings").delete().in_("mapping_id", mapping_ids)
    if event_id:
        q = q.eq("event_id", event_id)
    q.execute()


def update_mappings_bulk(updates: dict[int, dict]) -> None:
    if not updates:
        return
    sb = _get_client()
    if not sb:
        return
    allowed = {"urun_kodu", "urun_aciklamasi", "afis_fiyat", "source",
               "status", "x0", "y0", "x1", "y1"}
    groups: dict[tuple, list[int]] = defaultdict(list)
    for mid, fields in updates.items():
        to_set = {k: v for k, v in fields.items() if k in allowed}
        groups[tuple(sorted(to_set.items()))].append(mid)
    for field_tuple, mids in groups.items():
        to_set = dict(field_tuple)
        if not to_set:
            continue
        sb.table("halkgunu_mappings").update(to_set).in_("mapping_id", mids).execute()


# ============================================================================
# PRODUCTS — halkgunu_products (Excel-loaded discounted product list)
# ============================================================================

def save_event_products(event_id: str, products: list[dict]) -> int:
    """Replace all products for an event. Each row needs at minimum:
        urun_kod, magaza_kod
    Optional: urun_ad, normal_fiyat, indirimli_fiyat
    Returns number of inserted rows.
    """
    sb = _get_client()
    if not sb:
        return 0
    sb.table("halkgunu_products").delete().eq("event_id", event_id).execute()

    seen: set[tuple] = set()
    rows: list[dict] = []
    for p in products:
        urun = (p.get("urun_kod") or "").strip()
        magaza = (p.get("magaza_kod") or "").strip()
        if not urun or not magaza:
            continue
        key = (urun, magaza)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "event_id": event_id,
            "urun_kod": urun,
            "urun_ad": (p.get("urun_ad") or "").strip() or None,
            "magaza_kod": magaza,
            "normal_fiyat": _safe_decimal(p.get("normal_fiyat")),
            "indirimli_fiyat": _safe_decimal(p.get("indirimli_fiyat")),
        })
    inserted = 0
    for start in range(0, len(rows), 200):
        batch = rows[start:start + 200]
        sb.table("halkgunu_products").insert(batch).execute()
        inserted += len(batch)
    return inserted


def _safe_decimal(value):
    if value is None or value == "":
        return None
    try:
        # tolerate strings like "42.999,90" or "42,999.90"
        s = str(value).strip().replace(" ", "")
        if "," in s and "." in s:
            # assume European format (1.234,56)
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return None


def get_event_products(event_id: str) -> list[dict]:
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_products")
        .select("*")
        .eq("event_id", event_id)
        .order("urun_kod")
        .order("magaza_kod")
        .execute()
    )
    return res.data or []


def get_event_product_codes(event_id: str) -> set[str]:
    """Distinct urun_kod set for an event (used by mapping UI to filter queue)."""
    sb = _get_client()
    if not sb:
        return set()
    res = sb.table("halkgunu_products").select("urun_kod").eq("event_id", event_id).execute()
    return {r["urun_kod"] for r in (res.data or []) if r.get("urun_kod")}


def get_event_product_summary(event_id: str) -> list[dict]:
    """Distinct (urun_kod, urun_ad) with min indirimli_fiyat — for list-mode UI."""
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_products")
        .select("urun_kod, urun_ad, normal_fiyat, indirimli_fiyat")
        .eq("event_id", event_id)
        .execute()
    )
    rows = res.data or []
    by_code: dict[str, dict] = {}
    for r in rows:
        kod = r.get("urun_kod")
        if not kod:
            continue
        cur = by_code.get(kod)
        ind = r.get("indirimli_fiyat")
        nor = r.get("normal_fiyat")
        if cur is None:
            by_code[kod] = {
                "urun_kod": kod,
                "urun_ad": r.get("urun_ad"),
                "min_indirimli": ind,
                "max_normal": nor,
            }
        else:
            if ind is not None and (cur["min_indirimli"] is None or ind < cur["min_indirimli"]):
                cur["min_indirimli"] = ind
            if nor is not None and (cur["max_normal"] is None or nor > cur["max_normal"]):
                cur["max_normal"] = nor
            if not cur["urun_ad"] and r.get("urun_ad"):
                cur["urun_ad"] = r.get("urun_ad")
    return sorted(by_code.values(), key=lambda x: x["urun_kod"])


def get_product_stores(event_id: str, urun_kod: str) -> list[dict]:
    """Stores offering this discounted product. Joins magazalar + stok_gunluk via RPC."""
    sb = _get_client()
    if not sb:
        return []
    try:
        res = sb.rpc("get_halkgunu_product_stores", {
            "p_event_id": event_id,
            "p_urun_kod": urun_kod,
        }).execute()
        return res.data or []
    except Exception as e:
        log.warning("get_halkgunu_product_stores RPC failed, falling back: %s", e)

    # Fallback: 3 separate queries when RPC is missing
    res = (
        sb.table("halkgunu_products")
        .select("magaza_kod, normal_fiyat, indirimli_fiyat")
        .eq("event_id", event_id)
        .eq("urun_kod", urun_kod)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return []
    codes = list({r["magaza_kod"] for r in rows if r.get("magaza_kod")})

    mag_map: dict[str, dict] = {}
    if codes:
        try:
            m_res = sb.table("magazalar").select("*").in_("magaza_kod", codes).execute()
            mag_map = {m["magaza_kod"]: m for m in (m_res.data or [])}
        except Exception:
            pass

    stok_map: dict[str, int] = {}
    if codes:
        try:
            s_res = (
                sb.table("stok_gunluk")
                .select("magaza_kod, stok_adet")
                .eq("urun_kod", urun_kod)
                .in_("magaza_kod", codes)
                .execute()
            )
            stok_map = {s["magaza_kod"]: s.get("stok_adet", 0) for s in (s_res.data or [])}
        except Exception:
            pass

    out = []
    for r in rows:
        kod = r.get("magaza_kod")
        m = mag_map.get(kod, {})
        out.append({
            "magaza_kod": kod,
            "magaza_adi": m.get("magaza_adi") or kod,
            "latitude": m.get("latitude"),
            "longitude": m.get("longitude"),
            "adres": m.get("adres"),
            "normal_fiyat": r.get("normal_fiyat"),
            "indirimli_fiyat": r.get("indirimli_fiyat"),
            "stok_adet": stok_map.get(kod, 0),
        })
    out.sort(key=lambda x: (
        x["indirimli_fiyat"] if x["indirimli_fiyat"] is not None else 9e12,
        x["magaza_adi"] or "",
    ))
    return out


# ============================================================================
# PRODUCT IMAGES — re-export Ara helpers (shared product-images bucket)
# ============================================================================

def upload_event_product_image(urun_kod: str, jpeg_bytes: bytes) -> str:
    """Upload product image (uses Ara's shared product-images bucket)."""
    return upload_product_image(urun_kod, jpeg_bytes)


def get_event_product_image_url(urun_kod: str) -> str:
    return get_product_image_url(urun_kod)


def list_event_product_image_status(event_id: str) -> dict[str, bool]:
    """Returns {urun_kod: has_image_in_bucket}. Useful for "missing image" admin view."""
    sb = _get_client()
    if not sb:
        return {}
    codes = sorted(get_event_product_codes(event_id))
    if not codes:
        return {}
    # List bucket once and intersect
    have: set[str] = set()
    try:
        listed = sb.storage.from_(PRODUCT_IMG_BUCKET).list("", {"limit": 10000})
        for obj in listed or []:
            name = obj.get("name") or ""
            if name.endswith(".jpg"):
                have.add(name[:-4])
    except Exception as e:
        log.warning("product-images list failed: %s", e)
    return {kod: ((kod.replace("/", "_").replace(" ", "_")) in have) for kod in codes}


def backfill_event_product_images(event_id: str, progress_callback=None) -> dict:
    """Crop+upload product images from Halk Günü mappings.

    Mirrors storage.backfill_product_images but for halkgunu_pages/mappings.
    """
    pages = get_event_pages(event_id)
    mappings = list_event_mappings(event_id)
    page_lookup = {(p["flyer_filename"], p["page_no"]): p["png_data"] for p in pages}

    stats = {"total": len(mappings), "uploaded": 0, "skipped": 0, "errors": 0}
    for i, m in enumerate(mappings):
        urun = m.get("urun_kodu")
        if not urun:
            stats["skipped"] += 1
            continue
        png = page_lookup.get((m["flyer_filename"], m["page_no"]))
        if not png:
            stats["skipped"] += 1
            continue
        try:
            crop_and_upload_product_image(png, urun, m["x0"], m["y0"], m["x1"], m["y1"])
            stats["uploaded"] += 1
        except Exception as e:
            log.error("Halk Günü backfill crop failed for %s: %s", urun, e)
            stats["errors"] += 1
        if progress_callback:
            progress_callback(i + 1, stats["total"])
    return stats


# ============================================================================
# PHOTOS CRUD — halkgunu_photos ("Bizden Fotoğraflar")
# ----------------------------------------------------------------------------
# Mağaza ziyaretlerinde çekilen fotoğraflar. Frontend halkgunu.net'te yeşil
# "Bizden Fotoğraflar" sekmesinde grid olarak görünür. Foto/mağaza ilişkisi
# opsiyonel (magaza_kod NULL olabilir). Bucket: poster-images, path:
# photos/{event_id}/{uuid}.{ext}  (halkgunu/ prefix'i değil — frontend
# kontratı bu yolda bekliyor).
# ============================================================================

_HALKGUNU_PHOTO_PREFIX = "photos"

_PHOTO_FIELDS = {"event_id", "magaza_kod", "image_path", "caption", "sort_order"}

_PHOTO_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _hg_photo_path(event_id: str, original_filename: str) -> str:
    """Build a unique storage path for a photo upload."""
    safe_event = _safe_path_segment(event_id, fallback="event")
    ext = pathlib.Path(original_filename or "").suffix.lower()
    if ext not in _PHOTO_CONTENT_TYPES:
        ext = ".jpg"
    return f"{_HALKGUNU_PHOTO_PREFIX}/{safe_event}/{uuid.uuid4().hex}{ext}"


def _hg_upload_photo(path: str, image_bytes: bytes,
                     content_type: str | None = None) -> bool:
    """Upload a photo to poster-images bucket. Returns True on success."""
    sb = _get_client()
    if not sb:
        return False
    if not content_type:
        ext = pathlib.Path(path).suffix.lower()
        content_type = _PHOTO_CONTENT_TYPES.get(ext, "image/jpeg")
    try:
        sb.storage.from_(BUCKET).upload(
            path, image_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return True
    except Exception as e:
        log.warning("Halk Günü photo upload fallback: %s", e)
        try:
            sb.storage.from_(BUCKET).update(
                path, image_bytes,
                file_options={"content-type": content_type},
            )
            return True
        except Exception as e2:
            log.error("Halk Günü photo upload failed: %s", e2)
            return False


def get_photo_public_url(image_path: str) -> str:
    """Public URL for a stored photo (poster-images bucket)."""
    sb = _get_client()
    if not sb or not image_path:
        return ""
    return sb.storage.from_(BUCKET).get_public_url(image_path)


def get_max_photo_sort_order(event_id: str) -> int:
    sb = _get_client()
    if not sb:
        return 0
    res = (
        sb.table("halkgunu_photos")
        .select("sort_order")
        .eq("event_id", event_id)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    return (res.data[0]["sort_order"] if res.data else 0) or 0


def save_photo(event_id: str, image_path: str,
               magaza_kod: str | None = None,
               caption: str | None = None,
               sort_order: int | None = None) -> int | None:
    """Insert a halkgunu_photos row. If sort_order is None, append (max+1)."""
    sb = _get_client()
    if not sb:
        return None
    if sort_order is None:
        sort_order = (get_max_photo_sort_order(event_id) or 0) + 1
    row = {
        "event_id": event_id,
        "image_path": image_path,
        "magaza_kod": (magaza_kod or None) or None,
        "caption": (caption or None) or None,
        "sort_order": int(sort_order or 0),
    }
    res = sb.table("halkgunu_photos").insert(row).execute()
    return res.data[0]["id"] if res.data else None


def list_event_photos(event_id: str) -> list[dict]:
    """All photos for an event, ordered by sort_order then id."""
    sb = _get_client()
    if not sb:
        return []
    res = (
        sb.table("halkgunu_photos")
        .select("*")
        .eq("event_id", event_id)
        .order("sort_order")
        .order("id")
        .execute()
    )
    return res.data or []


def update_photo(photo_id: int, fields: dict) -> None:
    sb = _get_client()
    if not sb:
        return
    payload = {k: v for k, v in (fields or {}).items() if k in _PHOTO_FIELDS}
    if not payload:
        return
    # Empty strings → NULL for nullable cols
    for k in ("magaza_kod", "caption"):
        if k in payload and isinstance(payload[k], str) and not payload[k].strip():
            payload[k] = None
    if "sort_order" in payload and payload["sort_order"] is not None:
        payload["sort_order"] = int(payload["sort_order"])
    sb.table("halkgunu_photos").update(payload).eq("id", photo_id).execute()


def delete_photo(photo_id: int, also_storage: bool = True) -> None:
    """Delete a photo row; optionally remove the underlying storage object."""
    sb = _get_client()
    if not sb:
        return
    image_path = ""
    if also_storage:
        try:
            res = (
                sb.table("halkgunu_photos")
                .select("image_path")
                .eq("id", photo_id)
                .limit(1)
                .execute()
            )
            if res.data:
                image_path = res.data[0].get("image_path") or ""
        except Exception as e:
            log.warning("Halk Günü photo lookup before delete failed: %s", e)
    sb.table("halkgunu_photos").delete().eq("id", photo_id).execute()
    if also_storage and image_path:
        try:
            sb.storage.from_(BUCKET).remove([image_path])
        except Exception as e:
            log.warning("Halk Günü photo storage delete: %s", e)


# ============================================================================
# MAGAZALAR — read-only, photo dropdown için
# ============================================================================

def list_magazalar() -> list[dict]:
    """Return [{magaza_kod, magaza_adi}] for the photo store dropdown."""
    sb = _get_client()
    if not sb:
        return []
    try:
        res = (
            sb.table("magazalar")
            .select("magaza_kod, magaza_adi")
            .order("magaza_kod")
            .execute()
        )
    except Exception as e:
        log.warning("magazalar list failed: %s", e)
        return []
    return res.data or []
