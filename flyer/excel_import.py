"""Excel import — reads weekly product Excel, normalizes columns."""

from __future__ import annotations

from io import BytesIO

import pandas as pd


# Column name mapping (Turkish → normalized)
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
}


def _normalize_col(col: str) -> str:
    key = col.strip().upper().replace("\u0130", "I")
    return _COL_MAP.get(key, col)


def read_weekly_excel(file_or_path, sheet: int = 0) -> pd.DataFrame:
    """Read Excel and normalize column names.

    Returns DataFrame with columns: urun_kodu, urun_aciklamasi, afis_fiyat, ...
    """
    if isinstance(file_or_path, (str, bytes)):
        df = pd.read_excel(file_or_path, sheet_name=sheet, dtype=str)
    else:
        df = pd.read_excel(BytesIO(file_or_path.read()), sheet_name=sheet, dtype=str)

    df.columns = [_normalize_col(c) for c in df.columns]

    if "urun_kodu" not in df.columns and "urun_aciklamasi" not in df.columns:
        raise ValueError(
            f"Excel'de 'ÜRÜN KODU' veya 'ÜRÜN AÇIKLAMASI' sütunu bulunamadı. "
            f"Bulunan: {list(df.columns)}"
        )

    return df
