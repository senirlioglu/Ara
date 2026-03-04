"""SQLite persistence for flyer bbox-product mappings."""

from __future__ import annotations

import sqlite3
import json
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
    """Create the mappings table if it doesn't exist."""
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
    conn.commit()
    conn.close()


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
    """Update specific fields of a mapping by ID.

    *fields* is a dict of column-name → new-value.  Only the columns
    ``urun_kodu``, ``urun_aciklamasi``, ``afis_fiyat``, ``source``,
    ``status``, ``x0``, ``y0``, ``x1``, ``y1`` are allowed.
    """
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
