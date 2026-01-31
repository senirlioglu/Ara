"""
URUN ARAMA UYGULAMASI
=====================
Musteriye hangi magazada urun oldugunu gostermek icin basit arama uygulamasi.

Stok Seviyeleri:
- 1: Kritik (kirmizi)
- 2-5: Dusuk (turuncu)
- 6-10: Normal (yesil)
- 11+: Yuksek (mavi)
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime, time
from typing import Optional

# Sayfa ayarlari
st.set_page_config(
    page_title="Urun Ara",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# PWA Meta Tag'leri ve Service Worker
st.markdown("""
<link rel="manifest" href="/app/static/manifest.json">
<meta name="theme-color" content="#1e3a5f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Urun Ara">
<link rel="apple-touch-icon" href="/app/static/icon-192.png">
<script>
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/app/static/sw.js')
            .then(function(registration) {
                console.log('SW registered: ', registration);
            })
            .catch(function(error) {
                console.log('SW registration failed: ', error);
            });
    });
}
</script>
""", unsafe_allow_html=True)

# CSS - Stok seviyeleri icin renkler
st.markdown("""
<style>
    .stok-kritik {
        background-color: #ff4444 !important;
        color: white !important;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .stok-dusuk {
        background-color: #ff9800 !important;
        color: white !important;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .stok-normal {
        background-color: #4caf50 !important;
        color: white !important;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .stok-yuksek {
        background-color: #2196f3 !important;
        color: white !important;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .stok-yok {
        background-color: #9e9e9e !important;
        color: white !important;
        padding: 4px 8px;
        border-radius: 4px;
    }

    /* Buyuk arama kutusu */
    .stSearchInput > div > div > input {
        font-size: 1.2rem !important;
        padding: 12px !important;
    }

    /* Tablo baslik */
    .dataframe th {
        background-color: #1e3a5f !important;
        color: white !important;
    }

    /* Mobil uyumluluk */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SUPABASE BAGLANTISI
# ============================================================================

@st.cache_resource
def get_supabase_client():
    """Supabase client olustur"""
    try:
        from supabase import create_client

        # Environment variable'dan oku
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')

        # Secrets'dan oku (varsa)
        if not url:
            try:
                url = st.secrets.get('SUPABASE_URL')
            except:
                pass
        if not key:
            try:
                key = st.secrets.get('SUPABASE_KEY')
            except:
                pass

        if not url or not key:
            return None

        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase baglanti hatasi: {e}")
        return None


def get_cache_date() -> str:
    """
    Cache icin tarih key'i dondur.
    Saat 11'den once: onceki gunun tarihini kullan
    Saat 11'den sonra: bugunun tarihini kullan
    Boylece her gun saat 11'de cache yenilenir (stok 10'da yukleniyor).
    """
    now = datetime.now()
    if now.time() < time(11, 0):
        # Saat 11'den once, onceki gunun verisini kullan
        cache_date = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                      - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        # Saat 11'den sonra, bugunun verisini kullan
        cache_date = now.strftime('%Y-%m-%d')
    return cache_date


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_stok(cache_key: str) -> Optional[pd.DataFrame]:
    """
    Tum stok verisini yukle ve cache'le.
    cache_key her gun saat 11'de degisir, boylece veri yenilenir.
    Pagination ile tum veriyi ceker.
    """
    client = get_supabase_client()
    if not client:
        return None

    try:
        all_data = []
        batch_size = 50000  # Her seferde 50K kayit (daha hizli)
        offset = 0
        expected_total = 650000  # Tahmini toplam kayit

        progress_bar = st.progress(0, text="Stok verisi yukleniyor...")

        while True:
            result = client.table('stok_gunluk')\
                .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
                .range(offset, offset + batch_size - 1)\
                .execute()

            if not result.data:
                break

            all_data.extend(result.data)

            # Progress guncelle
            progress = min(len(all_data) / expected_total, 0.99)
            progress_bar.progress(progress, text=f"Yukleniyor... {len(all_data):,} kayit")

            # Eger gelen veri batch_size'dan azsa, son sayfa demektir
            if len(result.data) < batch_size:
                break

            offset += batch_size

        progress_bar.progress(1.0, text="Tamamlandi!")
        progress_bar.empty()

        if all_data:
            df = pd.DataFrame(all_data)
            # Arama icin normalize edilmis sutunlar ekle
            df['urun_kod_upper'] = df['urun_kod'].fillna('').str.upper()
            df['urun_ad_upper'] = df['urun_ad'].fillna('').apply(turkce_upper)
            df['urun_ad_lower'] = df['urun_ad'].fillna('').apply(turkce_lower)
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Veri yukleme hatasi: {e}")
        return None


# ============================================================================
# YARDIMCI FONKSIYONLAR
# ============================================================================

def normalize_turkish(text: str) -> str:
    """Turkce karakterleri normalize et (arama icin)"""
    if not text:
        return ""
    text = str(text).lower()
    # Turkce -> ASCII mapping
    tr_map = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
    }
    for tr_char, ascii_char in tr_map.items():
        text = text.replace(tr_char, ascii_char)
    return text


def turkce_upper(text: str) -> str:
    """Turkce karakterleri dogru sekilde buyuk harfe cevir"""
    if not text:
        return ""
    text = str(text)
    # Turkce ozel buyuk harf donusumu
    tr_upper_map = {
        'ı': 'I', 'i': 'İ',
        'ğ': 'Ğ', 'ü': 'Ü', 'ş': 'Ş', 'ö': 'Ö', 'ç': 'Ç'
    }
    result = ""
    for char in text:
        if char in tr_upper_map:
            result += tr_upper_map[char]
        else:
            result += char.upper()
    return result


def turkce_lower(text: str) -> str:
    """Turkce karakterleri dogru sekilde kucuk harfe cevir"""
    if not text:
        return ""
    text = str(text)
    # Turkce ozel kucuk harf donusumu
    tr_lower_map = {
        'I': 'ı', 'İ': 'i',
        'Ğ': 'ğ', 'Ü': 'ü', 'Ş': 'ş', 'Ö': 'ö', 'Ç': 'ç'
    }
    result = ""
    for char in text:
        if char in tr_lower_map:
            result += tr_lower_map[char]
        else:
            result += char.lower()
    return result


def get_stok_seviye(adet: int) -> tuple:
    """Stok seviyesi ve renk sinifi dondur"""
    if adet is None or adet <= 0:
        return "Yok", "stok-yok"
    elif adet == 1:
        return "Kritik", "stok-kritik"
    elif adet <= 5:
        return "Dusuk", "stok-dusuk"
    elif adet <= 10:
        return "Normal", "stok-normal"
    else:
        return "Yuksek", "stok-yuksek"


def format_stok_badge(adet: int) -> str:
    """Stok seviyesini HTML badge olarak formatla"""
    seviye, css_class = get_stok_seviye(adet)
    adet_str = int(adet) if adet and adet > 0 else 0
    return f'<span class="{css_class}">{seviye} ({adet_str})</span>'


# ============================================================================
# URUN ARAMA
# ============================================================================

def ara_urun(arama_text: str) -> Optional[pd.DataFrame]:
    """
    Cache'den urun ara (hizli arama)
    - urun_kod veya urun_ad icinde arama yapar
    - Case-insensitive ve Turkce karakter duyarsiz
    """
    if not arama_text or len(arama_text) < 2:
        return None

    # Cache'den veri al
    cache_key = get_cache_date()
    df_all = load_all_stok(cache_key)

    if df_all is None or df_all.empty:
        return None

    try:
        # Turkce buyuk/kucuk harf varyasyonlari olustur
        arama_original = arama_text.strip()
        arama_upper = turkce_upper(arama_original)
        arama_lower = turkce_lower(arama_original)

        # Cache'de arama yap (cok hizli - bellekte)
        mask_kod = df_all['urun_kod_upper'].str.contains(arama_upper, na=False, regex=False)
        mask_ad_upper = df_all['urun_ad_upper'].str.contains(arama_upper, na=False, regex=False)
        mask_ad_lower = df_all['urun_ad_lower'].str.contains(arama_lower, na=False, regex=False)

        # Tum sonuclari birlestir
        mask = mask_kod | mask_ad_upper | mask_ad_lower
        df = df_all[mask][['sm_kod', 'bs_kod', 'magaza_kod', 'magaza_ad', 'urun_kod', 'urun_ad', 'stok_adet', 'nitelik']].copy()

        # Tekrarlari kaldir
        df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])

        return df

    except Exception as e:
        st.error(f"Arama hatasi: {e}")
        return None


def goster_sonuclar(df: pd.DataFrame, arama_text: str):
    """Arama sonuclarini goster"""
    if df is None or df.empty:
        st.warning(f"'{arama_text}' icin sonuc bulunamadi.")
        return

    # Benzersiz urunleri bul ve stok bilgilerini hesapla
    urunler = df.groupby('urun_kod').agg({
        'urun_ad': 'first',
        'nitelik': 'first',
        'stok_adet': lambda x: (x > 0).sum()  # Stoklu magaza sayisi
    }).reset_index()
    urunler.columns = ['urun_kod', 'urun_ad', 'nitelik', 'stoklu_magaza']

    st.success(f"**{len(urunler)}** urun bulundu")

    # Durum renkleri
    durum_renk = {
        'Kritik': ('#ff4444', '#fff'),
        'Dusuk': ('#ff9800', '#fff'),
        'Normal': ('#4caf50', '#fff'),
        'Yuksek': ('#2196f3', '#fff')
    }

    # Her urun icin kompakt liste
    for _, urun in urunler.iterrows():
        urun_kod = urun['urun_kod']
        urun_ad = urun['urun_ad'] or urun_kod
        nitelik = urun['nitelik'] or ''
        stoklu_magaza = int(urun['stoklu_magaza'])

        # Bu urune ait magazalar
        urun_df = df[df['urun_kod'] == urun_kod].copy()
        urun_df_stoklu = urun_df[urun_df['stok_adet'] > 0].copy()

        # Expander basligi: Urun kodu | Urun adi | Magaza sayisi
        if stoklu_magaza > 0:
            baslik = f"📦 {urun_kod}  •  {urun_ad[:40]}  •  🏪 {stoklu_magaza} magaza"
        else:
            baslik = f"❌ {urun_kod}  •  {urun_ad[:40]}  •  Stok yok"

        with st.expander(baslik, expanded=False):
            if urun_df_stoklu.empty:
                st.error("Bu urun hicbir magazada stokta yok!")
            else:
                # Stok seviyesine gore sirala
                urun_df_stoklu = urun_df_stoklu.sort_values('stok_adet', ascending=False)

                # Kart seklinde goster
                for _, row in urun_df_stoklu.iterrows():
                    seviye, _ = get_stok_seviye(row['stok_adet'])
                    adet = int(row['stok_adet'])
                    magaza_ad = row.get('magaza_ad', row['magaza_kod']) or row['magaza_kod']
                    sm = row.get('sm_kod', '-') or '-'
                    bs = row.get('bs_kod', '-') or '-'
                    bg_renk, text_renk = durum_renk.get(seviye, ('#9e9e9e', '#fff'))

                    # Kart HTML
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, {bg_renk}22 0%, {bg_renk}11 100%);
                        border-left: 4px solid {bg_renk};
                        border-radius: 8px;
                        padding: 12px 16px;
                        margin-bottom: 8px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-wrap: wrap;
                        gap: 8px;
                    ">
                        <div style="flex: 1; min-width: 200px;">
                            <div style="font-weight: 600; font-size: 1rem; color: #1e3a5f;">{magaza_ad}</div>
                            <div style="font-size: 0.85rem; color: #666; margin-top: 4px;">
                                SM: {sm}  •  BS: {bs}
                            </div>
                        </div>
                        <div style="
                            background: {bg_renk};
                            color: {text_renk};
                            padding: 6px 14px;
                            border-radius: 20px;
                            font-weight: 600;
                            font-size: 0.9rem;
                            white-space: nowrap;
                        ">
                            {seviye}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)


# ============================================================================
# ANA UYGULAMA
# ============================================================================

def main():
    # Baslik
    col_title, col_refresh = st.columns([6, 1])
    with col_title:
        st.title("🔍 Urun Ara")
    with col_refresh:
        if st.button("🔄", help="Veriyi yenile"):
            load_all_stok.clear()
            st.rerun()

    st.caption("Musteriye hangi magazada urun oldugunu bulmak icin")

    # Supabase baglanti kontrolu
    client = get_supabase_client()
    if not client:
        st.error("⚠️ Veritabani baglantisi kurulamadi. Lutfen ayarlari kontrol edin.")
        st.info("SUPABASE_URL ve SUPABASE_KEY environment variable'lari veya secrets tanimli olmali.")
        return

    # Veri yukle (ilk acilista)
    cache_key = get_cache_date()
    with st.spinner("Stok verisi yukleniyor..."):
        df_all = load_all_stok(cache_key)

    if df_all is None or df_all.empty:
        st.error("⚠️ Stok verisi yuklenemedi.")
        return

    # Veri bilgisi
    st.caption(f"📊 {len(df_all):,} kayit | Son guncelleme: {cache_key}")

    # Arama kutusu
    col1, col2 = st.columns([4, 1])
    with col1:
        arama_text = st.text_input(
            "Arama",
            placeholder="Ornek: 123456 veya KOLTUK",
            label_visibility="collapsed",
            key="arama_input"
        )
    with col2:
        ara_btn = st.button("🔍 Ara", use_container_width=True, type="primary")

    # Arama yap
    if arama_text and len(arama_text) >= 2:
        with st.spinner("Araniyor..."):
            df = ara_urun(arama_text)
            goster_sonuclar(df, arama_text)
    elif arama_text and len(arama_text) < 2:
        st.info("En az 2 karakter girin.")


if __name__ == "__main__":
    main()
