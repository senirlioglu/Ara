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
import time
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


def _fetch_page_with_retry(client, last_id: int, page_size: int, max_retries: int = 5):
    """Tek bir sayfayı cursor-based pagination + retry ile çek."""
    for attempt in range(max_retries):
        try:
            result = client.table('stok_gunluk')\
                .select('id, urun_kod, urun_ad, birim_fiyat')\
                .order('id')\
                .gt('id', last_id)\
                .limit(page_size)\
                .execute()
            return result.data or []
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Sayfa last_id={last_id} hata: {e}. {wait}s bekleyip tekrar deneniyor...")
                time.sleep(wait)
            else:
                raise


def _fetch_urunler_raw(client, page_size: int = 5000, max_rows: int = 900000):
    """stok_gunluk kaynağından ürün satırlarını cursor-based pagination ile çek."""
    rows_out = []
    last_id = 0
    page_num = 0

    while len(rows_out) < max_rows:
        rows = _fetch_page_with_retry(client, last_id, page_size)
        if not rows:
            break

        last_id = rows[-1]['id']
        rows_out.extend(rows)
        page_num += 1
        print(f"  Sayfa {page_num} OK: last_id={last_id}, satır={len(rows)}, toplam={len(rows_out)}")
        if len(rows) < page_size:
            break
        time.sleep(0.3)

    if not rows_out:
        return pd.DataFrame(columns=['urun_kod', 'urun_ad', 'birim_fiyat'])

    df = pd.DataFrame(rows_out)
    df.drop(columns=['id'], errors='ignore', inplace=True)
    if 'urun_kod' not in df.columns:
        df['urun_kod'] = ''
    if 'urun_ad' not in df.columns:
        df['urun_ad'] = ''
    if 'birim_fiyat' not in df.columns:
        df['birim_fiyat'] = None

    df['urun_kod'] = df['urun_kod'].fillna('').astype(str).str.strip()
    df['urun_ad'] = df['urun_ad'].fillna('').astype(str).str.strip()
    df['birim_fiyat'] = pd.to_numeric(df['birim_fiyat'], errors='coerce')
    df = df[df['urun_ad'] != '']

    return df.reset_index(drop=True)


def build_and_save_urun_master() -> tuple[int, int]:
    """urun_master + öneri listesi üretip kaydeder.

    Returns:
        (master_satir_sayisi, oneri_sayisi)
    """
    client = get_supabase_client()
    raw_df = _fetch_urunler_raw(client)
    if raw_df.empty:
        raise RuntimeError('Ürün verisi bulunamadı')

    # Master: kimlik güvenli tablo (kod + ad)
    master_df = raw_df.drop_duplicates(subset=['urun_kod', 'urun_ad']).reset_index(drop=True)
    master_df['urun_ad_normalized'] = master_df['urun_ad'].map(normalize_urun_ad)

    # Öneri kaynağı: kod + ad + fiyat bazında frekans (ham satırdan)
    if 'birim_fiyat' not in raw_df.columns:
        raw_df['birim_fiyat'] = None

    oneri_df = (
        raw_df.groupby(['urun_kod', 'urun_ad'], as_index=False)
        .agg(frekans=('birim_fiyat', 'size'), birim_fiyat=('birim_fiyat', 'median'))
        .sort_values(['frekans', 'urun_ad', 'urun_kod'], ascending=[False, True, True])
    )

    def _format_oneri(row) -> str:
        kod = str(row['urun_kod']).strip()
        ad = str(row['urun_ad']).strip()
        fiyat = row.get('birim_fiyat')
        fiyat_str = ""
        if pd.notna(fiyat) and fiyat > 0:
            # Tam sayıysa .00 gösterme
            fiyat_str = f"{fiyat:.0f}" if fiyat == int(fiyat) else f"{fiyat:.2f}"
        if kod and fiyat_str:
            return f"{kod} - {ad} - {fiyat_str}"
        if kod:
            return f"{kod} - {ad}"
        return ad

    oneri_listesi = oneri_df.apply(_format_oneri, axis=1).drop_duplicates().tolist()

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
