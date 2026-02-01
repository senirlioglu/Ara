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
from PIL import Image

# Ikonu yukle (Favicon icin)
try:
    img_icon = Image.open("static/icon-192.png")
except:
    img_icon = "🔍"

# Sayfa ayarları
st.set_page_config(
    page_title="Ürün Ara",
    page_icon=img_icon,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# NOT: iOS ikon degisikligi Streamlit Cloud'da calismaz.
# Cozum: launcher/ klasorundeki HTML sayfasini GitHub Pages/Vercel'de host edin.
# Kullanicilar o sayfayi "Ana Ekrana Ekle" ile yüklesin.

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


@st.cache_data(ttl=14400, show_spinner=False)  # 4 saat cache (daha uzun)
def load_all_stok(cache_key: str) -> Optional[pd.DataFrame]:
    """
    Tum stok verisini yukle ve cache'le.
    cache_key her gun saat 11'de degisir, boylece veri yenilenir.
    Pagination ile tum veriyi ceker.
    """
    import time as time_module

    client = get_supabase_client()
    if not client:
        return None

    try:
        all_data = []
        batch_size = 20000  # Daha kucuk batch (daha guvenli)
        offset = 0
        expected_total = 650000
        max_retries = 3

        progress_bar = st.progress(0, text="Stok verisi yukleniyor...")

        while True:
            # Retry mekanizmasi
            for attempt in range(max_retries):
                try:
                    result = client.table('stok_gunluk')\
                        .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
                        .range(offset, offset + batch_size - 1)\
                        .execute()
                    break  # Basarili, donguden cik
                except Exception as e:
                    if attempt < max_retries - 1:
                        time_module.sleep(2)  # 2 saniye bekle ve tekrar dene
                        continue
                    else:
                        raise e  # Son deneme de basarisiz

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

            # Her batch arasinda kisa bekleme (rate limit icin)
            time_module.sleep(0.1)

        progress_bar.progress(1.0, text="Tamamlandi!")
        progress_bar.empty()

        if all_data:
            df = pd.DataFrame(all_data)

            # Sadece gerekli sutunlari isle (bellek tasarrufu)
            df['urun_kod'] = df['urun_kod'].fillna('')
            df['urun_ad'] = df['urun_ad'].fillna('')

            # Vectorized upper (daha hizli)
            df['urun_kod_upper'] = df['urun_kod'].str.upper()
            df['urun_ad_upper'] = df['urun_ad'].str.upper()

            # Turkce karakter normalizasyonu (vectorized)
            df['urun_ad_normalized'] = df['urun_ad'].str.lower()
            df['urun_kod_normalized'] = df['urun_kod'].str.lower()

            # Turkce karakterleri replace et (vectorized - cok daha hizli)
            tr_replacements = [
                ('ı', 'i'), ('ğ', 'g'), ('ü', 'u'), ('ş', 's'), ('ö', 'o'), ('ç', 'c'),
                ('İ', 'i'), ('Ğ', 'g'), ('Ü', 'u'), ('Ş', 's'), ('Ö', 'o'), ('Ç', 'c')
            ]
            for tr_char, ascii_char in tr_replacements:
                df['urun_ad_normalized'] = df['urun_ad_normalized'].str.replace(tr_char, ascii_char, regex=False)
                df['urun_kod_normalized'] = df['urun_kod_normalized'].str.replace(tr_char, ascii_char, regex=False)

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
        # Arama terimini normalize et
        arama_upper = arama_text.strip().upper()
        arama_normalized = normalize_turkish(arama_text.strip())

        # Cache'de arama yap (cok hizli - bellekte)
        mask_kod = df_all['urun_kod_upper'].str.contains(arama_upper, na=False, regex=False)
        mask_ad = df_all['urun_ad_upper'].str.contains(arama_upper, na=False, regex=False)
        # ASCII normalized arama (ü->u, ş->s ile eslesme)
        mask_kod_normalized = df_all['urun_kod_normalized'].str.contains(arama_normalized, na=False, regex=False)
        mask_ad_normalized = df_all['urun_ad_normalized'].str.contains(arama_normalized, na=False, regex=False)

        # Tum sonuclari birlestir
        mask = mask_kod | mask_ad | mask_kod_normalized | mask_ad_normalized
        df = df_all[mask][['sm_kod', 'bs_kod', 'magaza_kod', 'magaza_ad', 'urun_kod', 'urun_ad', 'stok_adet', 'nitelik']].copy()

        # Tekrarlari kaldir
        df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])

        return df

    except Exception as e:
        st.error(f"Arama hatasi: {e}")
        return None


def log_arama(arama_terimi: str, sonuc_sayisi: int):
    """Arama terimini Supabase'e logla (gunluk bazda)"""
    try:
        client = get_supabase_client()
        if client and arama_terimi:
            terim = arama_terimi.strip().lower()[:100]
            bugun = datetime.now().strftime('%Y-%m-%d')

            # Bugunku kayit var mi kontrol et
            result = client.table('arama_log')\
                .select('id, arama_sayisi')\
                .eq('tarih', bugun)\
                .eq('arama_terimi', terim)\
                .execute()

            if result.data:
                # Varsa sayiyi artir
                kayit = result.data[0]
                client.table('arama_log')\
                    .update({
                        'arama_sayisi': kayit['arama_sayisi'] + 1,
                        'sonuc_sayisi': sonuc_sayisi
                    })\
                    .eq('id', kayit['id'])\
                    .execute()
            else:
                # Yoksa yeni kayit ekle
                client.table('arama_log').insert({
                    'tarih': bugun,
                    'arama_terimi': terim,
                    'arama_sayisi': 1,
                    'sonuc_sayisi': sonuc_sayisi
                }).execute()
    except:
        pass  # Log hatasi kullaniciyi etkilemesin


def goster_sonuclar(df: pd.DataFrame, arama_text: str):
    """Arama sonuçlarını göster"""
    # Arama logla
    sonuc_sayisi = 0 if df is None or df.empty else len(df['urun_kod'].unique())
    log_arama(arama_text, sonuc_sayisi)

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
