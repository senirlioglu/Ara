"""
ÜRÜN ARAMA UYGULAMASI
=====================
Müşteriye hangi mağazada ürün olduğunu göstermek için arama uygulaması.
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime, time
from typing import Optional

# Sayfa ayarları
st.set_page_config(
    page_title="Ürün Ara",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# PWA Meta Tag'leri - Ana ekran ikonu icin base64 encoded
ICON_BASE64 = "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"

st.markdown(f"""
<meta name="theme-color" content="#667eea">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Ürün Ara">
<link rel="apple-touch-icon" href="data:image/png;base64,{ICON_BASE64}">
<link rel="icon" type="image/png" href="data:image/png;base64,{ICON_BASE64}">
""", unsafe_allow_html=True)

# Modern CSS Tasarımı
st.markdown("""
<style>
    /* Genel stil */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
    }

    /* Header gizle */
    header[data-testid="stHeader"] {
        background: transparent;
    }

    /* Ana başlık */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 1rem;
        border-radius: 0 0 20px 20px;
        margin: -1rem -1rem 1.5rem -1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }

    .main-header h1 {
        color: white !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    .main-header p {
        color: rgba(255,255,255,0.85);
        font-size: 0.9rem;
        margin: 0.5rem 0 0 0;
    }

    /* Arama kutusu container */
    .search-container {
        background: white;
        padding: 1rem;
        border-radius: 16px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
    }

    /* Input stili */
    .stTextInput > div > div > input {
        border-radius: 12px !important;
        border: 2px solid #e0e0e0 !important;
        padding: 0.75rem 1rem !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important;
    }

    /* Buton stili */
    .stButton > button {
        border-radius: 12px !important;
        padding: 0.75rem 1.5rem !important;
        font-weight: 600 !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
        transition: all 0.3s ease !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }

    /* Bilgi kartı */
    .info-card {
        background: white;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        font-size: 0.85rem;
        color: #666;
        text-align: center;
        margin-bottom: 1rem;
    }

    /* Expander stili */
    .streamlit-expanderHeader {
        background: white !important;
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
        padding: 0.75rem 1rem !important;
        font-weight: 500 !important;
    }

    .streamlit-expanderContent {
        background: white !important;
        border-radius: 0 0 12px 12px !important;
        border: none !important;
        padding: 0.5rem !important;
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
            # ASCII normalized (ü->u, ş->s, vs.) - Turkce karaktersiz arama icin
            df['urun_ad_normalized'] = df['urun_ad'].fillna('').apply(normalize_turkish)
            df['urun_kod_normalized'] = df['urun_kod'].fillna('').apply(normalize_turkish)
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
    """Stok seviyesi ve renk sınıfı döndür"""
    if adet is None or adet <= 0:
        return "Yok", "stok-yok"
    elif adet == 1:
        return "Kritik", "stok-kritik"
    elif adet <= 5:
        return "Düşük", "stok-dusuk"
    elif adet <= 10:
        return "Normal", "stok-normal"
    else:
        return "Yüksek", "stok-yuksek"


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
        arama_normalized = normalize_turkish(arama_original)  # ASCII normalized (zuber, biçak -> bicak)

        # Cache'de arama yap (cok hizli - bellekte)
        mask_kod = df_all['urun_kod_upper'].str.contains(arama_upper, na=False, regex=False)
        mask_ad_upper = df_all['urun_ad_upper'].str.contains(arama_upper, na=False, regex=False)
        mask_ad_lower = df_all['urun_ad_lower'].str.contains(arama_lower, na=False, regex=False)
        # ASCII normalized arama (ü->u, ş->s ile eslesme)
        mask_kod_normalized = df_all['urun_kod_normalized'].str.contains(arama_normalized, na=False, regex=False)
        mask_ad_normalized = df_all['urun_ad_normalized'].str.contains(arama_normalized, na=False, regex=False)

        # Tum sonuclari birlestir
        mask = mask_kod | mask_ad_upper | mask_ad_lower | mask_kod_normalized | mask_ad_normalized
        df = df_all[mask][['sm_kod', 'bs_kod', 'magaza_kod', 'magaza_ad', 'urun_kod', 'urun_ad', 'stok_adet', 'nitelik']].copy()

        # Tekrarlari kaldir
        df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])

        return df

    except Exception as e:
        st.error(f"Arama hatasi: {e}")
        return None


def goster_sonuclar(df: pd.DataFrame, arama_text: str):
    """Arama sonuçlarını göster"""
    if df is None or df.empty:
        st.warning(f"'{arama_text}' için sonuç bulunamadı.")
        return

    # Benzersiz ürünleri bul ve stok bilgilerini hesapla
    urunler = df.groupby('urun_kod').agg({
        'urun_ad': 'first',
        'nitelik': 'first',
        'stok_adet': lambda x: (x > 0).sum()
    }).reset_index()
    urunler.columns = ['urun_kod', 'urun_ad', 'nitelik', 'stoklu_magaza']

    st.success(f"**{len(urunler)}** ürün bulundu")

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

        # Expander başlığı: Ürün kodu | Ürün adı | Mağaza sayısı
        if stoklu_magaza > 0:
            baslik = f"📦 {urun_kod}  •  {urun_ad[:40]}  •  🏪 {stoklu_magaza} mağaza"
        else:
            baslik = f"❌ {urun_kod}  •  {urun_ad[:40]}  •  Stok yok"

        with st.expander(baslik, expanded=False):
            if urun_df_stoklu.empty:
                st.error("Bu ürün hiçbir mağazada stokta yok!")
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
    # Modern Header
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Ürün Ara</h1>
        <p>Hangi mağazada ürün var? Hızlıca öğren!</p>
    </div>
    """, unsafe_allow_html=True)

    # Supabase bağlantı kontrolü
    client = get_supabase_client()
    if not client:
        st.error("⚠️ Veritabanı bağlantısı kurulamadı.")
        st.info("Lütfen ayarları kontrol edin.")
        return

    # Veri yükle (ilk açılışta)
    cache_key = get_cache_date()
    with st.spinner("Stok verisi yükleniyor..."):
        df_all = load_all_stok(cache_key)

    if df_all is None or df_all.empty:
        st.error("⚠️ Stok verisi yüklenemedi.")
        return

    # Bilgi kartı
    st.markdown(f"""
    <div class="info-card">
        📊 <strong>{len(df_all):,}</strong> kayıt &nbsp;|&nbsp; 🕐 Güncelleme: {cache_key} 11:00
    </div>
    """, unsafe_allow_html=True)

    # Arama kutusu
    col1, col2 = st.columns([5, 1])
    with col1:
        arama_text = st.text_input(
            "Arama",
            placeholder="Ürün kodu veya adı yazın...",
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
