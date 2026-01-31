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
        # Turkce buyuk/kucuk harf varyasyonlari olustur
        arama_original = arama_text.strip()
        arama_upper = turkce_upper(arama_original)
        arama_lower = turkce_lower(arama_original)

        all_results = []

        # Supabase'den son yuklemedeki verileri cek
        # Urun kodu ile ara (genellikle buyuk harf)
        result = client.table('stok_gunluk')\
            .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
            .ilike('urun_kod', f'%{arama_upper}%')\
            .execute()
        if result.data:
            all_results.extend(result.data)

        # Urun adi ile ara - BUYUK HARF
        result2 = client.table('stok_gunluk')\
            .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
            .ilike('urun_ad', f'%{arama_upper}%')\
            .execute()
        if result2.data:
            all_results.extend(result2.data)

        # Urun adi ile ara - kucuk harf (farkli sonuc varsa)
        if arama_lower != arama_upper:
            result3 = client.table('stok_gunluk')\
                .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
                .ilike('urun_ad', f'%{arama_lower}%')\
                .execute()
            if result3.data:
                all_results.extend(result3.data)

        # Sonuclari birlestir ve tekrarlari kaldir
        if all_results:
            df = pd.DataFrame(all_results)
            # magaza_kod ve urun_kod kombinasyonuna gore tekrarlari kaldir
            df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])
            return df
        else:
            return pd.DataFrame()

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
