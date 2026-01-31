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
<link rel="icon" type="image/png" href="/app/static/icon-192.png">
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

@st.cache_data(ttl=300, show_spinner=False)
def ara_urun(arama_text: str) -> Optional[pd.DataFrame]:
    """
    Supabase'den urun ara
    - urun_kod veya urun_ad icinde arama yapar
    - Case-insensitive ve Turkce karakter duyarsiz
    """
    client = get_supabase_client()
    if not client:
        return None

    if not arama_text or len(arama_text) < 2:
        return None

    try:
        # Normalize arama metni
        arama_normalized = normalize_turkish(arama_text.strip())
        arama_upper = arama_text.strip().upper()

        # Supabase'den son yuklemedeki verileri cek
        # Oncelikle urun_kod ile tam eslesme dene
        result = client.table('stok_gunluk')\
            .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
            .ilike('urun_kod', f'%{arama_upper}%')\
            .execute()

        df_kod = pd.DataFrame(result.data) if result.data else pd.DataFrame()

        # Urun adi ile de ara
        result2 = client.table('stok_gunluk')\
            .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
            .ilike('urun_ad', f'%{arama_text}%')\
            .execute()

        df_ad = pd.DataFrame(result2.data) if result2.data else pd.DataFrame()

        # Birles ve tekrarlari kaldir
        if not df_kod.empty and not df_ad.empty:
            df = pd.concat([df_kod, df_ad]).drop_duplicates(subset=['magaza_kod', 'urun_kod'])
        elif not df_kod.empty:
            df = df_kod
        elif not df_ad.empty:
            df = df_ad
        else:
            return pd.DataFrame()

        return df

    except Exception as e:
        st.error(f"Arama hatasi: {e}")
        return None


def goster_sonuclar(df: pd.DataFrame, arama_text: str):
    """Arama sonuclarini goster"""
    if df is None or df.empty:
        st.warning(f"'{arama_text}' icin sonuc bulunamadi.")
        return

    # Benzersiz urunleri bul
    urunler = df.groupby('urun_kod').agg({
        'urun_ad': 'first',
        'nitelik': 'first'
    }).reset_index()

    st.success(f"**{len(urunler)}** urun bulundu")

    # Her urun icin
    for _, urun in urunler.iterrows():
        urun_kod = urun['urun_kod']
        urun_ad = urun['urun_ad'] or urun_kod
        nitelik = urun['nitelik'] or ''

        # Bu urune ait magazalar
        urun_df = df[df['urun_kod'] == urun_kod].copy()

        # Stok > 0 olanlari filtrele
        urun_df_stoklu = urun_df[urun_df['stok_adet'] > 0].copy()

        with st.expander(f"📦 **{urun_kod}** - {urun_ad[:50]} ({nitelik})", expanded=True):

            if urun_df_stoklu.empty:
                st.error("❌ Bu urun hicbir magazada stokta yok!")
            else:
                # Stok seviyesine gore sirala (yuksekten dusuge)
                urun_df_stoklu = urun_df_stoklu.sort_values('stok_adet', ascending=False)

                # Tablo olustur
                tablo_data = []
                for _, row in urun_df_stoklu.iterrows():
                    seviye, _ = get_stok_seviye(row['stok_adet'])
                    tablo_data.append({
                        'SM': row.get('sm_kod', '-') or '-',
                        'BS': row.get('bs_kod', '-') or '-',
                        'Magaza': row.get('magaza_ad', row['magaza_kod']) or row['magaza_kod'],
                        'Kod': row['magaza_kod'],
                        'Seviye': seviye
                    })

                tablo_df = pd.DataFrame(tablo_data)

                # Renklendirme fonksiyonu
                def renklendir(row):
                    seviye = row['Seviye']
                    if seviye == 'Kritik':
                        return ['background-color: #ffcdd2'] * len(row)
                    elif seviye == 'Dusuk':
                        return ['background-color: #ffe0b2'] * len(row)
                    elif seviye == 'Normal':
                        return ['background-color: #c8e6c9'] * len(row)
                    elif seviye == 'Yuksek':
                        return ['background-color: #bbdefb'] * len(row)
                    else:
                        return [''] * len(row)

                # Tabloyu goster
                st.dataframe(
                    tablo_df.style.apply(renklendir, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'SM': st.column_config.TextColumn('SM', width='small'),
                        'BS': st.column_config.TextColumn('BS', width='small'),
                        'Magaza': st.column_config.TextColumn('Magaza', width='medium'),
                        'Kod': st.column_config.TextColumn('Kod', width='small'),
                        'Seviye': st.column_config.TextColumn('Seviye', width='small')
                    }
                )

                # Ozet
                magaza_sayisi = len(urun_df_stoklu)
                st.caption(f"📊 {magaza_sayisi} magazada mevcut")


# ============================================================================
# ANA UYGULAMA
# ============================================================================

def main():
    # Baslik
    st.title("🔍 Urun Ara")
    st.caption("Musteriye hangi magazada urun oldugunu bulmak icin")

    # Supabase baglanti kontrolu
    client = get_supabase_client()
    if not client:
        st.error("⚠️ Veritabani baglantisi kurulamadi. Lutfen ayarlari kontrol edin.")
        st.info("SUPABASE_URL ve SUPABASE_KEY environment variable'lari veya secrets tanimli olmali.")
        return

    # Arama kutusu
    st.markdown("### Urun Kodu veya Adi")

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

    # Bilgilendirme
    with st.expander("ℹ️ Stok Seviyeleri", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown('<span class="stok-kritik">Kritik (1)</span>', unsafe_allow_html=True)
        with col2:
            st.markdown('<span class="stok-dusuk">Dusuk (2-5)</span>', unsafe_allow_html=True)
        with col3:
            st.markdown('<span class="stok-normal">Normal (6-10)</span>', unsafe_allow_html=True)
        with col4:
            st.markdown('<span class="stok-yuksek">Yuksek (11+)</span>', unsafe_allow_html=True)

    st.divider()

    # Arama yap
    if arama_text and len(arama_text) >= 2:
        with st.spinner("Araniyor..."):
            df = ara_urun(arama_text)
            goster_sonuclar(df, arama_text)
    elif arama_text and len(arama_text) < 2:
        st.info("En az 2 karakter girin.")


if __name__ == "__main__":
    main()
