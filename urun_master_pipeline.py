"""Ürün master üretim pipeline'ı.

Amaç:
- stok_gunluk güncellendiğinde unique ürün listesini tek yerde üretmek
- urun_kod, urun_ad, urun_ad_normalized kolonlarını saklamak
- Streamlit'in hızlı yükleyebilmesi için parquet/json çıktıları üretmek
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd


DATA_DIR = Path("data")
MASTER_PARQUET = DATA_DIR / "urun_master.parquet"
MASTER_JSON = DATA_DIR / "urun_master.json"
ONERI_JSON = DATA_DIR / "oneri_listesi.json"


def normalize_urun_ad(text: str) -> str:
    """SQL normalize_tr_search ile uyumlu sade normalize."""
    if not text:
        return ""

    tr_map = {
        'İ': 'i', 'I': 'i', 'ı': 'i',
        'Ğ': 'g', 'ğ': 'g',
        'Ü': 'u', 'ü': 'u',
        'Ş': 's', 'ş': 's',
        'Ö': 'o', 'ö': 'o',
        'Ç': 'c', 'ç': 'c',
    }

    result = text
    for tr_char, ascii_char in tr_map.items():
        result = result.replace(tr_char, ascii_char)

    result = unicodedata.normalize('NFKD', result)
    result = ''.join(c for c in result if not unicodedata.combining(c))
    result = result.lower()

    result = result.replace('makinasi', 'makine')
    result = result.replace('makinesi', 'makine')
    result = result.replace('makina', 'makine')

    for c, r in {
        '\u201c': '', '\u201d': '', '\u2019': '',
        '\u00a0': ' ', '\u0307': '',
    }.items():
        result = result.replace(c, r)

    result = re.sub(r'(tv|televizyon)(\d)', r'\1 \2', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def get_supabase_client():
    from supabase import create_client

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        raise RuntimeError('SUPABASE_URL/SUPABASE_KEY gerekli')
    return create_client(url, key)


def _fetch_urunler(client, page_size: int = 50000, max_scan_rows: int = 900000):
    """stok_gunluk kaynağından ürünleri sayfalı çek (frekans için tekrarlar korunur)."""
    rows_out = []
    for offset in range(0, max_scan_rows, page_size):
        result = client.table('stok_gunluk')\
            .select('urun_kod, urun_ad')\
            .range(offset, offset + page_size - 1)\
            .execute()

        rows = result.data or []
        if not rows:
            break

        rows_out.extend(rows)
        if len(rows) < page_size:
            break

    if not rows_out:
        return pd.DataFrame(columns=['urun_kod', 'urun_ad'])

    df = pd.DataFrame(rows_out)
    if 'urun_kod' not in df.columns:
        df['urun_kod'] = ''
    if 'urun_ad' not in df.columns:
        df['urun_ad'] = ''

    df['urun_kod'] = df['urun_kod'].fillna('').astype(str).str.strip()
    df['urun_ad'] = df['urun_ad'].fillna('').astype(str).str.strip()
    df = df[df['urun_ad'] != '']

    return df.reset_index(drop=True)


def build_and_save_urun_master() -> tuple[int, int]:
    """urun_master + öneri listesi üretip kaydeder.

    Returns:
        (master_satir_sayisi, oneri_sayisi)
    """
    client = get_supabase_client()
    raw_df = _fetch_urunler(client)
    if raw_df.empty:
        raise RuntimeError('Ürün verisi bulunamadı')

    raw_df['urun_ad_normalized'] = raw_df['urun_ad'].map(normalize_urun_ad)

    # Master: kod + ad bazlı tekilleştirilmiş ürün listesi
    master_df = raw_df.drop_duplicates(
        subset=['urun_kod', 'urun_ad']
    ).reset_index(drop=True)

    # Öneri kaynağı: kod + ad bazlı unique, frekansa göre sıralı
    oneri_df = (
        raw_df.groupby(['urun_kod', 'urun_ad', 'urun_ad_normalized'], as_index=False)
        .size()
        .rename(columns={'size': 'frekans'})
        .sort_values(['frekans', 'urun_ad', 'urun_kod'], ascending=[False, True, True])
    )

    oneri_listesi = [
        f"{kod} - {ad}" if kod else ad
        for kod, ad in zip(oneri_df['urun_kod'], oneri_df['urun_ad'])
    ]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    master_df.to_parquet(MASTER_PARQUET, index=False)
    master_df.to_json(MASTER_JSON, orient='records', force_ascii=False)

    with ONERI_JSON.open('w', encoding='utf-8') as f:
        json.dump(oneri_listesi, f, ensure_ascii=False)

    return len(master_df), len(oneri_listesi)


if __name__ == '__main__':
    master_count, oneri_count = build_and_save_urun_master()
    print(f'urun_master üretildi: {master_count} satır')
    print(f'oneri_listesi üretildi: {oneri_count} kayıt')
