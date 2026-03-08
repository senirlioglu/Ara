"""SQLite persistence for flyer bbox-product mappings and poster pages."""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_DB = Path(__file__).resolve().parent / "mappings.db"


def _conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    p = str(db_path or _DEFAULT_DB)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path | None = None):
    """Create tables if they don't exist."""
    conn = _conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mappings (
            mapping_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id      TEXT NOT NULL,
            flyer_filename TEXT NOT NULL,
            page_no      INTEGER NOT NULL,
            x0           REAL NOT NULL,
            y0           REAL NOT NULL,
            x1           REAL NOT NULL,
            y1           REAL NOT NULL,
            urun_kodu    TEXT,
            urun_aciklamasi TEXT,
            afis_fiyat   TEXT,
            ocr_text     TEXT,
            source       TEXT NOT NULL DEFAULT 'suggested',
            status       TEXT NOT NULL DEFAULT 'matched',
            created_at   TEXT NOT NULL
        )
    """)
    # Poster pages — stores actual page images as BLOB
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poster_pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id        TEXT NOT NULL,
            flyer_filename TEXT NOT NULL,
            page_no        INTEGER NOT NULL,
            png_data       BLOB NOT NULL,
            title          TEXT DEFAULT '',
            sort_order     INTEGER DEFAULT 0,
            UNIQUE(week_id, flyer_filename, page_no)
        )
    """)
    # Week products — product queue from Excel
    conn.execute("""
        CREATE TABLE IF NOT EXISTS week_products (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id        TEXT NOT NULL,
            urun_kodu      TEXT NOT NULL,
            urun_aciklamasi TEXT,
            afis_fiyat     TEXT,
            source_row     INTEGER DEFAULT 0,
            is_mapped      INTEGER DEFAULT 0,
            UNIQUE(week_id, urun_kodu)
        )
    """)
    # Week metadata — status tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poster_weeks (
            week_id        TEXT PRIMARY KEY,
            week_name      TEXT DEFAULT '',
            start_date     TEXT,
            end_date       TEXT,
            status         TEXT DEFAULT 'draft',
            created_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ============================================================================
# MAPPINGS CRUD
# ============================================================================

def save_mapping(m: dict, db_path: str | Path | None = None) -> int:
    """Insert a mapping and return its ID."""
    conn = _conn(db_path)
    cur = conn.execute(
        """INSERT INTO mappings
           (week_id, flyer_filename, page_no, x0, y0, x1, y1,
            urun_kodu, urun_aciklamasi, afis_fiyat, ocr_text,
            source, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            m["week_id"],
            m["flyer_filename"],
            m["page_no"],
            m["x0"], m["y0"], m["x1"], m["y1"],
            m.get("urun_kodu"),
            m.get("urun_aciklamasi"),
            m.get("afis_fiyat"),
            m.get("ocr_text"),
            m.get("source", "suggested"),
            m.get("status", "matched"),
            m.get("created_at") or datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid


def list_mappings(
    week_id: str,
    flyer_filename: str,
    page_no: int,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Return all mappings for a given page."""
    conn = _conn(db_path)
    rows = conn.execute(
        """SELECT * FROM mappings
           WHERE week_id=? AND flyer_filename=? AND page_no=?
           ORDER BY mapping_id""",
        (week_id, flyer_filename, page_no),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_mappings_for_page(
    week_id: str,
    flyer_filename: str,
    page_no: int,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Alias for list_mappings."""
    return list_mappings(week_id, flyer_filename, page_no, db_path)


def update_mapping(mapping_id: int, fields: dict, db_path: str | Path | None = None):
    """Update specific fields of a mapping by ID."""
    allowed = {"urun_kodu", "urun_aciklamasi", "afis_fiyat", "source",
                "status", "x0", "y0", "x1", "y1"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    set_clause = ", ".join(f"{k}=?" for k in to_set)
    vals = list(to_set.values()) + [mapping_id]
    conn = _conn(db_path)
    conn.execute(f"UPDATE mappings SET {set_clause} WHERE mapping_id=?", vals)
    conn.commit()
    conn.close()


def delete_mapping(mapping_id: int, db_path: str | Path | None = None):
    """Delete a single mapping by ID."""
    conn = _conn(db_path)
    conn.execute("DELETE FROM mappings WHERE mapping_id=?", (mapping_id,))
    conn.commit()
    conn.close()


# ============================================================================
# POSTER PAGES — persistent image storage
# ============================================================================

def save_poster_page(
    week_id: str,
    flyer_filename: str,
    page_no: int,
    png_data: bytes,
    title: str = "",
    sort_order: int = 0,
    db_path: str | Path | None = None,
):
    """Save or replace a poster page image in the DB."""
    conn = _conn(db_path)
    conn.execute(
        """INSERT INTO poster_pages (week_id, flyer_filename, page_no, png_data, title, sort_order)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(week_id, flyer_filename, page_no)
           DO UPDATE SET png_data=excluded.png_data, title=excluded.title, sort_order=excluded.sort_order""",
        (week_id, flyer_filename, page_no, png_data, title, sort_order),
    )
    conn.commit()
    conn.close()


def save_poster_pages_bulk(pages: list[dict], db_path: str | Path | None = None):
    """Save multiple poster pages at once. Each dict needs: week_id, flyer_filename, page_no, png_data."""
    conn = _conn(db_path)
    for pg in pages:
        conn.execute(
            """INSERT INTO poster_pages (week_id, flyer_filename, page_no, png_data, title, sort_order)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(week_id, flyer_filename, page_no)
               DO UPDATE SET png_data=excluded.png_data""",
            (pg["week_id"], pg["flyer_filename"], pg["page_no"],
             pg["png_data"], pg.get("title", ""), pg.get("sort_order", 0)),
        )
    conn.commit()
    conn.close()


def get_poster_pages(
    week_id: str,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Return all poster pages for a week, ordered by sort_order then page_no."""
    conn = _conn(db_path)
    rows = conn.execute(
        """SELECT id, week_id, flyer_filename, page_no, png_data, title, sort_order
           FROM poster_pages
           WHERE week_id=?
           ORDER BY sort_order, flyer_filename, page_no""",
        (week_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_poster_page(page_id: int, fields: dict, db_path: str | Path | None = None):
    """Update title or sort_order of a poster page."""
    allowed = {"title", "sort_order"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return
    set_clause = ", ".join(f"{k}=?" for k in to_set)
    vals = list(to_set.values()) + [page_id]
    conn = _conn(db_path)
    conn.execute(f"UPDATE poster_pages SET {set_clause} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_poster_page(page_id: int, db_path: str | Path | None = None):
    """Delete a poster page by ID."""
    conn = _conn(db_path)
    conn.execute("DELETE FROM poster_pages WHERE id=?", (page_id,))
    conn.commit()
    conn.close()


def delete_week(week_id: str, db_path: str | Path | None = None):
    """Delete all poster pages AND mappings for a given week."""
    conn = _conn(db_path)
    conn.execute("DELETE FROM poster_pages WHERE week_id=?", (week_id,))
    conn.execute("DELETE FROM mappings WHERE week_id=?", (week_id,))
    conn.commit()
    conn.close()


# ============================================================================
# WEEK PRODUCTS — product queue from Excel
# ============================================================================

def save_week_products(week_id: str, products: list[dict], db_path: str | Path | None = None):
    """Bulk save products for a week. Each dict: urun_kodu, urun_aciklamasi, afis_fiyat."""
    conn = _conn(db_path)
    conn.execute("DELETE FROM week_products WHERE week_id=?", (week_id,))
    for i, p in enumerate(products):
        conn.execute(
            """INSERT OR IGNORE INTO week_products
               (week_id, urun_kodu, urun_aciklamasi, afis_fiyat, source_row, is_mapped)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (week_id, p.get("urun_kodu", ""), p.get("urun_aciklamasi", ""),
             p.get("afis_fiyat", ""), i + 1),
        )
    conn.commit()
    conn.close()


def get_week_products(week_id: str, db_path: str | Path | None = None) -> list[dict]:
    """Return all products for a week, ordered by source_row."""
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT * FROM week_products WHERE week_id=? ORDER BY source_row",
        (week_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_product_mapped(week_id: str, urun_kodu: str, db_path: str | Path | None = None):
    """Mark a product as mapped in the queue."""
    conn = _conn(db_path)
    conn.execute(
        "UPDATE week_products SET is_mapped=1 WHERE week_id=? AND urun_kodu=?",
        (week_id, urun_kodu),
    )
    conn.commit()
    conn.close()


def unmark_product_mapped(week_id: str, urun_kodu: str, db_path: str | Path | None = None):
    """Unmark a product (e.g. when mapping deleted)."""
    conn = _conn(db_path)
    conn.execute(
        "UPDATE week_products SET is_mapped=0 WHERE week_id=? AND urun_kodu=?",
        (week_id, urun_kodu),
    )
    conn.commit()
    conn.close()


def get_mapped_product_codes(week_id: str, db_path: str | Path | None = None) -> set[str]:
    """Return set of all urun_kodu that have at least one mapping in this week."""
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT urun_kodu FROM mappings WHERE week_id=? AND urun_kodu IS NOT NULL",
        (week_id,),
    ).fetchall()
    conn.close()
    return {r["urun_kodu"] for r in rows}


# ============================================================================
# POSTER WEEKS — week metadata & status
# ============================================================================

def save_week(week_id: str, week_name: str = "", start_date: str = "",
              end_date: str = "", status: str = "draft",
              db_path: str | Path | None = None):
    """Create or update a week record."""
    conn = _conn(db_path)
    conn.execute(
        """INSERT INTO poster_weeks (week_id, week_name, start_date, end_date, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(week_id) DO UPDATE SET
             week_name=excluded.week_name, start_date=excluded.start_date,
             end_date=excluded.end_date, status=excluded.status""",
        (week_id, week_name, start_date, end_date, status,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_week(week_id: str, db_path: str | Path | None = None) -> dict | None:
    """Return week metadata or None."""
    conn = _conn(db_path)
    row = conn.execute(
        "SELECT * FROM poster_weeks WHERE week_id=?", (week_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_week_status(week_id: str, status: str, db_path: str | Path | None = None):
    """Update week status (draft/published/archived)."""
    conn = _conn(db_path)
    conn.execute(
        "UPDATE poster_weeks SET status=? WHERE week_id=?", (status, week_id),
    )
    conn.commit()
    conn.close()


def list_weeks_with_meta(db_path: str | Path | None = None) -> list[dict]:
    """Return all weeks with metadata, stats (page count, mapping count)."""
    conn = _conn(db_path)
    rows = conn.execute("""
        SELECT
            pw.week_id, pw.week_name, pw.start_date, pw.end_date,
            pw.status, pw.created_at,
            (SELECT COUNT(*) FROM poster_pages pp WHERE pp.week_id = pw.week_id) as page_count,
            (SELECT COUNT(*) FROM mappings m WHERE m.week_id = pw.week_id) as mapping_count,
            (SELECT COUNT(*) FROM week_products wp WHERE wp.week_id = pw.week_id) as product_count
        FROM poster_weeks pw
        ORDER BY pw.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================================
# Frontend viewer helpers
# ============================================================================

def list_all_weeks(db_path: str | Path | None = None) -> list[str]:
    """Return all distinct week_ids that have poster pages, most recent first."""
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT week_id FROM poster_pages ORDER BY week_id DESC"
    ).fetchall()
    conn.close()
    return [r["week_id"] for r in rows]


def list_mappings_for_week(
    week_id: str,
    flyer_filename: str,
    page_no: int,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Alias — same as list_mappings, used by frontend viewer."""
    return list_mappings(week_id, flyer_filename, page_no, db_path)
