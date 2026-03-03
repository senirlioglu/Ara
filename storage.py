import sqlite3
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id TEXT NOT NULL,
    flyer_filename TEXT NOT NULL,
    page_no INTEGER NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    urun_kodu TEXT NOT NULL,
    urun_aciklamasi TEXT NOT NULL,
    afis_fiyat TEXT NULL,
    ocr_text TEXT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db(db_path: str = "mappings.db"):
    with sqlite3.connect(db_path) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def save_mapping(mapping_dict: dict[str, Any], db_path: str = "mappings.db") -> int:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO mappings (
                week_id, flyer_filename, page_no, x0, y0, x1, y1,
                urun_kodu, urun_aciklamasi, afis_fiyat, ocr_text,
                source, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapping_dict["week_id"],
                mapping_dict["flyer_filename"],
                mapping_dict["page_no"],
                mapping_dict["bbox_norm"]["x0"],
                mapping_dict["bbox_norm"]["y0"],
                mapping_dict["bbox_norm"]["x1"],
                mapping_dict["bbox_norm"]["y1"],
                mapping_dict["urun_kodu"],
                mapping_dict["urun_aciklamasi"],
                str(mapping_dict.get("afis_fiyat")) if mapping_dict.get("afis_fiyat") is not None else None,
                mapping_dict.get("ocr_text"),
                mapping_dict["source"],
                mapping_dict["status"],
                mapping_dict["created_at"],
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_mappings(week_id: str, flyer_filename: str, page_no: int, db_path: str = "mappings.db") -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM mappings
            WHERE week_id=? AND flyer_filename=? AND page_no=?
            ORDER BY id DESC
            """,
            (week_id, flyer_filename, page_no),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_mapping(mapping_id: int, db_path: str = "mappings.db"):
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM mappings WHERE id=?", (mapping_id,))
        conn.commit()
