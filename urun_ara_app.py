"""
ÜRÜN ARAMA UYGULAMASI
=====================
Müşteriye hangi mağazada ürün olduğunu göstermek için arama uygulaması.
"""

import streamlit as st
import pandas as pd
import os
import re
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
    """Supabase client olustur - UI yok, sadece client dondur"""
    try:
        from supabase import create_client

        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')

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
    except:
        return None  # UI yok, sadece None don


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


@st.cache_data(ttl=14400, max_entries=2, show_spinner=False)
def load_all_stok(cache_key: str) -> Optional[pd.DataFrame]:
    """
    Tum stok verisini yukle ve cache'le.
    UI yok - sadece veri dondur. Progress/error main()'de gosterilir.
    max_entries=2: sadece 2 gunluk veri tutar, RAM sismasini onler.
    """
    import time as time_module

    client = get_supabase_client()
    if not client:
        raise Exception("Veritabani baglantisi kurulamadi")

    all_data = []
    batch_size = 20000
    offset = 0
    max_retries = 3

    while True:
        for attempt in range(max_retries):
            try:
                result = client.table('stok_gunluk')\
                    .select('sm_kod, bs_kod, magaza_kod, magaza_ad, urun_kod, urun_ad, stok_adet, nitelik')\
                    .range(offset, offset + batch_size - 1)\
                    .execute()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    time_module.sleep(2)
                    continue
                else:
                    raise e

        if not result.data:
            break

        all_data.extend(result.data)

        if len(result.data) < batch_size:
            break

        offset += batch_size
        time_module.sleep(0.1)

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)

    # Veri isleme
    df['urun_kod'] = df['urun_kod'].fillna('')
    df['urun_ad'] = df['urun_ad'].fillna('')

    # Turkce buyuk harf donusumu - VEKTORIZE (hizli)
    # Once Turkce karakterleri degistir, sonra upper()
    df['urun_kod_upper'] = df['urun_kod']
    df['urun_ad_upper'] = df['urun_ad']

    for old, new in [('i', 'İ'), ('ı', 'I'), ('ğ', 'Ğ'), ('ü', 'Ü'), ('ş', 'Ş'), ('ö', 'Ö'), ('ç', 'Ç')]:
        df['urun_kod_upper'] = df['urun_kod_upper'].str.replace(old, new, regex=False)
        df['urun_ad_upper'] = df['urun_ad_upper'].str.replace(old, new, regex=False)

    df['urun_kod_upper'] = df['urun_kod_upper'].str.upper()
    df['urun_ad_upper'] = df['urun_ad_upper'].str.upper()

    # Normalize: ONCE Turkce karakterleri degistir, SONRA lower - VEKTORIZE
    tr_replacements = [
        ('İ', 'i'), ('I', 'i'), ('ı', 'i'),
        ('Ğ', 'g'), ('ğ', 'g'),
        ('Ü', 'u'), ('ü', 'u'),
        ('Ş', 's'), ('ş', 's'),
        ('Ö', 'o'), ('ö', 'o'),
        ('Ç', 'c'), ('ç', 'c'),
    ]

    df['urun_ad_normalized'] = df['urun_ad']
    df['urun_kod_normalized'] = df['urun_kod']

    for tr_char, ascii_char in tr_replacements:
        df['urun_ad_normalized'] = df['urun_ad_normalized'].str.replace(tr_char, ascii_char, regex=False)
        df['urun_kod_normalized'] = df['urun_kod_normalized'].str.replace(tr_char, ascii_char, regex=False)

    df['urun_ad_normalized'] = df['urun_ad_normalized'].str.lower()
    df['urun_kod_normalized'] = df['urun_kod_normalized'].str.lower()

    return df


# ============================================================================
# YARDIMCI FONKSIYONLAR
# ============================================================================

def normalize_turkish(text: str) -> str:
    """Turkce karakterleri normalize et (arama icin)"""
    if not text:
        return ""
    text = str(text)
    # ONCE Turkce karakterleri degistir, SONRA lower() yap
    # Cunku Python'un lower() fonksiyonu İ -> i donusumunu dogru yapmiyor
    tr_map = {
        'İ': 'i', 'I': 'i',  # Her iki buyuk I da kucuk i olsun
        'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c',
        'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'ı': 'i',  # noktasiz i de i olsun
    }
    for tr_char, ascii_char in tr_map.items():
        text = text.replace(tr_char, ascii_char)
    return text.lower()


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

def temizle_turkce_ek(kelime: str) -> list:
    """Turkce ekleri temizleyip kokleri dondur (mamasi -> mama, tavuklu -> tavuk)"""
    kelime = kelime.strip().lower()
    kokler = [kelime]  # Orijinali de dahil et

    # Turkce yaygın ekler (uzundan kısaya sıralı)
    ekler = [
        'ları', 'leri', 'ler', 'lar',
        'lık', 'lik', 'luk', 'lük',
        'sı', 'si', 'su', 'sü',
        'lu', 'lü', 'lı', 'li',
        'cı', 'ci', 'cu', 'cü',
        'ca', 'ce',
        'ın', 'in', 'un', 'ün',
        'nı', 'ni', 'nu', 'nü',
        'da', 'de', 'ta', 'te',
        'dan', 'den', 'tan', 'ten',
        'yla', 'yle',
    ]

    for ek in ekler:
        if kelime.endswith(ek) and len(kelime) > len(ek) + 2:
            kok = kelime[:-len(ek)]
            if kok not in kokler:
                kokler.append(kok)

    return kokler


def get_es_anlamlilar(kelime: str) -> list:
    """Kelimenin eş anlamlılarını getir"""
    try:
        client = get_supabase_client()
        if client:
            result = client.table('es_anlamlilar')\
                .select('es_anlam')\
                .eq('kelime', kelime.lower().strip())\
                .execute()
            if result.data:
                return [r['es_anlam'] for r in result.data]
    except:
        pass
    return []


def fuzzy_ara(arama_text: str) -> Optional[pd.DataFrame]:
    """
    Fuzzy search - benzer yazımları bulur (yazım hatası toleransı)
    Supabase'deki fuzzy_urun_ara fonksiyonunu kullanır
    """
    try:
        client = get_supabase_client()
        if not client:
            return None

        result = client.rpc('fuzzy_urun_ara', {'arama_text': arama_text.strip()}).execute()

        if result.data:
            df = pd.DataFrame(result.data)
            return df
    except:
        pass
    return None


def ara_urun(arama_text: str, fuzzy_fallback: bool = True) -> tuple[Optional[pd.DataFrame], bool]:
    """
    Cache'den urun ara (hizli arama)
    - Arama terimini kelimelere boler, HER kelime eslesme(olmali (AND mantigi)
    - Case-insensitive ve Turkce karakter duyarsiz
    - Kısa terimler için kelime sınırı kontrolü yapar
    - Sonuç bulunamazsa fuzzy search dener
    Returns: (DataFrame, is_fuzzy) tuple
    """
    if not arama_text or len(arama_text) < 2:
        return None, False

    try:
        # Cache'den veri al
        cache_key = get_cache_date()
        df_all = load_all_stok(cache_key)

        if df_all is None or df_all.empty:
            return None, False

        # Arama terimini kelimelere bol
        kelimeler = arama_text.strip().split()

        # Her kelime icin es anlamlilar ve kok formlarini ekle
        tum_kelime_gruplari = []
        for kelime in kelimeler:
            # Kok formlarini bul (mamasi -> mama, tavuklu -> tavuk)
            kokler = temizle_turkce_ek(kelime)
            # Es anlamlilar
            es_anlamlar = get_es_anlamlilar(kelime)
            # Hepsini birlestir
            tum_formlar = list(set(kokler + es_anlamlar + [kelime]))
            tum_kelime_gruplari.append(tum_formlar)

        # Her kelime grubu icin mask olustur (AND mantigi)
        final_mask = pd.Series([True] * len(df_all))

        for kelime_grubu in tum_kelime_gruplari:
            # Bu kelime grubu icindeki herhangi biri eslesmeli (OR)
            grup_mask = pd.Series([False] * len(df_all))

            for terim in kelime_grubu:
                terim_upper = turkce_upper(terim)
                terim_normalized = normalize_turkish(terim)

                # Kısa terimler için (2-3 karakter) kelime sınırı kullan
                if len(terim.strip()) <= 3:
                    pattern_upper = r'(^|[\s])' + re.escape(terim_upper) + r'($|[\s\d])'
                    pattern_norm = r'(^|[\s])' + re.escape(terim_normalized) + r'($|[\s\d])'

                    mask_kod = df_all['urun_kod_upper'].str.contains(pattern_upper, na=False, regex=True)
                    mask_ad = df_all['urun_ad_upper'].str.contains(pattern_upper, na=False, regex=True)
                    mask_kod_norm = df_all['urun_kod_normalized'].str.contains(pattern_norm, na=False, regex=True)
                    mask_ad_norm = df_all['urun_ad_normalized'].str.contains(pattern_norm, na=False, regex=True)
                else:
                    # Uzun terimler icin normal contains
                    mask_kod = df_all['urun_kod_upper'].str.contains(terim_upper, na=False, regex=False)
                    mask_ad = df_all['urun_ad_upper'].str.contains(terim_upper, na=False, regex=False)
                    mask_kod_norm = df_all['urun_kod_normalized'].str.contains(terim_normalized, na=False, regex=False)
                    mask_ad_norm = df_all['urun_ad_normalized'].str.contains(terim_normalized, na=False, regex=False)

                grup_mask = grup_mask | mask_kod | mask_ad | mask_kod_norm | mask_ad_norm

            # Her kelime grubu eslesme(olmali (AND)
            final_mask = final_mask & grup_mask

        df = df_all[final_mask][['sm_kod', 'bs_kod', 'magaza_kod', 'magaza_ad', 'urun_kod', 'urun_ad', 'stok_adet', 'nitelik']].copy()

        # Tekrarlari kaldir
        df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])

        # Sonuç varsa döndür
        if not df.empty:
            return df, False

        # Sonuç yoksa ve fuzzy aktifse, fuzzy dene
        if fuzzy_fallback and len(arama_text.strip()) >= 3:
            df_fuzzy = fuzzy_ara(arama_text)
            if df_fuzzy is not None and not df_fuzzy.empty:
                return df_fuzzy, True

        return df, False

    except Exception as e:
        st.error(f"Arama hatasi: {e}")
        return None, False


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


def goster_sonuclar(df: pd.DataFrame, arama_text: str, is_fuzzy: bool = False):
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

    if is_fuzzy:
        st.info(f"🔮 Benzer sonuçlar gösteriliyor ('{arama_text}' için tam eşleşme bulunamadı)")

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
    try:
        with st.spinner("Stok verisi yükleniyor..."):
            df_all = load_all_stok(cache_key)
    except Exception as e:
        st.error(f"⚠️ Veri yüklenirken hata: {e}")
        st.info("Lütfen sayfayı yenileyin veya daha sonra tekrar deneyin.")
        return

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
        with st.spinner("Aranıyor..."):
            df, is_fuzzy = ara_urun(arama_text)
            goster_sonuclar(df, arama_text, is_fuzzy)
    elif arama_text and len(arama_text) < 2:
        st.info("En az 2 karakter girin.")


def admin_panel():
    """Admin paneli - arama analitikleri"""
    from datetime import timedelta
    import hashlib

    # Basit token oluştur (şifre + tarih)
    admin_pass = os.environ.get('ADMIN_PASSWORD') or st.secrets.get('ADMIN_PASSWORD', 'admin123')
    today = datetime.now().strftime('%Y-%m-%d')
    valid_token = hashlib.md5(f"{admin_pass}{today}".encode()).hexdigest()[:16]

    params = st.query_params
    url_token = params.get("token", "")

    # Token varsa ve geçerliyse direkt giriş
    if url_token == valid_token:
        st.session_state.admin_auth = True

    # Şifre kontrolü
    if not st.session_state.get('admin_auth', False):
        st.title("🔐 Admin Girişi")
        password = st.text_input("Şifre:", type="password")
        if st.button("Giriş"):
            if password == admin_pass:
                st.session_state.admin_auth = True
                # Token'ı URL'e ekle (yenileme için)
                st.query_params["admin"] = "true"
                st.query_params["token"] = valid_token
                st.rerun()
            else:
                st.error("Yanlış şifre!")
        return

    st.title("📊 Arama Analitikleri")

    # Veri yükle
    client = get_supabase_client()
    if not client:
        st.error("Veritabanı bağlantısı yok")
        return

    gun_sayisi = st.selectbox("Dönem:", [7, 14, 30], format_func=lambda x: f"Son {x} gün")

    try:
        baslangic = (datetime.now() - timedelta(days=gun_sayisi)).strftime('%Y-%m-%d')
        result = client.table('arama_log')\
            .select('*')\
            .gte('tarih', baslangic)\
            .order('tarih', desc=True)\
            .order('arama_sayisi', desc=True)\
            .execute()

        if not result.data:
            st.warning("Henüz veri yok")
            return

        df = pd.DataFrame(result.data)

        # Metrikler
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Toplam Arama", f"{df['arama_sayisi'].sum():,}")
        with col2:
            st.metric("Benzersiz Terim", f"{len(df['arama_terimi'].unique()):,}")
        with col3:
            sonucsuz = df[df['sonuc_sayisi'] == 0]['arama_sayisi'].sum()
            st.metric("Sonuçsuz", f"{sonucsuz:,}")

        st.markdown("---")

        # En çok arananlar
        st.subheader("🔥 En Çok Arananlar")
        top_df = df.groupby('arama_terimi').agg({'arama_sayisi': 'sum', 'sonuc_sayisi': 'last'}).reset_index()
        top_df = top_df.sort_values('arama_sayisi', ascending=False).head(20)
        top_df.columns = ['Terim', 'Arama', 'Sonuç']
        st.dataframe(top_df, use_container_width=True, hide_index=True)

        # Sonuçsuzlar
        st.subheader("❌ Sonuç Bulunamayanlar")
        sonucsuz_df = df[df['sonuc_sayisi'] == 0].groupby('arama_terimi')['arama_sayisi'].sum().reset_index()
        sonucsuz_df = sonucsuz_df.sort_values('arama_sayisi', ascending=False).head(20)
        sonucsuz_df.columns = ['Terim', 'Arama']
        if sonucsuz_df.empty:
            st.success("Tüm aramalarda sonuç bulunmuş!")
        else:
            st.dataframe(sonucsuz_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Hata: {e}")

    if st.button("🚪 Çıkış"):
        st.session_state.admin_auth = False
        st.rerun()


if __name__ == "__main__":
    # URL parametresi kontrolü
    params = st.query_params
    if params.get("admin") == "true":
        admin_panel()
    else:
        main()
