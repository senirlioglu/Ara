"""Excel import – reads weekly flyer Excel and upserts into poster_items."""

from __future__ import annotations

from io import BytesIO
from typing import Optional

import pandas as pd

from poster.db import get_supabase


# Column name mapping (Turkish → DB)
_COL_MAP = {
    "ÜRÜN KODU": "urun_kodu",
    "URUN KODU": "urun_kodu",
    "ÜRÜN_KODU": "urun_kodu",
    "URUN_KODU": "urun_kodu",
    "ÜRÜN AÇIKLAMASI": "urun_aciklamasi",
    "URUN ACIKLAMASI": "urun_aciklamasi",
    "ÜRÜN_AÇIKLAMASI": "urun_aciklamasi",
    "URUN_ACIKLAMASI": "urun_aciklamasi",
    "AFIS_FIYAT": "afis_fiyat",
    "AFİŞ_FİYAT": "afis_fiyat",
    "AFIS FIYAT": "afis_fiyat",
    "AFİŞ FİYAT": "afis_fiyat",
    "FIYAT": "afis_fiyat",
    "FİYAT": "afis_fiyat",
    "SAYFA_NO": "page_no",
    "SAYFA NO": "page_no",
    "AFIS_ID": "poster_id",
    "AFİŞ_ID": "poster_id",
}


def _normalize_col_name(col: str) -> str:
    """Uppercase + strip → lookup in _COL_MAP."""
    key = col.strip().upper().replace("\u0130", "I")  # İ → I
    return _COL_MAP.get(key, col)


def read_excel(file_or_path, sheet: int = 0) -> pd.DataFrame:
    """Read an Excel file and normalize column names."""
    if isinstance(file_or_path, (str, bytes)):
        df = pd.read_excel(file_or_path, sheet_name=sheet, dtype=str)
    else:
        # Streamlit UploadedFile (file-like)
        df = pd.read_excel(BytesIO(file_or_path.read()), sheet_name=sheet, dtype=str)

    df.columns = [_normalize_col_name(c) for c in df.columns]
    return df


def import_excel_to_poster_items(
    file_or_path,
    poster_id: int,
    sheet: int = 0,
) -> tuple[int, int]:
    """Read Excel → upsert rows into poster_items.

    Returns (inserted_count, skipped_count).
    """
    client = get_supabase()
    if not client:
        raise RuntimeError("Supabase bağlantısı kurulamadı")

    df = read_excel(file_or_path, sheet)

    if "urun_kodu" not in df.columns and "urun_aciklamasi" not in df.columns:
        raise ValueError(
            "Excel dosyasında 'ÜRÜN KODU' veya 'ÜRÜN AÇIKLAMASI' sütunu bulunamadı. "
            f"Bulunan sütunlar: {list(df.columns)}"
        )

    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        urun_kodu = str(row.get("urun_kodu", "") or "").strip()
        # Excel bazen sayısal kodları float olarak okur: "9035.0" → "9035"
        if urun_kodu.endswith(".0") and urun_kodu[:-2].isdigit():
            urun_kodu = urun_kodu[:-2]
        urun_aciklamasi = str(row.get("urun_aciklamasi", "") or "").strip()

        if not urun_kodu and not urun_aciklamasi:
            skipped += 1
            continue

        afis_fiyat = str(row.get("afis_fiyat", "") or "").strip() or None
        page_no_raw = row.get("page_no")
        page_no: Optional[int] = None
        if page_no_raw and str(page_no_raw).strip().isdigit():
            page_no = int(page_no_raw)

        # Check duplicate (same poster + urun_kodu)
        if urun_kodu:
            existing = (
                client.table("poster_items")
                .select("id")
                .eq("poster_id", poster_id)
                .eq("urun_kodu", urun_kodu)
                .limit(1)
                .execute()
            )
            if existing.data:
                # Update existing
                client.table("poster_items").update({
                    "urun_aciklamasi": urun_aciklamasi,
                    "afis_fiyat": afis_fiyat,
                    "page_no": page_no,
                }).eq("id", existing.data[0]["id"]).execute()
                inserted += 1
                continue

        new_row = {
            "poster_id": poster_id,
            "urun_kodu": urun_kodu or None,
            "urun_aciklamasi": urun_aciklamasi or None,
            "afis_fiyat": afis_fiyat,
            "page_no": page_no,
            "status": "pending",
        }
        client.table("poster_items").insert(new_row).execute()
        inserted += 1

    return inserted, skipped
