"""Excel product import service."""

from __future__ import annotations

import io
import logging
import re

import pandas as pd
from sqlalchemy import text

from ..db import get_db

log = logging.getLogger(__name__)

_TR_MAP = str.maketrans("İŞĞÖÜÇıişğöüç", "ISGOUCiisgouc")


def _normalize(s: str) -> str:
    """Turkish-aware normalize for search: upper + tr-map + strip punct."""
    s = s.upper().translate(_TR_MAP)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _detect_columns(df: pd.DataFrame) -> dict[str, str]:
    """Auto-detect column name mapping."""
    col_map = {}
    for c in df.columns:
        cu = str(c).strip().upper()
        if "KOD" in cu:
            col_map[c] = "urun_kod"
        elif "AÇIKLAMA" in cu or "ACIKLAMA" in cu or "AD" in cu:
            col_map[c] = "urun_ad"
    return col_map


async def import_excel_bytes(week_id: str, excel_bytes: bytes) -> int:
    """Parse Excel and upsert products into DB. Returns count imported."""
    df = pd.read_excel(io.BytesIO(excel_bytes))

    col_map = _detect_columns(df)
    if col_map:
        df = df.rename(columns=col_map)

    if "urun_kod" not in df.columns:
        raise ValueError("Excel'de 'ürün kodu' sütunu bulunamadı")

    count = 0
    async with get_db() as db:
        for _, row in df.iterrows():
            kod = str(row.get("urun_kod", "")).strip()
            if not kod:
                continue
            ad = str(row.get("urun_ad", "")).strip() if "urun_ad" in row else None
            normalized = _normalize(f"{kod} {ad or ''}")

            await db.execute(text("""
                INSERT INTO products (week_id, urun_kod, urun_ad, normalized)
                VALUES (:wid, :kod, :ad, :norm)
                ON CONFLICT (week_id, urun_kod)
                DO UPDATE SET urun_ad    = EXCLUDED.urun_ad,
                              normalized = EXCLUDED.normalized
            """), {"wid": week_id, "kod": kod, "ad": ad, "norm": normalized})
            count += 1

        # Update week product count
        await db.execute(text("""
            UPDATE weeks SET product_count = :cnt, updated_at = now()
            WHERE week_id = :wid
        """), {"wid": week_id, "cnt": count})

    log.info("Imported %d products for week %s", count, week_id)
    return count
