"""
ÜRÜN ARAMA UYGULAMASI v5 (Server-Side Search)
==============================================
Tüm arama işlemleri PostgreSQL'de yapılır. RAM kullanımı minimal.

DEĞİŞİKLİKLER (v4 → v5):
  - temizle_ve_kok_bul: Kök bulma KALDIRILDI (terlik→ter sorunu)
  - SQL normalize_tr_search ile birebir uyumlu:
      translate → unaccent → lower → makinasi/makinesi/makina→makine
  - Smart quote temizliği eklendi (" " ' nbsp)
  - Bitişik tv+sayı ayırma: tv65 → tv 65
"""

import streamlit as st
import pandas as pd
import os
import re
import json
import unicodedata
import html
import hmac
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from PIL import Image
import threading
import subprocess
from pathlib import Path

# Kontrol karakterlerini temizle (null byte, vb. — Streamlit InvalidCharacterError'ı önler)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
def _safe_str(val) -> str:
    """Convert value to string and strip control characters that break Streamlit HTML rendering."""
    s = str(val) if val is not None else ""
    return _CTRL_RE.sub('', s)

def _safe_html(val) -> str:
    """HTML-escape AND encode non-Latin1 chars as numeric entities.

    Streamlit's st.markdown(unsafe_allow_html=True) uses btoa() internally
    which only supports Latin1 (U+0000-U+00FF). Turkish İ/ı/Ğ/ğ/Ş/ş are
    outside this range and cause InvalidCharacterError.
    """
    s = html.escape(_safe_str(val))
    # Encode any character outside Latin1 as HTML numeric entity
    return s.encode('ascii', 'xmlcharrefreplace').decode('ascii')

def _latin1_safe(html_str: str) -> str:
    """Encode non-Latin1 characters in an HTML string as numeric entities.

    Unlike _safe_html, this does NOT html-escape — use for strings that
    already contain valid HTML markup (tags, styles, etc.)."""
    out = []
    for ch in html_str:
        if ord(ch) > 255:
            out.append(f'&#{ord(ch)};')
        else:
            out.append(ch)
    return ''.join(out)

# --- Günlük Pipeline (günde 1 kez, lazy tetikleme) ---
def _pipeline_gunluk_guncelle():
    """oneri_listesi.json bugün güncellenmemişse pipeline'ı arka planda çalıştırır."""
    from datetime import date
    json_path = Path("data/oneri_listesi.json")
    if json_path.exists():
        son_degisim = datetime.fromtimestamp(json_path.stat().st_mtime).date()
        if son_degisim >= date.today():
            return  # Bugün zaten güncellendi
    try:
        subprocess.run(
            ["python", "urun_master_pipeline.py"],
            timeout=600,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logging.warning("urun_master_pipeline timeout (600s)")
    except Exception as e:
        logging.warning("urun_master_pipeline failed: %s", e)

def _pipeline_kontrol():
    from datetime import date
    now = datetime.now()
    # Stok sabah 09:00'da yükleniyor, pipeline 10:30'dan sonra çalışsın
    if now.hour < 10 or (now.hour == 10 and now.minute < 30):
        return
    bugun = str(date.today())
    if getattr(st, '_pipeline_last_check', None) != bugun:
        st._pipeline_last_check = bugun
        threading.Thread(target=_pipeline_gunluk_guncelle, daemon=True).start()

_pipeline_kontrol()


# --- Performans için Önceden Derlenmiş Regexler ---
RE_TV_NEGATIF = re.compile(
    r'battaniye|battanıye|ünite|unite|sehpa|koltuk|kılıf|kumanda|askı|aparat|kablo|atv|oyuncak|lisanslı|tvk',
    re.IGNORECASE
)

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

# Modern CSS Tasarımı
st.markdown("""
<style>
    .stApp { background: #f5f7fa; }
    header[data-testid="stHeader"] { background: transparent; }

    /* Prevent any horizontal scroll from overflowing elements */
    .stMainBlockContainer, [data-testid="stAppViewBlockContainer"],
    .block-container, [data-testid="stMain"] {
        overflow-x: clip !important;
    }

    /* Block spacing */
    .block-container { padding-top: 0 !important; }
    [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
    hr { margin: 0.4rem 0 !important; }

    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem 0.75rem 0.8rem;
        border-radius: 0 0 16px 16px;
        margin: -1rem -1rem 0.5rem -1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 { color: white !important; font-size: 1.5rem !important; font-weight: 700 !important; margin: 0 !important; }
    .main-header p { color: rgba(255,255,255,0.85); font-size: 0.82rem; margin: 0.3rem 0 0 0; }

    .stTextInput > div > div > input { border-radius: 12px !important; border: 2px solid #e0e0e0 !important; padding: 0.6rem 0.8rem !important; font-size: 0.95rem !important; }
    .stTextInput > div > div > input:focus { border-color: #667eea !important; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important; }

    /* Ara butonu (hem normal button hem form submit button) */
    .stButton > button,
    .stFormSubmitButton > button,
    [data-testid="stFormSubmitButton"] > button {
        border-radius: 12px !important; padding: 0.6rem 1rem !important; font-weight: 600 !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; border: none !important;
        color: white !important;
    }
    .stButton > button:hover,
    .stFormSubmitButton > button:hover,
    [data-testid="stFormSubmitButton"] > button:hover {
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }

    /* Popüler arama pill rows */
    [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) [data-testid="stHorizontalBlock"] {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
        -ms-overflow-style: none;
        gap: 4px !important;
        padding-bottom: 2px;
    }
    [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) [data-testid="stHorizontalBlock"]::-webkit-scrollbar { display: none; }
    [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: fit-content !important;
    }
    [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) .stButton > button {
        background: #f0f1f6 !important;
        color: #555 !important;
        border: 1px solid #e0e2ea !important;
        border-radius: 20px !important;
        padding: 0.35rem 0.85rem !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        white-space: nowrap !important;
        min-height: unset !important;
        line-height: 1.3 !important;
    }
    [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) .stButton > button:hover {
        background: #e4e5f0 !important;
        border-color: #667eea !important;
        color: #667eea !important;
        transform: none !important;
        box-shadow: none !important;
    }

    .popular-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #555;
        margin: 0.2rem 0 0.1rem 0.2rem;
    }

    /* Poster badge */
    .poster-badge {
        display: inline-block;
        background: linear-gradient(135deg, #FFD600 0%, #FFC107 100%);
        color: #333;
        font-weight: 700;
        font-size: 1rem;
        padding: 0.4rem 1.2rem;
        border-radius: 8px;
        margin: 0.3rem 0 0.6rem 0;
        box-shadow: 0 2px 8px rgba(255, 193, 7, 0.35);
        letter-spacing: 0.3px;
    }

    /* Week pills — active pill gold badge */
    [data-testid="stPills"] button[aria-pressed="true"],
    [data-testid="stPills"] button[aria-checked="true"] {
        background: linear-gradient(135deg, #FFD600 0%, #FFC107 100%) !important;
        color: #333 !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 8px rgba(255, 193, 7, 0.35) !important;
        border: none !important;
    }
    [data-testid="stPills"] button {
        font-weight: 600 !important;
        border-radius: 8px !important;
    }

    .info-card { background: white; padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.85rem; color: #666; text-align: center; margin-bottom: 0.5rem; }
    .streamlit-expanderHeader { background: white !important; border-radius: 12px !important; border: none !important; box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important; padding: 0.6rem 0.8rem !important; font-weight: 500 !important; }
    .streamlit-expanderContent { background: white !important; border-radius: 0 0 12px 12px !important; border: none !important; padding: 0.5rem !important; }

    @media (max-width: 768px) {
        .block-container { padding: 0.3rem !important; }
        .main-header { padding: 0.7rem 0.5rem 0.6rem; margin-bottom: 0.3rem; }
        .main-header h1 { font-size: 1.2rem !important; }
        [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) .stButton > button {
            padding: 0.3rem 0.65rem !important;
            font-size: 0.78rem !important;
        }
        .poster-badge { font-size: 0.9rem; padding: 0.3rem 1rem; }
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
        url = os.environ.get('SUPABASE_URL') or st.secrets.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY') or st.secrets.get('SUPABASE_KEY')
        if not url or not key:
            return None
        return create_client(url, key)
    except:
        return None


# ============================================================================
# YARDIMCI FONKSIYONLAR
# ============================================================================

def get_stok_seviye(adet: int) -> tuple:
    """Stok seviyesi, css class ve renk döndür"""
    if adet is None or adet <= 0:
        return "Yok", "stok-yok", "#9e9e9e"
    elif adet <= 2:
        return "Düşük", "stok-dusuk", "#e74c3c"
    elif adet <= 5:
        return "Orta", "stok-orta", "#f39c12"
    else:
        return "Yüksek", "stok-yuksek", "#27ae60"


def temizle_ve_kok_bul(text: str) -> str:
    """
    SQL normalize_tr_search ile birebir uyumlu normalize.

    SQL fonksiyonu sırası:
      1. translate(text, 'İIıĞğÜüŞşÖöÇç', 'iiigguussoocc')
      2. unaccent(...)       → â→a gibi accent temizliği
      3. lower(...)
      4. replace('makinasi','makine')
      5. replace('makinesi','makine')
      6. replace('makina','makine')

    Örnekler:
      "terlik"           → "terlik"          (ESKİ: "ter" ❌)
      "waffle makinesi"  → "waffle makine"   ✅
      "akıllı saat"      → "akilli saat"     (ESKİ: "akil saat" ❌)
      "nescaffe gold"    → "nescafe gold"    ✅ (yazım düzeltme)
    """
    if not text:
        return ""

    # 1. Türkçe karakter dönüşümü (SQL: translate)
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

    # 2. Accent temizliği (SQL: unaccent) - â→a, é→e gibi
    result = unicodedata.normalize('NFKD', result)
    result = ''.join(c for c in result if not unicodedata.combining(c))

    # 3. Lowercase (SQL: lower)
    result = result.lower()

    # 4-6. Makine dönüşümleri (SQL: replace)
    result = result.replace('makinasi', 'makine')
    result = result.replace('makinesi', 'makine')
    result = result.replace('makina', 'makine')

    # Smart quote ve özel karakter temizliği
    for c, r in {
        '\u201c': '', '\u201d': '', '\u2019': '',
        '\u00a0': ' ', '\u0307': '',
    }.items():
        result = result.replace(c, r)

    # Bitişik tv+sayı ayır: "tv65" → "tv 65"
    result = re.sub(r'(tv|televizyon)(\d)', r'\1 \2', result)

    # Çoklu boşlukları tekle
    result = re.sub(r'\s+', ' ', result).strip()

    # 7. Yazım hatası düzeltme (kelime bazlı)
    words = result.split()
    corrected = [YAZIM_DUZELTME.get(w, w) for w in words]
    result = ' '.join(corrected)

    return result


# ============================================================================
# YAZIM HATASI SÖZLÜĞÜ
# ============================================================================
# Arama loglarından tespit edilen yaygın yazım hataları.
# Yeni hatalar tespit edildikçe buraya eklenebilir.
# Format: 'yanlis_yazim': 'dogru_yazim'
# ============================================================================

YAZIM_DUZELTME = {
    # Marka yazım hataları
    'nescaffe': 'nescafe', 'nescfe': 'nescafe', 'nesacfe': 'nescafe',
    'cold': 'gold',
    'philps': 'philips', 'phlips': 'philips', 'plips': 'philips',
    'samsun': 'samsung', 'samgung': 'samsung', 'smasung': 'samsung',
    'tosiba': 'toshiba', 'toshbia': 'toshiba', 'tosihba': 'toshiba',
    'grundik': 'grundig', 'grunding': 'grundig',
    'sinbo': 'sinbo',

    # Ürün kategorisi yazım hataları
    'tercere': 'tencere', 'tencre': 'tencere', 'tenecre': 'tencere',
    'blendir': 'blender', 'belnder': 'blender', 'blnder': 'blender',
    'wafle': 'waffle', 'vafle': 'waffle', 'wafle': 'waffle',
    'aklli': 'akilli', 'akkilli': 'akilli', 'aklili': 'akilli',
    'buzdobali': 'buzdolabi', 'buzdolbi': 'buzdolabi',
    'televizon': 'televizyon', 'televzyon': 'televizyon', 'teleivzyon': 'televizyon',
    'makarana': 'makarna', 'maknara': 'makarna',
    'bibron': 'biberon', 'bbiron': 'biberon',
    'termoss': 'termos',
    'kulaklik': 'kulaklik',
    'supurge': 'supurge', 'spurge': 'supurge', 'surpuge': 'supurge',
    'camasir': 'camasir', 'camaisr': 'camasir',
    'bulasik': 'bulasik', 'bualsik': 'bulasik',
    'mikrodlga': 'mikrodalga', 'mikrdalga': 'mikrodalga',
    'sampuan': 'sampuan', 'sampuvan': 'sampuan',
    'rejisor': 'rejisör',
}


# ============================================================================
# URUN ARAMA (SERVER-SIDE)
# ============================================================================

@st.cache_data(ttl=3600)
def _build_oneri_lookup():
    """Öneri listesinden ad→kod reverse lookup tablosu oluştur"""
    lookup = {}
    try:
        oneri_path = Path('data/oneri_listesi.json')
        if oneri_path.exists():
            with oneri_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            for entry in data:
                if isinstance(entry, str) and ' - ' in entry:
                    parts = entry.split(' - ')
                    kod = parts[0].strip()
                    ad = parts[1].strip() if len(parts) >= 2 else ''
                    if kod.isdigit() and ad:
                        lookup[ad.lower()] = kod
    except Exception:
        pass
    return lookup


def _oneri_ad_to_kod(arama_text: str) -> str:
    """Dropdown'dan gelen ürün adını koda çevir. Bulamazsa boş string döner."""
    lookup = _build_oneri_lookup()
    return lookup.get(arama_text.strip().lower(), '')


def ara_urun(arama_text: str) -> Optional[pd.DataFrame]:
    """
    SERVER-SIDE SEARCH - Tüm arama SQL'de yapılır.
    Python sadece normalize + negatif filtre uygular.

    Query Router: Kod araması (exact) vs Metin araması (relevance) ayrımı yapar.
    """
    if not arama_text or len(arama_text) < 2:
        return None

    try:
        client = get_supabase_client()
        if not client:
            return None

        # Başta ürün kodu varsa sadece onu kullan ("25006169 - ÜRÜN ADI" gibi)
        arama_raw = arama_text.strip()
        kod_prefix_match = re.match(r'^\s*(\d{5,})\s*(?:-|–)\s*', arama_raw)

        if kod_prefix_match:
            optimize_sorgu = kod_prefix_match.group(1)
        elif arama_raw.isdigit():
            optimize_sorgu = arama_raw
        else:
            # Öneri listesinden seçilen ürün adını koda çevir (reverse lookup)
            resolved_kod = _oneri_ad_to_kod(arama_raw)
            if resolved_kod:
                optimize_sorgu = resolved_kod
            else:
                optimize_sorgu = temizle_ve_kok_bul(arama_raw)

        # --- Query Router: Kod mu, metin mi? ---
        is_kod_araması = optimize_sorgu.isdigit() and len(optimize_sorgu) >= 7

        def process_results(data, query):
            df = pd.DataFrame(data)
            df.columns = [col.replace('out_', '') for col in df.columns]

            # --- Akıllı Sıralama (Relevance Scoring) ---
            query_words = set(query.lower().split())

            def calculate_relevance(row):
                score = 0
                urun_ad = str(row.get('urun_ad', '')).lower()
                urun_kod = str(row.get('urun_kod', ''))

                # Kod eşleşme (en yüksek öncelik)
                if query.isdigit():
                    if urun_kod == query:
                        score += 1000
                    elif urun_kod.startswith(query):
                        score += 600
                    elif len(query) >= 6 and query in urun_kod:
                        score += 200

                # Tam eşleşme (metin)
                if query.lower() in urun_ad:
                    score += 100

                # Kelime bazlı eşleşme
                urun_words = set(urun_ad.split())
                common_words = query_words.intersection(urun_words)
                score += len(common_words) * 10

                # Stok puanı (Bonus)
                stok = row.get('stok_adet', 0)
                if stok > 0:
                    score += 5

                return score

            df['alaka'] = df.apply(calculate_relevance, axis=1)

            # TV Filtresi (sadece bağımsız kelime olarak "tv" veya "televizyon" varsa)
            query_words_set = set(query.lower().split())
            if query_words_set.intersection({'tv', 'televizyon'}):
                df = df[~df['urun_ad'].str.contains(RE_TV_NEGATIF, na=False, regex=True)]

            # Kısa sorgularda alakasızları (substring) temizle
            if len(query) <= 2:
                df = df[df['alaka'] > 0]

            # Hem alakaya hem de stok durumuna göre sırala
            df = df.sort_values(by=['alaka', 'stok_adet'], ascending=[False, False])
            df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])
            return df

        # RPC Çağrısı (Zaman aşımı kontrolü ile)
        try:
            result = client.rpc('hizli_urun_ara', {'arama_terimi': optimize_sorgu}).execute()
            if result.data:
                df = process_results(result.data, optimize_sorgu)

                # Kod araması: exact varsa SADECE exact dön
                if is_kod_araması and not df.empty:
                    exact = df[df['urun_kod'].astype(str) == optimize_sorgu]
                    if not exact.empty:
                        return exact

                return df
        except Exception as e:
            if not ("timeout" in str(e).lower() or "57014" in str(e)):
                logging.exception("ara_urun RPC call failed")
                st.error("Arama servisi şu an yanıt vermedi. Lütfen kısa süre sonra tekrar deneyin.")

        # Hata kontrolü (result nesnesi üzerinden)
        if 'result' in locals() and getattr(result, 'error', None):
            err_msg = str(result.error)
            if not ("timeout" in err_msg.lower() or "57014" in err_msg):
                logging.error("ara_urun RPC returned error: %s", result.error)
                st.error("Arama servisi şu an yanıt vermedi. Lütfen kısa süre sonra tekrar deneyin.")

        # Kod aramasında fallback yapma - kod ya var ya yok
        if is_kod_araması:
            st.warning("Bu ürün kodu bulunamadı. Kodu kontrol edip tekrar deneyin.")
            return pd.DataFrame()

        # ---- FALLBACK SEARCH (Google-like) ----
        # 1. Kategori temizleyip tekrar dene (Örn: "Seg klima" -> "Seg")
        kategoriler = {
            'klima', 'televizyon', 'tv', 'telefon', 'supurge', 'buzdolabi',
            'camasir', 'bulasik', 'makine', 'makinesi', 'makinası', 'ucretsiz', 'teslimat',
            'btu', 'inv', 'inverter'
        }
        sorgu_kelimeleri = optimize_sorgu.split()
        yeni_sorgu_kelimeleri = [w for w in sorgu_kelimeleri if w not in kategoriler]

        if 0 < len(yeni_sorgu_kelimeleri) < len(sorgu_kelimeleri):
            yeni_sorgu = " ".join(yeni_sorgu_kelimeleri)
            try:
                fallback_result = client.rpc('hizli_urun_ara', {'arama_terimi': yeni_sorgu}).execute()
                if fallback_result.data:
                    return process_results(fallback_result.data, optimize_sorgu)
            except: pass

        # 2. Kelimeleri Tek Tek Dene (Eğer çok kelimeliyse ve sonuç yoksa)
        if len(sorgu_kelimeleri) > 1:
            for w in sorgu_kelimeleri:
                if len(w) >= 3 and w not in kategoriler:
                    try:
                        fallback_result = client.rpc('hizli_urun_ara', {'arama_terimi': w}).execute()
                        if fallback_result.data:
                            return process_results(fallback_result.data, optimize_sorgu)
                    except: pass

        # 3. Kapasite temizleyip tekrar dene (Örn: "18000" -> "18")
        if "000" in optimize_sorgu:
            yeni_sorgu = optimize_sorgu.replace("000", "").strip()
            if len(yeni_sorgu) >= 2:
                try:
                    fallback_result = client.rpc('hizli_urun_ara', {'arama_terimi': yeni_sorgu}).execute()
                    if fallback_result.data:
                        return process_results(fallback_result.data, optimize_sorgu)
                except: pass

        # 4. İlk Kelimeyi Dene (Marka odaklı)
        if len(sorgu_kelimeleri) > 1:
            ilk_kelime = sorgu_kelimeleri[0]
            if len(ilk_kelime) >= 3 and ilk_kelime not in kategoriler:
                try:
                    fallback_result = client.rpc('hizli_urun_ara', {'arama_terimi': ilk_kelime}).execute()
                    if fallback_result.data:
                        return process_results(fallback_result.data, optimize_sorgu)
                except: pass

        # 5. En Uzun Kelimeyi Dene (Son çare)
        if len(sorgu_kelimeleri) > 1:
            en_uzun_kelime = max(sorgu_kelimeleri, key=len)
            if len(en_uzun_kelime) >= 4:
                try:
                    fallback_result = client.rpc('hizli_urun_ara', {'arama_terimi': en_uzun_kelime}).execute()
                    if fallback_result.data:
                        return process_results(fallback_result.data, optimize_sorgu)
                except: pass

        # Timeout uyarısı (Eğer buraya kadar gelip sonuç yoksa ve timeout olmuşsa)
        st.warning("Aradığınız kriterlerde sonuç bulunamadı veya veri tabanı meşgul. Lütfen daha kısa/farklı kelimeler deneyin.")
        return pd.DataFrame()

    except Exception:
        logging.exception("ara_urun unhandled error")
        st.error("Arama sırasında bir sorun oluştu. Lütfen kısa süre sonra tekrar deneyin.")
        return None


# Arama log'una yazılacak terimler için whitelist — HTML/script injection'a karşı
# sadece harf (Türkçe dahil), rakam, boşluk ve minimal noktalama karakterleri kalır.
_LOG_TERM_RE = re.compile(r"[^0-9a-zçğıöşüâîû\s\-.,']")


def _sanitize_log_term(term: str) -> str:
    """Log/popüler terim olarak saklanabilir güvenli bir string döndürür."""
    s = _safe_str(term).strip().lower()
    s = _LOG_TERM_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:100]


def log_arama(arama_terimi: str, sonuc_sayisi: int):
    """Arama logla (sessiz çalışır)"""
    try:
        client = get_supabase_client()
        if client and arama_terimi:
            terim = _sanitize_log_term(arama_terimi)
            if not terim or len(terim) < 2:
                return
            bugun = datetime.now().strftime('%Y-%m-%d')

            # Bugün bu terim arandı mı?
            result = client.table('arama_log')\
                .select('id, arama_sayisi')\
                .eq('tarih', bugun)\
                .eq('arama_terimi', terim)\
                .execute()

            simdi = datetime.now().isoformat()

            if result.data:
                kayit = result.data[0]
                veri = {'arama_sayisi': kayit['arama_sayisi'] + 1, 'sonuc_sayisi': sonuc_sayisi}
                try:
                    client.table('arama_log').update({**veri, 'son_arama_zamani': simdi}).eq('id', kayit['id']).execute()
                except Exception:
                    client.table('arama_log').update(veri).eq('id', kayit['id']).execute()
            else:
                veri = {'tarih': bugun, 'arama_terimi': terim, 'arama_sayisi': 1, 'sonuc_sayisi': sonuc_sayisi}
                try:
                    client.table('arama_log').insert({**veri, 'son_arama_zamani': simdi}).execute()
                except Exception:
                    client.table('arama_log').insert(veri).execute()
    except Exception:
        logging.exception("log_arama failed")


@st.cache_data(ttl=3600)
def get_populer_terimler():
    """En çok aranan ve sonuç getiren terimleri getir"""
    try:
        client = get_supabase_client()
        if not client: return []

        # Son 3 günün en çok aranan 10 terimi (en az 1 sonuç getirmiş olanlar)
        baslangic = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        result = client.table('arama_log')\
            .select('arama_terimi, arama_sayisi')\
            .gte('tarih', baslangic)\
            .gt('sonuc_sayisi', 0)\
            .order('arama_sayisi', desc=True)\
            .limit(10)\
            .execute()

        if result.data:
            # Defensive: DB'de eski/kötü biçimli terim varsa tekrar sanitize et.
            # Saf ürün kodlarını (tam sayı) filtrele (kullanıcıya anlamsız).
            terimler = []
            for r in result.data:
                raw = r.get('arama_terimi') or ""
                safe = _sanitize_log_term(raw)
                if not safe or len(safe) < 2 or safe.isdigit():
                    continue
                terimler.append(safe)
            return list(dict.fromkeys(terimler))[:10]
    except Exception:
        logging.exception("get_populer_terimler failed")
    return ["tv", "klima", "supurge", "mama", "tuvalet kagidi"]


def _get_oneri_listesi_impl():
    """Autocomplete için ürün önerilerini dosya tabanlı kaynaktan getir."""
    debug_info = []
    try:
        oneri_json_path = Path('data/oneri_listesi.json')
        if oneri_json_path.exists():
            with oneri_json_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                liste = [x for x in data if isinstance(x, str) and x.strip()]
                if liste:
                    debug_info.append(f"oneri_listesi.json OK: {len(liste)} öneri")
                    return liste, debug_info
    except Exception as e:
        debug_info.append(f"Genel hata: {e}")

    debug_info.append('oneri_listesi.json bulunamadı veya geçersiz')
    return [], debug_info

@st.cache_data(ttl=3600)
def get_oneri_listesi():
    """Cached wrapper — pipeline'ın ürettiği dosyadan okur."""
    liste, _ = _get_oneri_listesi_impl()
    return liste



def goster_sonuclar(df: pd.DataFrame, arama_text: str):
    """Sonuçları kartlar halinde göster"""
    # Hata varsa (None) sessizce çık - hata mesajı zaten basıldı
    if df is None:
        return

    sonuc_sayisi = 0 if df.empty else len(df['urun_kod'].unique())

    # Arka planda logla (UI bloklamaması için)
    # Kod aramasını ürün adına çevir (popüler aramalar çöplüğünü önler)
    log_terimi = arama_text
    if arama_text.strip().isdigit():
        # Kod araması → sonuçlardan ürün adını al
        if not df.empty and 'urun_ad' in df.columns:
            log_terimi = str(df.iloc[0]['urun_ad']).strip()
    threading.Thread(target=log_arama, args=(log_terimi, sonuc_sayisi), daemon=True).start()

    # Sonuç yoksa (empty) kullanıcıya bildir
    if df.empty:
        arama_raw = arama_text.strip()
        # "KOD - AD" formatını temizle
        if ' - ' in arama_raw:
            parts = arama_raw.split(' - ', 1)
            if parts[0].strip().isdigit():
                arama_raw = parts[0].strip()
        if arama_raw.isdigit() and len(arama_raw) >= 7:
            st.warning(f"Ürün kodu **{arama_raw}** sistemde kayıtlı ancak şu an hiçbir mağazada stok bilgisi bulunamadı.")
        else:
            st.warning(f"'{arama_text}' için sonuç bulunamadı.")
        return

    # Pandas Gruplama - SQL'den dönen sırayı koru
    # SQL rank DESC ile sıralı gelir, groupby bunu bozar
    # Bu yüzden ilk görünüş sırasını (SQL sırası) saklıyoruz
    urun_sirasi = df['urun_kod'].drop_duplicates().reset_index(drop=True)

    urunler = df.groupby('urun_kod').agg({
        'urun_ad': 'first',
        'stok_adet': lambda x: (x > 0).sum()
    }).reset_index()

    urunler.columns = ['urun_kod', 'urun_ad', 'stoklu_magaza']

    # SQL sırasına göre sırala
    urunler['sira'] = urunler['urun_kod'].map(
        {kod: i for i, kod in enumerate(urun_sirasi)}
    )
    urunler = urunler.sort_values('sira').drop('sira', axis=1)

    # Performans için sonuçları sınırla
    top_n = 40
    gosterilecek_urunler = urunler.head(top_n)

    if len(urunler) > top_n:
        st.info(f"🔍 Toplam {len(urunler)} ürün bulundu, en alakalı {top_n} ürün gösteriliyor.")
    else:
        st.success(f"**{len(urunler)}** farklı ürün bulundu")

    for _, urun in gosterilecek_urunler.iterrows():
        urun_kod = _safe_str(urun['urun_kod'])
        urun_ad = _safe_str(urun['urun_ad']) if urun['urun_ad'] else urun_kod
        stoklu_magaza = int(urun['stoklu_magaza'])

        urun_df = df[df['urun_kod'] == urun_kod].copy()
        urun_df_stoklu = urun_df[urun_df['stok_adet'] > 0].sort_values('stok_adet', ascending=False)

        # Toplam bölge stoku
        toplam_stok = int(urun_df_stoklu['stok_adet'].sum()) if not urun_df_stoklu.empty else 0

        # Fiyatı ürün seviyesinde al (ilk geçerli fiyat)
        ham_fiyat = urun_df_stoklu['birim_fiyat'].dropna()
        ham_fiyat = ham_fiyat[ham_fiyat > 0]
        if not ham_fiyat.empty:
            fiyat_val = float(ham_fiyat.iloc[0])
            fiyat_str = f"{fiyat_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"
        else:
            fiyat_str = ""

        icon = "📦" if stoklu_magaza > 0 else "❌"
        fiyat_badge = f"  ⸱  {fiyat_str}" if fiyat_str else ""
        baslik = f"{icon} {urun_kod}  •  {urun_ad[:40]}  •  🏪 {stoklu_magaza} mağaza{fiyat_badge}"

        with st.expander(baslik, expanded=False):
            # Üst bilgi satırı: Fiyat + Toplam Bölge Stoku
            badges_html = ""
            if fiyat_str:
                badges_html += f"""<div style="display:inline-block; background:linear-gradient(135deg,#00b894,#00cec9);
                     color:white; padding:6px 16px; border-radius:20px; font-weight:700;
                     font-size:1.05rem;">🏷️ {fiyat_str}</div>"""
            if toplam_stok > 0:
                badges_html += f"""<div style="display:inline-block; background:linear-gradient(135deg,#6c5ce7,#a29bfe);
                     color:white; padding:6px 16px; border-radius:20px; font-weight:700;
                     font-size:1.05rem; margin-left:8px;">📊 Toplam Bölge Stok: {toplam_stok}</div>"""
            if badges_html:
                st.markdown(_latin1_safe(f'<div style="margin-bottom:12px;">{badges_html}</div>'), unsafe_allow_html=True)
            if urun_df_stoklu.empty:
                st.error("Bu ürün hiçbir mağazada stokta yok!")
            else:
                html_cards = []
                for _, row in urun_df_stoklu.iterrows():
                    try:
                        seviye, _, renk = get_stok_seviye(row['stok_adet'])
                    except:
                        seviye, renk = "Normal", "#3498db"

                    magaza_ad = _safe_html(row['magaza_ad'] or row['magaza_kod'])

                    # Güvenli Veri Çekme
                    sm = _safe_html(row.get('sm_kod') or "-")
                    bs = _safe_html(row.get('bs_kod') or "-")
                    magaza_kod = _safe_html(row.get('magaza_kod') or "-")
                    seviye_escaped = _safe_html(seviye)

                    # Harita Linki
                    lat = row.get('latitude')
                    lon = row.get('longitude')

                    harita_ikonu = ""
                    if lat and lon:
                        try:
                            lat_f = float(lat)
                            lon_f = float(lon)
                            harita_ikonu = (
                                f'<a href="https://www.google.com/maps?q={lat_f},{lon_f}" '
                                'target="_blank" '
                                'rel="noopener noreferrer" '
                                'style="text-decoration:none; margin-left:8px; padding:4px 8px; '
                                'border-radius:12px; background:#eef2ff; color:#374151; font-size:0.78rem;" '
                                'title="Yol tarifi al">'
                                '📍 Yol tarifi</a>'
                            )
                        except (TypeError, ValueError):
                            harita_ikonu = ""

                    html_cards.append(f"""
                    <div style="
                        background: linear-gradient(135deg, {renk}22 0%, {renk}11 100%);
                        border-left: 4px solid {renk};
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
                            <div style="font-weight: 600; font-size: 1rem; color: #1e3a5f; display:flex; align-items:center;">
                                {magaza_ad}
                                {harita_ikonu}
                            </div>
                            <div style="font-size: 0.85rem; color: #666; margin-top: 4px;">
                                <b>SM:</b> {sm}  •  <b>BS:</b> {bs}  •  <i>{magaza_kod}</i>
                            </div>
                        </div>
                        <div style="background: {renk}; color: white; padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 0.85rem;">
                            {seviye_escaped}
                        </div>
                    </div>
                    """)
                st.markdown(_latin1_safe("".join(html_cards)), unsafe_allow_html=True)


# ============================================================================
# ANA UYGULAMA
# ============================================================================

def main():
    st.markdown("""
    <div class="main-header" id="top-anchor">
        <h1>Ürün Ara</h1>
        <p>Hangi mağazada ürün var? Hızlıca öğren!</p>
    </div>
    """, unsafe_allow_html=True)

    # Hotspot tıklama sonrası sayfayı yukarı kaydır
    if st.session_state.pop("_fe_scroll_top", False):
        import streamlit.components.v1 as _sc
        _sc.html('<script>window.parent.document.querySelector(".main").scrollTo({top:0,behavior:"smooth"});</script>', height=0)

    client = get_supabase_client()
    if not client:
        st.error("Veritabanı bağlantısı kurulamadı.")
        st.info("Lütfen ayarları kontrol edin.")
        return

    # Arama kutusu
    with st.form("arama_form", clear_on_submit=False, border=False):
        arama_text = st.text_input(
            "Arama",
            placeholder="Ürün kodu veya adı yazın (örn: kedi mama, tv 55)...",
            label_visibility="collapsed",
            key="arama_input"
        )
        ara_btn = st.form_submit_button("🔍 Ara", use_container_width=True, type="primary")

    # Autocomplete önerileri (client-side, performans dostu)
    oneriler = get_oneri_listesi()
    if oneriler:
        import json
        import streamlit.components.v1 as components
        # json.dumps default olarak </ ve <! escape etmez → inline <script>
        # içine embed ederken script-tag break / HTML comment başlangıcı riskine
        # karşı bu iki pattern'i nötralize ediyoruz.
        _ac_data = (
            json.dumps(oneriler, ensure_ascii=True)
            .replace("</", "<\\/")
            .replace("<!--", "<\\!--")
        )
        _ac_js = """
<script>
(function(){
try{
var S=__DATA__;
var pd=window.parent.document;
var inp=pd.querySelector('input[placeholder*="Ürün kodu"]');
if(!inp)return;
var old=pd.getElementById('ac-dd');if(old)old.remove();
if(inp._acIn)inp.removeEventListener('input',inp._acIn);
if(inp._acFo)inp.removeEventListener('focus',inp._acFo);
if(inp._acKu)inp.removeEventListener('keyup',inp._acKu);

var dd=pd.createElement('div');dd.id='ac-dd';
dd.style.cssText='display:none;position:absolute;left:0;right:0;top:100%;background:white;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 12px 12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);max-height:280px;overflow-y:auto;z-index:9999;';
var wr=inp.closest('[data-testid="stTextInput"]')||inp.parentElement;
wr.style.position='relative';wr.appendChild(dd);

dd.addEventListener('click',function(e){
  var it=e.target.closest('[data-t]');if(!it)return;
  var t=it.getAttribute('data-t') || '';
  var parts=t.split(' - ');
  var kod=parts.length>=2?parts[0].trim():'';
  var ad=parts.length>=2?parts[1].trim():t.trim();
  // Set product name in input
  var st=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
  st.call(inp,ad);
  // Store selected code in hidden attribute
  inp.setAttribute('data-selected-kod', kod);
  inp.dispatchEvent(new Event('input',{bubbles:true}));
  setTimeout(function(){inp.dispatchEvent(new Event('change',{bubbles:true}));inp.blur();},50);
  dd.style.display='none';
});

function esc(s){return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');}
function norm(s){
  var map={'\\u0130':'i','I':'i','\\u0131':'i','\\u011e':'g','\\u011f':'g','\\u00dc':'u','\\u00fc':'u','\\u015e':'s','\\u015f':'s','\\u00d6':'o','\\u00f6':'o','\\u00c7':'c','\\u00e7':'c'};
  var out='';
  for(var i=0;i<s.length;i++){out+=map[s[i]]||s[i];}
  if(out.normalize){out=out.normalize('NFD').replace(/[\u0300-\u036f]/g,'');}
  return out.toLowerCase().replace(/\\s+/g,' ').trim();
}

var IDX=S.map(function(raw){
  var parts=raw.split(' - ');
  var kod=parts.length>=2?parts[0].trim():'';
  var ad=parts.length>=2?parts[1].trim():raw;
  var fiyat=parts.length>=3?parts[2].trim():'';
  var nKod=norm(kod);
  var nAd=norm(ad);
  return {raw:raw,kod:kod,ad:ad,fiyat:fiyat,nKod:nKod,nAd:nAd};
});

function show(v){
  if(v.length<2){dd.style.display='none';return;}
  var q=norm(v);
  if(!q){dd.style.display='none';return;}

  function score(it){
    var ad=it.nAd, kod=it.nKod;
    if(!ad && !kod) return -1;
    if(ad===q) return 1000;
    if(ad.indexOf(q)===0) return 920;

    var isShort=q.length<=2;
    var adWords=ad.split(' ');
    for(var i=0;i<adWords.length;i++){
      if(adWords[i].indexOf(q)===0) return 820;
    }

    // Short queries: only match word-start to reduce noise
    if(!isShort && ad.indexOf(q)!==-1) return 560;

    if(kod && kod.indexOf(q)===0) return isShort ? 280 : 320;
    if(!isShort && kod && kod.indexOf(q)!==-1) return 180;

    // Short query: try compact match
    if(isShort){
      var compact=ad.replace(/\s+/g,'');
      if(compact.indexOf(q)===0) return 700;
    }

    return -1;
  }

  var m=[];
  for(var i=0;i<IDX.length;i++){
    var it=IDX[i];
    var sc=score(it);
    if(sc>0){m.push({it:it,sc:sc});}
  }
  m.sort(function(a,b){return b.sc-a.sc || a.it.raw.length-b.it.raw.length;});
  m=m.slice(0,12).map(function(x){return x.it;});
  if(!m.length){dd.style.display='none';return;}
  dd.innerHTML=m.map(function(it){
    var kod=it.kod,ad=it.ad,fiyat=it.fiyat,s=it.raw;
    var label='<span style="color:#333;font-size:0.92rem;">';
    if(kod) label+=esc(kod)+'-'+esc(ad);
    else label+=esc(ad);
    if(fiyat) label+='<span style="color:#e53935;font-weight:600;margin-left:4px;">'+esc(fiyat)+'TL</span>';
    label+='</span>';
    return '<div data-t="'+esc(s)+'" style="padding:9px 14px;cursor:pointer;display:flex;align-items:center;gap:8px;border-bottom:1px solid #f5f5f5;transition:background 0.15s;" onmouseover="this.style.background=\\'#f5f5fa\\'" onmouseout="this.style.background=\\'white\\'">'
    +'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#bbb" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
    +label+'</div>';
  }).join('');
  dd.style.display='block';
}

inp._acIn=function(e){show(e.target.value);};
inp._acFo=function(){if(inp.value.length>=2)show(inp.value);};
inp._acKu=function(){show(inp.value);};
inp.addEventListener('input',inp._acIn);
inp.addEventListener('focus',inp._acFo);
inp.addEventListener('keyup',inp._acKu);
pd.addEventListener('click',function(e){if(!dd.contains(e.target)&&e.target!==inp)dd.style.display='none';});
}catch(e){}
})();
</script>""".replace('__DATA__', _ac_data)
        components.html(_ac_js, height=0, scrolling=False)

    # Popüler Aramalar (Yatay kaydırmalı pill butonlar)
    def set_search_and_run(term):
        st.session_state._pop_arama = term

    populer = get_populer_terimler()

    if populer:
        st.markdown('<div class="popular-pill-anchor"></div>', unsafe_allow_html=True)
        st.markdown(_latin1_safe('<div style="font-size:0.85rem; font-weight:600; color:#555; padding:8px 0 2px 2px; margin-bottom:6px;">🔥 Popüler Aramalar</div>'), unsafe_allow_html=True)
        cols_pop = st.columns(len(populer))
        for i, p in enumerate(populer):
            cols_pop[i].button(p, use_container_width=True, key=f"pop_{p}_{i}", on_click=set_search_and_run, args=(p,))

    # Popüler pill tıklayınca da arama yap
    if st.session_state.get('_pop_arama'):
        pop_term = st.session_state.pop('_pop_arama')
        with st.spinner("Aranıyor..."):
            df = ara_urun(pop_term)
            # Sonuçları session state'e kaydet (poster rerun'larına dayanıklı)
            st.session_state["_fe_search_result"] = {"df": df, "term": pop_term}
    elif ara_btn:
        if arama_text and len(arama_text) >= 2:
            with st.spinner("Aranıyor..."):
                df = ara_urun(arama_text)
                st.session_state["_fe_search_result"] = {"df": df, "term": arama_text}
        elif arama_text:
            st.info("En az 2 karakter girin.")

    # Sonuçlar için poster üstünde placeholder
    result_slot = st.empty()

    # ---- Poster Slider (ön yüz) ----
    click_result = _frontend_poster_viewer()

    # Hotspot tıklandı → aramayı yap, sonucu kaydet
    if click_result:
        df = ara_urun(click_result)
        st.session_state["_fe_search_result"] = {"df": df, "term": click_result}

    # Kaydedilmiş arama sonuçlarını göster (poster üstünde placeholder'a)
    if "_fe_search_result" in st.session_state:
        sr = st.session_state["_fe_search_result"]
        with result_slot.container():
            rc1, rc2 = st.columns([6, 1])
            with rc2:
                if st.button("Temizle", key="fe_clear_results", use_container_width=True):
                    st.session_state.pop("_fe_search_result", None)
                    st.rerun()
            goster_sonuclar(sr["df"], sr["term"])


# ============================================================================
# FRONTEND POSTER VIEWER (Kullanıcı tarafı — ön yüz)
# ============================================================================

def _frontend_poster_viewer():
    """Ön yüzde poster sayfalarını slider ile gösteren bölüm.

    Performans:
    - Poster resimleri DB'den okunur (session bağımsız, her kullanıcı görür)
    - Sadece aktif sayfanın image'ı component'a gönderilir
    - Hotspot tıklayınca mevcut _pop_arama mekanizması tetiklenir (kod değişmez)
    """
    from components.poster_viewer import poster_viewer
    from storage import init_db, list_all_weeks, list_mappings_for_week, list_all_mappings_for_week, get_poster_pages, get_week

    # DB hazır mı
    if "fe_db_ready" not in st.session_state:
        init_db()
        st.session_state["fe_db_ready"] = True

    weeks = list_all_weeks()
    if not weeks:
        return  # Henüz poster yok, sessizce geç

    # Sadece yayında olan haftaları göster (meta yoksa göster — geriye uyum)
    visible_weeks = []
    week_meta_cache = {}
    for w in weeks:
        meta = get_week(w)
        week_meta_cache[w] = meta
        if meta is None or meta.get("status") == "published":
            visible_weeks.append(w)
    weeks = visible_weeks
    if not weeks:
        return

    # Hafta adlarını al (cached metadata kullan)
    week_names = {}
    for w in weeks:
        meta = week_meta_cache.get(w)
        week_names[w] = (meta.get("week_name") if meta else None) or w

    # İlk hafta varsayılan olarak seçili
    if "fe_week_select" not in st.session_state or st.session_state["fe_week_select"] not in weeks:
        st.session_state["fe_week_select"] = weeks[0]
    selected_week = st.session_state["fe_week_select"]

    # Hafta seçimi — st.pills (native widget, CSS hack gerektirmez)
    pill_options = [week_names[w] for w in weeks]
    pill_default = week_names[selected_week]
    picked = st.pills("Hafta", pill_options, default=pill_default, key="fe_week_pills", label_visibility="collapsed")
    if picked and picked != pill_default:
        for w in weeks:
            if week_names[w] == picked:
                st.session_state["fe_week_select"] = w
                st.session_state["fe_pv_idx"] = 0
                st.session_state.pop("_pv_cache_fe_poster_viewer", None)
                st.rerun()

    # Poster sayfalarını DB'den yükle (cache)
    cache_key = f"_fe_dbpages_{selected_week}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = get_poster_pages(selected_week)

    poster_pages = st.session_state[cache_key]
    if not poster_pages:
        return

    total_pages = len(poster_pages)

    # Sayfa navigasyonu
    if "fe_pv_idx" not in st.session_state:
        st.session_state["fe_pv_idx"] = 0

    cur_idx = st.session_state["fe_pv_idx"]
    if cur_idx >= total_pages:
        cur_idx = 0
        st.session_state["fe_pv_idx"] = 0

    pg = poster_pages[cur_idx]

    # Tüm sayfaları component'a gönder — navigasyon tamamen component içinde
    # Tek sorguda tüm mapping'leri al (7 ayrı HTTP yerine 1)
    all_mappings = list_all_mappings_for_week(selected_week)
    all_comp_pages = []
    for i, pp in enumerate(poster_pages):
        fn, pno = pp["flyer_filename"], pp["page_no"]
        m = [mx for mx in all_mappings if mx.get("flyer_filename") == fn and mx.get("page_no") == pno]
        hs = [{
            "x0": mx["x0"], "y0": mx["y0"], "x1": mx["x1"], "y1": mx["y1"],
            "urun_kodu": mx.get("urun_kodu") or "",
        } for mx in m]
        all_comp_pages.append({
            "png_bytes": pp["png_data"],
            "label": pp["title"] or f'Sayfa {i + 1}',
            "hotspots": hs,
        })

    # Component: search mode — navigasyon component içinde, hotspot tıklayınca urun_kodu döner
    result = poster_viewer(
        pages=all_comp_pages,
        current_index=cur_idx,
        click_mode="search",
        max_display_width=1200,
        height=900,
        key="fe_poster_viewer",
    )

    # Hotspot tıklandı → ürün kodunu döndür (rerun yok, çağıran fonksiyon işleyecek)
    if result and isinstance(result, dict):
        if result.get("type") == "hotspot_click":
            urun_kodu = (result.get("urun_kodu") or "").strip()
            click_ts = result.get("ts", 0)
            if urun_kodu and click_ts != st.session_state.get("_fe_last_click_ts"):
                st.session_state["_fe_last_click_ts"] = click_ts
                st.session_state["_fe_scroll_top"] = True
                page_idx = result.get("page_index")
                if page_idx is not None:
                    st.session_state["fe_pv_idx"] = page_idx
                return urun_kodu
    return None


# ============================================================================
# MAPPING TOOL TAB (Kutu Çiz + Ürün Ara — OCR'sız)
# ============================================================================

def _mapping_tool_tab():
    """Manuel bbox seçimi ile ürün eşleştirme aracı — Product Queue + hızlı akış."""
    import uuid as _uuid

    from components.bbox_canvas import bbox_canvas
    from mapping_ui.search import search_products, build_search_index

    # init_db sadece bir kez çalışsın
    if "mt_db_ready" not in st.session_state:
        from storage import init_db
        init_db()
        st.session_state["mt_db_ready"] = True

    from storage import (
        list_mappings as _db_list_mappings, delete_mapping as _db_delete_mapping,
        update_mapping as _db_update_mapping, save_week_products, get_week_products,
        get_mapped_product_codes as _db_get_mapped_codes, save_week,
        save_mapping as _db_save_mapping, mark_product_mapped as _db_mark_mapped,
        unmark_product_mapped as _db_unmark_mapped,
    )

    # --- Session state defaults ---
    for k, v in {
        "mt_pages": [],
        "mt_products": [],
        "mt_product_labels": [],
        "mt_week_id": datetime.now().strftime("%Y-%m-%d"),
        "mt_bbox": None,
        "mt_queue_kod": None,    # active product code in queue (stable identity)
        "mt_mode": "upload",     # upload | mapping
        "mt_pending_mappings": [],      # new mappings not yet saved to Supabase
        "mt_pending_deletes": [],       # DB mapping_ids to delete on flush
        "mt_pending_updates": {},       # {mapping_id: {field: val}} to update on flush
        "mt_pending_mapped_codes": set(),  # codes mapped in pending
        "mt_pending_unmapped_codes": set(),  # codes un-mapped (deleted) in pending
        "mt_db_cache": {},              # {page_key: [mapping_dicts]} — cached DB reads
        "mt_db_mapped_codes": None,     # cached DB mapped codes (loaded once)
        "mt_dirty": False,              # has unsaved changes
        "mt_next_temp_id": -1,          # temp IDs for pending mappings
        "mt_bbox_consumed": False,      # True after bbox is used (ignore stale canvas value)
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ====================================================================
    # UPLOAD PHASE
    # ====================================================================
    if st.session_state["mt_mode"] == "upload":
        from storage import list_weeks_with_meta, get_poster_pages, list_all_weeks

        # --- Yeni hafta oluştur ---
        st.subheader("Yeni Hafta Oluştur")

        c1, c2 = st.columns(2)
        with c1:
            mt_week = st.text_input("Hafta ID", value=st.session_state["mt_week_id"], key="mt_inp_week")
            if mt_week != st.session_state["mt_week_id"]:
                st.session_state["mt_db_cache"] = {}  # clear cache on week change
            st.session_state["mt_week_id"] = mt_week
            mt_week_name = st.text_input("Hafta Adı (opsiyonel)", key="mt_week_name",
                                         placeholder="Örn: Hafta 12 - Mart")
        with c2:
            mt_excel = st.file_uploader("Excel Ürün Listesi", type=["xlsx", "xls"], key="mt_excel")
            mt_pdfs = st.file_uploader("Afiş Dosyaları (PDF / JPEG / PNG)", type=["pdf", "jpeg", "jpg", "png"],
                                       accept_multiple_files=True, key="mt_pdfs")

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("Haftayı Yükle ve Eşleştirmeye Başla", type="primary",
                         key="mt_btn_load", use_container_width=True):
                # Çakışma kontrolü
                existing_weeks = list_all_weeks()
                if mt_week in existing_weeks and not mt_excel and not mt_pdfs:
                    st.error(f"**{mt_week}** zaten mevcut! Farklı bir ID girin veya aşağıdan devam edin.")
                else:
                    _mt_process_uploads(mt_week, mt_week_name, mt_excel, mt_pdfs, _uuid,
                                        save_week_products, save_week)
        with bc2:
            if st.session_state["mt_pages"]:
                if st.button("Eşleştirmeye Devam Et", key="mt_btn_continue", use_container_width=True):
                    st.session_state["mt_mode"] = "mapping"
                    st.rerun()

        # Mevcut durum özeti
        pages = st.session_state["mt_pages"]
        products = st.session_state["mt_products"]
        if pages or products:
            st.markdown("---")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("PDF Sayfası", len(pages))
            mc2.metric("Ürün", len(products))
            if pages:
                mapped_codes = get_mapped_product_codes(st.session_state["mt_week_id"])
                mc3.metric("Eşleştirilen", len(mapped_codes))

        # --- Mevcut haftaya devam et (DB'den yükle) ---
        st.markdown("---")
        st.subheader("Mevcut Haftaya Devam Et")

        existing_weeks = list_weeks_with_meta()
        if existing_weeks:
            ew_options = {w["week_id"]: f'{w.get("week_name") or w["week_id"]} — {w.get("page_count",0)} sayfa, {w.get("mapping_count",0)}/{w.get("product_count",0)} eşleşme' for w in existing_weeks}
            resume_wid = st.selectbox("Hafta seç:", list(ew_options.keys()),
                                      format_func=lambda k: ew_options[k], key="mt_resume_week")
            if st.button("Bu Haftayı Yükle ve Devam Et", key="mt_btn_resume", use_container_width=True):
                # DB'den poster pages ve products yükle
                db_pages = get_poster_pages(resume_wid)
                db_prods = get_week_products(resume_wid)
                if db_pages:
                    st.session_state["mt_pages"] = [{
                        "flyer_id": f"db_{pg['id']}",
                        "flyer_filename": pg["flyer_filename"],
                        "page_no": pg["page_no"],
                        "png_bytes": pg["png_data"],
                        "w": 0, "h": 0,
                    } for pg in db_pages]
                    raw_prods = [
                        {"urun_kod": p["urun_kodu"], "urun_ad": p.get("urun_aciklamasi", "")}
                        for p in db_prods
                    ]
                    st.session_state["mt_products"] = build_search_index(raw_prods)
                    st.session_state["mt_product_labels"] = [
                        f'{p["urun_kodu"]} — {p.get("urun_aciklamasi", "")}' for p in db_prods
                    ]
                    st.session_state["mt_week_id"] = resume_wid
                    st.session_state["mt_bbox"] = None
                    st.session_state["mt_queue_kod"] = None
                    st.session_state["mt_mode"] = "mapping"
                    st.rerun()
                else:
                    st.warning("Bu haftada poster sayfası bulunamadı.")
        else:
            st.info("Henüz hafta yok. Yukarıdan yeni oluşturun.")
        return

    # ====================================================================
    # MAPPING PHASE — ana eşleştirme editörü
    # ====================================================================
    pages = st.session_state["mt_pages"]
    products = st.session_state["mt_products"]
    product_labels = st.session_state["mt_product_labels"]
    week_id = st.session_state["mt_week_id"]

    if not pages:
        st.warning("Önce dosyaları yükleyin.")
        if st.button("Yükleme Ekranına Dön", key="mt_back_upload"):
            st.session_state["mt_mode"] = "upload"
            st.rerun()
        return

    # --- Üst bar: sayfa seç + durum + geri ---
    hdr1, hdr2, hdr3 = st.columns([4, 3, 1])
    with hdr1:
        page_labels = [f'{p["flyer_filename"]} - s{p["page_no"]}' for p in pages]
        sel_idx = st.selectbox("Sayfa", range(len(pages)),
                               format_func=lambda i: page_labels[i], key="mt_sel_page")
    with hdr2:
        # Load DB mapped codes once, then merge with pending
        if st.session_state["mt_db_mapped_codes"] is None:
            st.session_state["mt_db_mapped_codes"] = _db_get_mapped_codes(week_id)
        mapped_codes = (
            st.session_state["mt_db_mapped_codes"]
            | st.session_state["mt_pending_mapped_codes"]
        ) - st.session_state["mt_pending_unmapped_codes"]
        total_prods = len(products)
        mapped_count = len(mapped_codes)
        remaining = total_prods - mapped_count
        if total_prods > 0:
            pct = int(mapped_count / total_prods * 100)
            st.progress(pct / 100, text=f"{mapped_count}/{total_prods} eşleşti ({pct}%) - {remaining} kaldı")
        else:
            st.caption("Ürün listesi yüklenmedi")
    with hdr3:
        if st.button("Geri", key="mt_back"):
            st.session_state["mt_mode"] = "upload"
            st.rerun()

    page = pages[sel_idx]

    # Clear bbox when page changes
    page_id = f"{page['flyer_filename']}_p{page['page_no']}"
    if st.session_state.get("mt_current_page") != page_id:
        st.session_state["mt_current_page"] = page_id
        st.session_state["mt_bbox"] = None
        # No mt_bbox_consumed here — canvas key changes so no stale cached value

    # --- Load saved mappings (DB cache + pending) ---
    page_key = f'{week_id}_{page["flyer_filename"]}_p{page["page_no"]}'
    if page_key not in st.session_state["mt_db_cache"]:
        st.session_state["mt_db_cache"][page_key] = _db_list_mappings(
            week_id, page["flyer_filename"], page["page_no"])
    db_saved = st.session_state["mt_db_cache"][page_key]
    # Filter out DB mappings that are pending delete
    del_ids = set(st.session_state["mt_pending_deletes"])
    db_filtered = [m for m in db_saved if m["mapping_id"] not in del_ids]
    # Apply pending updates to DB mappings
    upd = st.session_state["mt_pending_updates"]
    for m in db_filtered:
        if m["mapping_id"] in upd:
            m.update(upd[m["mapping_id"]])
    # Merge: DB (filtered) + pending for this page
    pending_for_page = [
        m for m in st.session_state["mt_pending_mappings"]
        if m["flyer_filename"] == page["flyer_filename"] and m["page_no"] == page["page_no"]
    ]
    saved = db_filtered + pending_for_page
    saved_boxes = [
        {"x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
         "label": m.get("urun_kodu") or "?"}
        for m in saved
    ]

    # --- LAYOUT: sol=canvas (büyük), sağ=kontrol (kompakt) ---
    col_img, col_ctrl = st.columns([7, 3])

    with col_img:
        canvas_key = f"bbox_{page['flyer_filename']}_p{page['page_no']}"
        result = bbox_canvas(
            page_png_bytes=page["png_bytes"],
            saved_boxes=saved_boxes,
            active_bbox=st.session_state["mt_bbox"],
            key=canvas_key,
        )

        if result and isinstance(result, dict) and "x0" in result:
            # Ignore stale cached canvas value after bbox was consumed (save/clear)
            if st.session_state.get("mt_bbox_consumed"):
                st.session_state["mt_bbox_consumed"] = False
            elif result != st.session_state.get("mt_bbox"):
                st.session_state["mt_bbox"] = result
                # No st.rerun() — current run will use the updated value below

    with col_ctrl:
        bbox = st.session_state["mt_bbox"]

        # ── Seçim durumu ──
        if bbox:
            st.success(f"Kutu seçildi: ({bbox['x0']:.2f},{bbox['y0']:.2f})→({bbox['x1']:.2f},{bbox['y1']:.2f})")
        else:
            st.info("Poster üzerinde kutu çizin (ENTER ile onayla)")

        # ── Product Queue: Kalan / Tamamlanan / Arama sekmeleri ──
        q_tab_remaining, q_tab_search, q_tab_done, q_tab_manual = st.tabs(
            ["Kalan", "Ara", "Tamamlanan", "Manuel"])

        # Build remaining / completed lists
        remaining_prods = []
        completed_prods = []
        for i, p in enumerate(products):
            if p["urun_kod"] in mapped_codes:
                completed_prods.append((i, p))
            else:
                remaining_prods.append((i, p))

        # ── TAB: Kalan (Queue) ──
        with q_tab_remaining:
            if remaining_prods:
                st.caption(f"{len(remaining_prods)} ürün kaldı")

                # --- Selection by stable product code, not positional index ---
                # Resolve current selection from session_state (stored as urun_kod)
                sel_kod = st.session_state.get("mt_queue_kod")
                # Build code→index lookup for the current remaining list
                _rem_kod_to_idx = {rp["urun_kod"]: i for i, (_, rp) in enumerate(remaining_prods)}
                if sel_kod not in _rem_kod_to_idx:
                    # Selected product was mapped or doesn't exist — fall back to first
                    sel_kod = remaining_prods[0][1]["urun_kod"]
                    st.session_state["mt_queue_kod"] = sel_kod
                q_idx = _rem_kod_to_idx[sel_kod]

                # Paginate: show 15 items centered on active index
                _Q_PAGE = 15
                page_start = max(0, q_idx - _Q_PAGE // 2)
                page_end = min(len(remaining_prods), page_start + _Q_PAGE)
                page_start = max(0, page_end - _Q_PAGE)
                visible_slice = remaining_prods[page_start:page_end]

                # Radio options keyed by product code for stable identity
                radio_codes = [rp["urun_kod"] for _, rp in visible_slice]
                radio_labels_map = {
                    rp["urun_kod"]: f"`{rp['urun_kod']}` — {rp.get('urun_ad', '')}"
                    for _, rp in visible_slice
                }
                radio_default_idx = radio_codes.index(sel_kod) if sel_kod in radio_codes else 0

                sel_radio_code = st.radio(
                    "Ürün seç:", radio_codes,
                    index=radio_default_idx,
                    format_func=lambda c: radio_labels_map[c],
                    key="mt_q_radio",
                    label_visibility="collapsed",
                )
                # Sync radio selection back to stable code
                if sel_radio_code != sel_kod:
                    st.session_state["mt_queue_kod"] = sel_radio_code
                    sel_kod = sel_radio_code
                    q_idx = _rem_kod_to_idx[sel_kod]

                active_prod = remaining_prods[q_idx][1]

                # Page indicator
                if len(remaining_prods) > _Q_PAGE:
                    st.caption(f"Gösterilen: {page_start+1}–{page_end} / {len(remaining_prods)}")

                # Eşleştir butonu — saves by product code, not by index
                if st.button("Eşleştir (kutu + bu ürün)", key="mt_q_save",
                             type="primary", disabled=(bbox is None), use_container_width=True):
                    _mt_save_local(page, bbox, active_prod["urun_kod"],
                                   active_prod.get("urun_ad"), "excel")

                # Atla / Geri — advance by code identity
                ac1, ac2 = st.columns(2)
                with ac1:
                    if st.button("Atla →", key="mt_q_skip", use_container_width=True):
                        next_idx = (q_idx + 1) % len(remaining_prods)
                        st.session_state["mt_queue_kod"] = remaining_prods[next_idx][1]["urun_kod"]
                        st.rerun()
                with ac2:
                    if st.button("← Geri", key="mt_q_prev", use_container_width=True):
                        prev_idx = (q_idx - 1) % len(remaining_prods)
                        st.session_state["mt_queue_kod"] = remaining_prods[prev_idx][1]["urun_kod"]
                        st.rerun()
            else:
                st.success("Tüm ürünler eşleştirildi!")

        # ── TAB: Arama ──
        with q_tab_search:
            query = st.text_input("Ürün kodu veya adı:", key="mt_search_q",
                                  placeholder="Kod veya isim yazın...")
            if query and products:
                results = search_products(query, products, limit=10)
                if results:
                    # Radio keyed by product code for stable identity across reruns
                    sr_codes = [r["urun_kod"] for r in results]
                    sr_code_to_result = {r["urun_kod"]: r for r in results}
                    sr_labels_map = {}
                    for r in results:
                        is_mapped = r["urun_kod"] in mapped_codes
                        status = " ✓" if is_mapped else ""
                        sr_labels_map[r["urun_kod"]] = f"`{r['urun_kod']}` — {r.get('urun_ad', '')}{status}"

                    sel_sr_code = st.radio(
                        "Sonuç seç:", sr_codes,
                        format_func=lambda c: sr_labels_map[c],
                        key="mt_sr_radio",
                        label_visibility="collapsed",
                    )
                    sel_r = sr_code_to_result[sel_sr_code]
                    if st.button("Eşleştir (kutu + seçili)", key="mt_sr_save",
                                 type="primary", disabled=(bbox is None), use_container_width=True):
                        _mt_save_local(page, bbox, sel_r["urun_kod"],
                                       sel_r.get("urun_ad"), "excel")
                else:
                    st.caption("Sonuç bulunamadı")
            elif query and not products:
                st.warning("Önce Excel yükleyin.")

        # ── TAB: Tamamlanan ──
        with q_tab_done:
            if completed_prods:
                st.caption(f"{len(completed_prods)} ürün eşleştirildi")
                for _, cp in completed_prods[:50]:
                    st.markdown(f"~~`{cp['urun_kod']}`~~ {cp.get('urun_ad', '')}")
                if len(completed_prods) > 50:
                    st.caption(f"... ve {len(completed_prods) - 50} ürün daha")
            else:
                st.caption("Henüz eşleştirme yok")

        # ── TAB: Manuel ──
        with q_tab_manual:
            code_in = st.text_input("Ürün Kodu:", key="mt_code_in")
            desc_in = st.text_input("Açıklama:", key="mt_desc_in")
            if st.button("Kaydet", disabled=(not code_in or bbox is None),
                         key="mt_btn_save_manual", use_container_width=True):
                _mt_save_local(page, bbox, code_in.strip(), desc_in.strip() or None, "manual")

    # --- Hızlı eylemler: Kaydet + Undo + Toplu sil ---
    st.markdown("---")

    # "Değişiklikleri Kaydet" butonu (Supabase'e flush)
    if st.session_state["mt_dirty"]:
        pending_count = len(st.session_state["mt_pending_mappings"])
        del_count = len(st.session_state["mt_pending_deletes"])
        upd_count = len(st.session_state["mt_pending_updates"])
        change_parts = []
        if pending_count:
            change_parts.append(f"{pending_count} yeni")
        if del_count:
            change_parts.append(f"{del_count} silme")
        if upd_count:
            change_parts.append(f"{upd_count} güncelleme")
        change_text = ", ".join(change_parts)
        save_col1, save_col2 = st.columns([3, 5])
        with save_col1:
            if st.button(f"Kaydet ({change_text})", key="mt_flush_save",
                         type="primary", use_container_width=True):
                _mt_flush_to_supabase()
                st.success("Tüm değişiklikler Supabase'e kaydedildi!")
                st.rerun()
        with save_col2:
            st.caption("Kaydedilmemiş değişiklikleriniz var")

    undo_col, clear_col, spacer_col = st.columns([2, 2, 4])
    with undo_col:
        last_mid = st.session_state.get("mt_last_mapping_id")
        if last_mid and st.button("Geri Al (Son Eşleştirme)", key="mt_undo", use_container_width=True):
            # Silmeden önce ürün kodunu al
            undo_target = next((m for m in saved if m["mapping_id"] == last_mid), None)
            if last_mid < 0:
                # Pending mapping — remove from list
                st.session_state["mt_pending_mappings"] = [
                    m for m in st.session_state["mt_pending_mappings"]
                    if m["mapping_id"] != last_mid
                ]
            else:
                # DB mapping — schedule for deletion
                st.session_state["mt_pending_deletes"].append(last_mid)
            if undo_target and undo_target.get("urun_kodu"):
                code = undo_target["urun_kodu"]
                st.session_state["mt_pending_mapped_codes"].discard(code)
                st.session_state["mt_pending_unmapped_codes"].add(code)
            st.session_state["mt_dirty"] = True
            st.session_state.pop("mt_last_mapping_id", None)
            st.rerun()
    with clear_col:
        if saved:
            if st.button(f"Tümünü Sil ({len(saved)})", key="mt_clear_page", use_container_width=True):
                st.session_state["_confirm_clear_page"] = True
    if st.session_state.get("_confirm_clear_page"):
        st.warning(f"Bu sayfadaki **{len(saved)}** eşleştirme silinecek!")
        yc1, yc2 = st.columns(2)
        with yc1:
            if st.button("Evet, Tümünü Sil", key="mt_clear_yes", type="primary", use_container_width=True):
                # Pending ones — remove from list
                st.session_state["mt_pending_mappings"] = [
                    m for m in st.session_state["mt_pending_mappings"]
                    if not (m["flyer_filename"] == page["flyer_filename"] and m["page_no"] == page["page_no"])
                ]
                # DB ones — schedule for deletion
                for m in db_filtered:
                    st.session_state["mt_pending_deletes"].append(m["mapping_id"])
                # Unmark all affected product codes
                for m in saved:
                    if m.get("urun_kodu"):
                        st.session_state["mt_pending_mapped_codes"].discard(m["urun_kodu"])
                        st.session_state["mt_pending_unmapped_codes"].add(m["urun_kodu"])
                st.session_state["mt_dirty"] = True
                st.session_state.pop("_confirm_clear_page", None)
                st.rerun()
        with yc2:
            if st.button("İptal", key="mt_clear_no", use_container_width=True):
                st.session_state.pop("_confirm_clear_page", None)
                st.rerun()

    # --- Saved mappings: selectbox by mapping_id + edit form ---
    if saved:
        with st.expander(f"Bu Sayfadaki Eşleştirmeler ({len(saved)})", expanded=False):
            # Selectbox keyed by mapping_id (stable identity, not positional index)
            mid_list = [m["mapping_id"] for m in saved]
            mid_to_mapping = {m["mapping_id"]: m for m in saved}
            mid_labels = {}
            for m in saved:
                mid = m["mapping_id"]
                tag = f"*{abs(mid)}" if mid < 0 else f"#{mid}"
                mid_labels[mid] = f"{tag}  {m.get('urun_kodu') or '?'} — {m.get('urun_aciklamasi') or ''}"

            sel_mid = st.selectbox(
                "Eşleştirme seç:", mid_list,
                format_func=lambda mid: mid_labels[mid],
                key="mt_map_select",
            )
            sel_m = mid_to_mapping[sel_mid]
            is_pending = sel_mid < 0

            # Edit form — keys include mapping_id so inputs refresh on selection change
            new_kod = st.text_input("Kod", value=sel_m["urun_kodu"] or "", key=f"mt_ek_{sel_mid}")
            new_desc = st.text_input("Açıklama", value=sel_m["urun_aciklamasi"] or "", key=f"mt_ed_{sel_mid}")
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("Güncelle", key="mt_eu_sel", use_container_width=True):
                    if is_pending:
                        for pm in st.session_state["mt_pending_mappings"]:
                            if pm["mapping_id"] == sel_mid:
                                pm["urun_kodu"] = new_kod.strip()
                                pm["urun_aciklamasi"] = new_desc.strip() or None
                                break
                    else:
                        st.session_state["mt_pending_updates"][sel_mid] = {
                            "urun_kodu": new_kod.strip(),
                            "urun_aciklamasi": new_desc.strip() or None,
                        }
                    st.session_state["mt_dirty"] = True
                    st.rerun()
            with ec2:
                if st.button("Sil", key="mt_edel_sel", use_container_width=True):
                    if is_pending:
                        st.session_state["mt_pending_mappings"] = [
                            pm for pm in st.session_state["mt_pending_mappings"]
                            if pm["mapping_id"] != sel_mid
                        ]
                    else:
                        st.session_state["mt_pending_deletes"].append(sel_mid)
                    if sel_m.get("urun_kodu"):
                        st.session_state["mt_pending_mapped_codes"].discard(sel_m["urun_kodu"])
                        st.session_state["mt_pending_unmapped_codes"].add(sel_m["urun_kodu"])
                    st.session_state["mt_dirty"] = True
                    st.rerun()
    else:
        st.caption("Bu sayfada henüz eşleştirme yok.")


def _clear_week_session_state(week_id: str | None = None):
    """Hafta silindiğinde tüm ilişkili session state'i temizle."""
    # Prefix-based temizlik
    prefixes = ("_fe_dbpages_", "_pv_cache_", "_confirm_del_page_",
                "_confirm_del_week", "_confirm_del_wl_")
    for k in list(st.session_state.keys()):
        if any(k.startswith(p) for p in prefixes):
            st.session_state.pop(k, None)

    # Mapping mode: silinen hafta aktif haftaysa upload'a dön
    if week_id and st.session_state.get("mt_week_id") == week_id:
        for k in ("mt_pages", "mt_products", "mt_product_labels",
                  "mt_bbox", "mt_queue_kod"):
            st.session_state.pop(k, None)
        st.session_state["mt_mode"] = "upload"

    # Frontend viewer state
    st.session_state.pop("fe_pv_idx", None)
    st.session_state.pop("_fe_search_result", None)
    st.session_state.pop("_fe_last_click_ts", None)

    # Admin poster viewer state
    st.session_state.pop("pv_page_idx", None)


# ============================================================================
# POSTER VIEWER TAB (Admin — Başlık/Sıralama Yönetimi + Önizleme)
# ============================================================================

def _poster_viewer_tab():
    """Admin poster yönetimi: durum, başlık, sıralama, validasyon, önizleme."""
    from components.poster_viewer import poster_viewer
    from storage import (
        list_mappings as _pv_list,
        get_poster_pages, get_poster_pages_meta,
        update_poster_page, delete_poster_page,
        delete_week, list_all_weeks, get_week, update_week_status,
        list_weeks_with_meta, get_mapped_product_codes, get_week_products,
    )

    st.subheader("Poster Yönetimi")

    # Kaydedilmemiş değişiklik uyarısı
    if st.session_state.get("mt_dirty"):
        pending_n = len(st.session_state.get("mt_pending_mappings", []))
        del_n = len(st.session_state.get("mt_pending_deletes", []))
        upd_n = len(st.session_state.get("mt_pending_updates", {}))
        parts = []
        if pending_n:
            parts.append(f"{pending_n} yeni eşleştirme")
        if del_n:
            parts.append(f"{del_n} silme")
        if upd_n:
            parts.append(f"{upd_n} güncelleme")
        st.warning(
            f"Kaydedilmemiş değişiklikleriniz var: **{', '.join(parts)}**. "
            f"Lütfen önce 'Eşleştir' sekmesindeki **Kaydet** butonuna basın!"
        )

    weeks = list_all_weeks()
    if not weeks:
        st.info("Önce 'Eşleştir' sekmesinden PDF yükleyip 'Haftayı Yükle' basın.")
        return

    # --- Hafta Seçimi + Durum + Silme ---
    wc1, wc2, wc3 = st.columns([3, 2, 1])
    with wc1:
        selected_week = st.selectbox("Hafta:", weeks, key="pv_admin_week")
    with wc2:
        week_meta = get_week(selected_week)
        current_status = week_meta["status"] if week_meta else "draft"
        status_labels = {"draft": "Taslak", "published": "Yayında", "archived": "Arşiv"}
        status_colors = {"draft": "orange", "published": "green", "archived": "gray"}
        st.markdown(
            f'<span style="background:{status_colors.get(current_status,"gray")}; color:white; '
            f'padding:4px 12px; border-radius:12px; font-size:14px; font-weight:600;">'
            f'{status_labels.get(current_status, current_status)}</span>',
            unsafe_allow_html=True,
        )
        new_status = st.selectbox("Durumu değiştir:", ["draft", "published", "archived"],
                                   format_func=lambda s: status_labels.get(s, s),
                                   index=["draft", "published", "archived"].index(current_status),
                                   key="pv_status_sel")
        if new_status != current_status:
            if st.button("Durumu Güncelle", key="pv_status_update", use_container_width=True):
                update_week_status(selected_week, new_status)
                _clear_week_session_state()
                st.rerun()
    with wc3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Haftayı Sil", key="pv_del_week", use_container_width=True):
            st.session_state["_confirm_del_week"] = selected_week

    # Hafta silme onayı
    if st.session_state.get("_confirm_del_week") == selected_week:
        st.warning(f"**{selected_week}** haftasının tüm afiş sayfaları ve eşleştirmeleri silinecek!")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Evet, Sil", key="pv_confirm_yes", type="primary", use_container_width=True):
                delete_week(selected_week)
                _clear_week_session_state(selected_week)
                st.rerun()
        with cc2:
            if st.button("İptal", key="pv_confirm_no", use_container_width=True):
                st.session_state.pop("_confirm_del_week", None)
                st.rerun()

    # --- Validasyon özeti (metadata only — no image downloads) ---
    poster_pages_meta = get_poster_pages_meta(selected_week)
    week_products = get_week_products(selected_week)
    mapped_codes = get_mapped_product_codes(selected_week)

    # Bulk fetch all mappings (reused for validation + preview — 1 query instead of N)
    from storage import list_all_mappings_for_week
    all_week_mappings = list_all_mappings_for_week(selected_week)

    if week_products:
        unmapped = [p for p in week_products if p["urun_kodu"] not in mapped_codes]
        all_mapped_codes = [m["urun_kodu"] for m in all_week_mappings if m.get("urun_kodu")]
        from collections import Counter
        code_counts = Counter(all_mapped_codes)
        duplicates = {code: cnt for code, cnt in code_counts.items() if cnt > 1}

        vc1, vc2, vc3, vc4 = st.columns(4)
        vc1.metric("Sayfa", len(poster_pages_meta))
        vc2.metric("Ürün", len(week_products))
        vc3.metric("Eşleşen", len(mapped_codes))
        vc4.metric("Kalan", len(unmapped))

        if unmapped:
            with st.expander(f"Eşleştirilmemiş Ürünler ({len(unmapped)})", expanded=False):
                for p in unmapped:
                    st.markdown(f"- `{p['urun_kodu']}` {p.get('urun_aciklamasi', '')}")

        if duplicates:
            with st.expander(f"Duplikat Eşleştirmeler ({len(duplicates)})", expanded=False):
                for code, cnt in duplicates.items():
                    st.markdown(f"- `{code}` → {cnt} kez eşleştirilmiş")

    if not poster_pages_meta:
        st.info("Bu hafta için poster sayfası bulunamadı.")

    # --- Ürün Görsellerini Oluştur (backfill) ---
    if all_week_mappings:
        with st.expander("Ürün Görsellerini Oluştur", expanded=False):
            st.caption("Bu haftadaki tüm eşleştirmelerden ürün görselleri kırpılıp Supabase'e yüklenir.")
            mapped_with_code = [m for m in all_week_mappings if m.get("urun_kodu")]
            st.info(f"{len(mapped_with_code)} eşleştirme bulundu.")
            if st.button("Görselleri Oluştur", key="pv_backfill", type="primary", use_container_width=True):
                from storage import backfill_product_images
                progress = st.progress(0, text="Başlıyor...")
                def _update_progress(current, total):
                    progress.progress(current / total, text=f"{current}/{total} işlendi...")
                stats = backfill_product_images(selected_week, progress_callback=_update_progress)
                progress.empty()
                st.success(
                    f"Tamamlandı: {stats['uploaded']} yüklendi, "
                    f"{stats['skipped']} atlandı, {stats['errors']} hata"
                )

    # --- Yeni Afiş Ekleme (mevcut haftaya) ---
    with st.expander("Bu Haftaya Yeni Afiş Ekle", expanded=False):
        new_pdfs = st.file_uploader("Afiş Dosyası (PDF / JPEG / PNG)", type=["pdf", "jpeg", "jpg", "png"],
                                     accept_multiple_files=True, key="pv_new_pdf")
        if new_pdfs and st.button("Yükle", key="pv_upload_new", type="primary", use_container_width=True):
            from pdf_render import (
                render_pdf_bytes_to_pages, render_image_bytes_to_page,
                UploadValidationError,
            )
            from storage import save_poster_pages_bulk, get_max_sort_order
            base_sort = get_max_sort_order(selected_week) + 1
            new_pages = []
            rejected: list[str] = []
            for f in new_pdfs:
                raw = f.read()
                ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
                try:
                    if ext == "pdf":
                        rendered = render_pdf_bytes_to_pages(raw, zoom=2.0)
                        for p in rendered:
                            new_pages.append({
                                "week_id": selected_week,
                                "flyer_filename": f.name,
                                "page_no": p["page_no"],
                                "png_data": p["png_bytes"],
                                "sort_order": base_sort,
                            })
                            base_sort += 1
                    elif ext in ("jpeg", "jpg", "png"):
                        p = render_image_bytes_to_page(raw, f.name, page_no=1)
                        new_pages.append({
                            "week_id": selected_week,
                            "flyer_filename": f.name,
                            "page_no": 1,
                            "png_data": p["png_bytes"],
                            "sort_order": base_sort,
                        })
                        base_sort += 1
                    else:
                        rejected.append(f"{f.name}: desteklenmeyen uzantı")
                except UploadValidationError as e:
                    rejected.append(f"{f.name}: {e}")
            if rejected:
                st.warning("Bazı dosyalar atlandı:\n- " + "\n- ".join(rejected))
            if new_pages:
                save_poster_pages_bulk(new_pages)
                _clear_week_session_state()
                st.success(f"{len(new_pages)} sayfa eklendi!")
                st.rerun()

    if not poster_pages_meta:
        return

    # --- Afiş Sayfaları: Başlık, Sıralama, Silme ---
    st.markdown("#### Afiş Sayfaları")

    with st.form("pv_pages_form", clear_on_submit=False):
        for pg in poster_pages_meta:
            pid = pg["id"]
            tc1, tc2, tc3 = st.columns([3, 2, 1])
            with tc1:
                st.text_input(
                    "Başlık", value=pg["title"] or "",
                    key=f"pv_t_{pid}", label_visibility="collapsed",
                    placeholder=f'{pg["flyer_filename"]} s{pg["page_no"]}',
                )
            with tc2:
                st.caption(f'{pg["flyer_filename"]} — s{pg["page_no"]}')
            with tc3:
                st.text_input(
                    "Sıra", value=str(pg["sort_order"]),
                    key=f"pv_s_{pid}", label_visibility="collapsed",
                )

        if st.form_submit_button("Tümünü Kaydet", type="primary", use_container_width=True):
            changed = 0
            for pg in poster_pages_meta:
                pid = pg["id"]
                new_title = st.session_state.get(f"pv_t_{pid}", pg["title"] or "").strip()
                raw_sort = st.session_state.get(f"pv_s_{pid}", str(pg["sort_order"]))
                new_sort = int(raw_sort) if str(raw_sort).strip().isdigit() else pg["sort_order"]
                if new_title != (pg["title"] or "") or new_sort != pg["sort_order"]:
                    update_poster_page(pid, {"title": new_title, "sort_order": new_sort})
                    changed += 1
            if changed:
                _clear_week_session_state()
                st.success(f"{changed} sayfa güncellendi!")
            else:
                st.info("Değişiklik yok.")
            st.rerun()

    # Silme butonları (form dışında)
    with st.expander("Sayfa Sil", expanded=False):
        for pg in poster_pages_meta:
            pid = pg["id"]
            dc1, dc2 = st.columns([4, 1])
            with dc1:
                st.caption(f'{pg["flyer_filename"]} — s{pg["page_no"]}')
            with dc2:
                if st.session_state.get(f"_confirm_del_page_{pid}"):
                    if st.button("Onayla", key=f"pv_cdel_y_{pid}", type="primary", use_container_width=True):
                        delete_poster_page(pid, week_id=selected_week)
                        _clear_week_session_state()
                        st.rerun()
                else:
                    if st.button("Sil", key=f"pv_del_{pid}", use_container_width=True):
                        st.session_state[f"_confirm_del_page_{pid}"] = True
                        st.rerun()

    # --- Önizleme (lazy — only downloads images when expanded) ---
    st.markdown("---")
    st.markdown("#### Önizleme")

    # Cache full poster pages (with images) in session_state to avoid re-downloading
    _pv_cache_key = f"_pv_cache_{selected_week}"
    if _pv_cache_key not in st.session_state:
        st.session_state[_pv_cache_key] = get_poster_pages(selected_week)
    poster_pages_full = st.session_state[_pv_cache_key]

    # Group mappings by (flyer_filename, page_no) for O(1) lookup
    from collections import defaultdict
    _mappings_by_page = defaultdict(list)
    for m in all_week_mappings:
        _mappings_by_page[(m["flyer_filename"], m["page_no"])].append(m)

    viewer_pages = []
    for pg in poster_pages_full:
        page_mappings = _mappings_by_page.get((pg["flyer_filename"], pg["page_no"]), [])
        hotspots = [{
            "x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
            "urun_kodu": m.get("urun_kodu") or "?",
            "urun_ad": m.get("urun_aciklamasi") or "",
            "afis_fiyat": m.get("afis_fiyat") or "",
        } for m in page_mappings]
        label = pg["title"] or f'{pg["flyer_filename"]} - Sayfa {pg["page_no"]}'
        viewer_pages.append({
            "png_bytes": pg["png_data"],
            "label": label,
            "hotspots": hotspots,
        })

    result = poster_viewer(
        pages=viewer_pages,
        current_index=st.session_state.get("pv_page_idx", 0),
        click_mode="popup",
        key="poster_viewer_admin",
    )

    if result and isinstance(result, dict) and result.get("type") == "page_change":
        st.session_state["pv_page_idx"] = result["index"]


def _mt_process_uploads(mt_week, mt_week_name, mt_excel, mt_pdfs, _uuid,
                        save_week_products_fn, save_week_fn):
    """Process Excel + PDF uploads and switch to mapping mode."""
    from storage import save_poster_pages_bulk

    if mt_excel:
        try:
            df = pd.read_excel(mt_excel)
            col_map = {}
            for c in df.columns:
                cu = str(c).strip().upper()
                if "KOD" in cu:
                    col_map[c] = "urun_kodu"
                elif "AÇIKLAMA" in cu or "ACIKLAMA" in cu:
                    col_map[c] = "urun_aciklamasi"
                elif "FİYAT" in cu or "FIYAT" in cu:
                    col_map[c] = "afis_fiyat"
            if col_map:
                df = df.rename(columns=col_map)
            prods = []
            labels = []
            db_prods = []
            for _, r in df.iterrows():
                kod = str(r.get("urun_kodu", "")).strip()
                ad = str(r.get("urun_aciklamasi", "")).strip()
                fiyat = str(r.get("afis_fiyat", "")).strip() if "afis_fiyat" in r.index else ""
                prods.append({"urun_kod": kod, "urun_ad": ad})
                labels.append(f"{kod} — {ad}" if ad else kod)
                db_prods.append({"urun_kodu": kod, "urun_aciklamasi": ad, "afis_fiyat": fiyat})
            from mapping_ui.search import build_search_index
            st.session_state["mt_products"] = build_search_index(prods)
            st.session_state["mt_product_labels"] = labels
            # Persist product queue to DB
            save_week_products_fn(mt_week, db_prods)
        except Exception as e:
            st.error(f"Excel yükleme hatası: {e}")
            return

    if mt_pdfs:
        from pdf_render import (
            render_pdf_bytes_to_pages, render_image_bytes_to_page,
            UploadValidationError,
        )
        all_pages = []
        img_counter = {}  # filename → page counter for multi-image uploads
        rejected: list[str] = []
        for f in mt_pdfs:
            raw = f.read()
            ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
            try:
                if ext == "pdf":
                    rendered = render_pdf_bytes_to_pages(raw, zoom=2.0)
                    for p in rendered:
                        all_pages.append({
                            "flyer_id": str(_uuid.uuid4())[:8],
                            "flyer_filename": f.name,
                            "page_no": p["page_no"],
                            "png_bytes": p["png_bytes"],
                            "w": p["w"],
                            "h": p["h"],
                        })
                elif ext in ("jpeg", "jpg", "png"):
                    # Her resim dosyası = 1 sayfa
                    page_no = img_counter.get(f.name, 0) + 1
                    img_counter[f.name] = page_no
                    p = render_image_bytes_to_page(raw, f.name, page_no=page_no)
                    all_pages.append({
                        "flyer_id": str(_uuid.uuid4())[:8],
                        "flyer_filename": f.name,
                        "page_no": p["page_no"],
                        "png_bytes": p["png_bytes"],
                        "w": p["w"],
                        "h": p["h"],
                    })
                else:
                    rejected.append(f"{f.name}: desteklenmeyen uzantı")
            except UploadValidationError as e:
                rejected.append(f"{f.name}: {e}")
        if rejected:
            st.warning("Bazı dosyalar atlandı:\n- " + "\n- ".join(rejected))
        st.session_state["mt_pages"] = all_pages

        # Poster sayfalarını DB'ye kaydet (frontend için)
        save_poster_pages_bulk([{
            "week_id": mt_week,
            "flyer_filename": pg["flyer_filename"],
            "page_no": pg["page_no"],
            "png_data": pg["png_bytes"],
        } for pg in all_pages])

    # Save week metadata
    save_week_fn(mt_week, week_name=mt_week_name or mt_week)

    st.session_state["mt_bbox"] = None
    st.session_state["mt_queue_kod"] = None
    st.session_state["mt_mode"] = "mapping"
    st.rerun()


def _mt_save_local(page, bbox, urun_kod, urun_ad, source):
    """Save a mapping to session_state (in-memory). Flushed to Supabase on explicit save."""
    # Excel'den afis_fiyat bilgisini bul (session_state'ten, DB'den değil)
    afis_fiyat = None
    week_id = st.session_state["mt_week_id"]
    for p in st.session_state.get("mt_products", []):
        if p.get("urun_kod") == urun_kod:
            afis_fiyat = p.get("afis_fiyat") or None
            break

    # Temp negatif ID ata
    temp_id = st.session_state["mt_next_temp_id"]
    st.session_state["mt_next_temp_id"] = temp_id - 1

    mapping = {
        "mapping_id": temp_id,
        "week_id": week_id,
        "flyer_filename": page["flyer_filename"],
        "page_no": page["page_no"],
        "x0": bbox["x0"], "y0": bbox["y0"], "x1": bbox["x1"], "y1": bbox["y1"],
        "urun_kodu": urun_kod,
        "urun_aciklamasi": urun_ad,
        "afis_fiyat": afis_fiyat,
        "ocr_text": None,
        "source": source, "status": "matched",
        "created_at": datetime.utcnow().isoformat(),
    }
    st.session_state["mt_pending_mappings"].append(mapping)
    st.session_state["mt_pending_mapped_codes"].add(urun_kod)
    st.session_state["mt_pending_unmapped_codes"].discard(urun_kod)
    st.session_state["mt_dirty"] = True

    # Son eşleştirme ID'sini kaydet (Undo için)
    st.session_state["mt_last_mapping_id"] = temp_id
    # Clear bbox for next draw; mark consumed so stale canvas value is ignored
    st.session_state["mt_bbox"] = None
    st.session_state["mt_bbox_consumed"] = True
    st.rerun()


def _mt_flush_to_supabase():
    """Flush all pending mappings/deletes/updates to Supabase.

    Uses bulk operations: ~5 requests total instead of N per pending item.
    Also crops and uploads product images for new mappings.
    """
    from storage import (
        save_mappings_bulk, delete_mappings_bulk,
        update_mappings_bulk, mark_products_mapped_bulk,
        crop_and_upload_product_image,
    )
    week_id = st.session_state["mt_week_id"]

    # 1. Bulk insert pending mappings (strip temp IDs and index fields)
    insert_rows = []
    for m in st.session_state["mt_pending_mappings"]:
        row = {k: v for k, v in m.items()
               if k not in ("mapping_id", "_norm_text", "_norm_tokens", "_kod", "score")}
        insert_rows.append(row)
    save_mappings_bulk(insert_rows)

    # 1b. Crop and upload product images for new mappings
    # Build page lookup from session pages: (flyer_filename, page_no) → png_bytes
    _page_lookup = {}
    for pg in st.session_state.get("mt_pages", []):
        _page_lookup[(pg["flyer_filename"], pg["page_no"])] = pg["png_bytes"]

    for m in st.session_state["mt_pending_mappings"]:
        urun_kodu = m.get("urun_kodu")
        if not urun_kodu:
            continue
        png = _page_lookup.get((m["flyer_filename"], m["page_no"]))
        if not png:
            continue
        try:
            crop_and_upload_product_image(
                png, urun_kodu, m["x0"], m["y0"], m["x1"], m["y1"])
        except Exception:
            pass  # non-critical — mapping is saved regardless

    # 2. Bulk delete
    delete_mappings_bulk(st.session_state["mt_pending_deletes"], week_id=week_id)

    # 3. Bulk update
    update_mappings_bulk(st.session_state["mt_pending_updates"])

    # 4. Bulk mark/unmark products
    mark_products_mapped_bulk(week_id, st.session_state["mt_pending_mapped_codes"], mapped=True)
    mark_products_mapped_bulk(week_id, st.session_state["mt_pending_unmapped_codes"], mapped=False)

    # 5. Clear pending state
    st.session_state["mt_pending_mappings"] = []
    st.session_state["mt_pending_deletes"] = []
    st.session_state["mt_pending_updates"] = {}
    st.session_state["mt_pending_mapped_codes"] = set()
    st.session_state["mt_pending_unmapped_codes"] = set()
    st.session_state["mt_db_cache"] = {}  # invalidate cache
    st.session_state["mt_db_mapped_codes"] = None
    st.session_state["mt_dirty"] = False
    st.session_state["mt_next_temp_id"] = -1


# ============================================================================
# ADMIN PANEL
# ============================================================================

def admin_panel():
    """Admin paneli - sekmeli: Analitikler + Afiş Yönetimi"""
    from io import BytesIO

    admin_pass = os.environ.get('ADMIN_PASSWORD') or st.secrets.get('ADMIN_PASSWORD')

    if not admin_pass:
        st.error("Admin şifresi ayarlanmamış! Lütfen çevre değişkenlerini kontrol edin.")
        return

    if not st.session_state.get('admin_auth', False):
        st.title("Admin Girişi")

        # Basit rate-limit: 5 başarısız denemeden sonra 60 sn bekleme
        fails = int(st.session_state.get('admin_fails', 0))
        locked_until = float(st.session_state.get('admin_locked_until', 0))
        now = time.time()
        if locked_until > now:
            remaining = int(locked_until - now)
            st.error(f"Çok fazla hatalı deneme. Lütfen {remaining} sn bekleyin.")
            return

        password = st.text_input("Şifre:", type="password")
        if st.button("Giriş"):
            # Constant-time karşılaştırma (timing attack'e karşı)
            if hmac.compare_digest(str(password), str(admin_pass)):
                st.session_state.admin_auth = True
                st.session_state.admin_fails = 0
                st.session_state.admin_locked_until = 0
                st.rerun()
            else:
                fails += 1
                st.session_state.admin_fails = fails
                if fails >= 5:
                    st.session_state.admin_locked_until = now + 60
                    st.session_state.admin_fails = 0
                    st.error("Çok fazla hatalı deneme. 60 sn kilitlendi.")
                else:
                    st.error(f"Yanlış şifre! ({fails}/5)")
        return

    # ---- Header ----
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem 1rem;
        border-radius: 0 0 20px 20px;
        margin: -1rem -1rem 1.2rem -1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(102,126,234,0.3);
    ">
        <h1 style="color:white; font-size:1.6rem; font-weight:700; margin:0;">
            Admin Paneli
        </h1>
    </div>
    """, unsafe_allow_html=True)

    def df_to_xlsx(dataframe):
        """DataFrame'i xlsx byte'larına çevir"""
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            dataframe.to_excel(writer, index=False, sheet_name='Veri')
        return output.getvalue()

    # ---- Conditional router (replaces st.tabs to avoid executing all tabs on every rerun) ----
    _ADMIN_SECTIONS = ["Haftalar", "Eşleştir", "Poster Yönetimi", "Halk Günü", "Analitikler"]
    if "admin_section" not in st.session_state:
        st.session_state["admin_section"] = "Eşleştir"
    active = st.segmented_control(
        "Bölüm", _ADMIN_SECTIONS,
        default=st.session_state["admin_section"],
        key="admin_section_ctrl",
        selection_mode="single",
    )
    if active and active != st.session_state["admin_section"]:
        st.session_state["admin_section"] = active
    active = st.session_state["admin_section"]

    if active == "Haftalar":
        _admin_tab_weeks()
    elif active == "Eşleştir":
        _mapping_tool_tab()
    elif active == "Poster Yönetimi":
        _poster_viewer_tab()
    elif active == "Halk Günü":
        _admin_halkgunu()
    elif active == "Analitikler":
        _admin_tab_analytics(df_to_xlsx)

    # ---- Çıkış ----
    st.markdown("---")
    if st.button("Çıkış", key="admin_logout"):
        st.session_state.admin_auth = False
        st.rerun()


# ---------------------------------------------------------------------------
# ADMIN TAB: Hafta Listesi
# ---------------------------------------------------------------------------

def _admin_tab_weeks():
    """Hafta listesi — oluştur, düzenle, durum yönetimi."""
    from storage import (
        init_db, list_weeks_with_meta, list_all_weeks, get_week,
        save_week, update_week_status, update_week_sort_order, delete_week,
        get_poster_pages, get_mapped_product_codes, get_week_products,
    )
    init_db()

    st.subheader("Hafta Listesi")
    st.caption("Sıra numarası küçük olan hafta ön yüzde ilk gösterilir. Sıra 0 ise en yeni hafta varsayılan olur.")

    weeks = list_weeks_with_meta()
    status_labels = {"draft": "Taslak", "published": "Yayında", "archived": "Arşiv"}
    status_colors = {"draft": "#f0ad4e", "published": "#5cb85c", "archived": "#999"}

    if weeks:
        # Sıralama formu (render tetiklemeden numara girilebilir)
        with st.form("wl_sort_form", clear_on_submit=False):
            for w in weeks:
                wid = w["week_id"]
                sc1, sc2, sc3 = st.columns([0.8, 3, 4])
                with sc1:
                    cur_sort = w.get("sort_order", 0) or 0
                    st.text_input(
                        "Sıra", value=str(cur_sort),
                        key=f"wl_sort_{wid}", label_visibility="collapsed",
                    )
                with sc2:
                    name = _safe_html(w.get("week_name") or wid)
                    s = w.get("status", "draft")
                    label = _safe_html(status_labels.get(s, s))
                    color = status_colors.get(s, "#999")
                    badge = (f'<span style="background:{color}; color:white; '
                             f'padding:2px 8px; border-radius:10px; font-size:11px; margin-left:8px;">'
                             f'{label}</span>')
                    st.markdown(f"**{name}**{badge}", unsafe_allow_html=True)
                with sc3:
                    pg_cnt = w.get("page_count", 0)
                    mp_cnt = w.get("mapping_count", 0)
                    pr_cnt = w.get("product_count", 0)
                    st.caption(f"{pg_cnt} sayfa · {mp_cnt}/{pr_cnt} eşleşme")

            if st.form_submit_button("Sıralamayı Kaydet", type="primary", use_container_width=True):
                changed = 0
                for w in weeks:
                    wid = w["week_id"]
                    raw = st.session_state.get(f"wl_sort_{wid}", str(w.get("sort_order", 0) or 0))
                    new_val = int(raw) if str(raw).strip().isdigit() else (w.get("sort_order", 0) or 0)
                    if new_val != (w.get("sort_order", 0) or 0):
                        update_week_sort_order(wid, new_val)
                        changed += 1
                if changed:
                    st.success(f"{changed} hafta sıralaması güncellendi!")
                    st.rerun()
                else:
                    st.info("Değişiklik yok.")

        # Durum ve silme işlemleri (form dışında)
        for w in weeks:
            wid = w["week_id"]
            with st.container(border=True):
                wc1, wc2, wc3 = st.columns([3, 2, 1])
                with wc1:
                    name = w.get("week_name") or wid
                    st.caption(f"{name} ({wid})")
                with wc2:
                    s = w.get("status", "draft")
                    if s == "draft":
                        if st.button("Yayınla", key=f"wl_pub_{wid}", use_container_width=True):
                            update_week_status(wid, "published")
                            st.rerun()
                    elif s == "published":
                        if st.button("Arşivle", key=f"wl_arch_{wid}", use_container_width=True):
                            update_week_status(wid, "archived")
                            st.rerun()
                    else:
                        if st.button("Taslak Yap", key=f"wl_draft_{wid}", use_container_width=True):
                            update_week_status(wid, "draft")
                            st.rerun()
                with wc3:
                    if st.button("Sil", key=f"wl_del_{wid}", use_container_width=True):
                        st.session_state[f"_confirm_del_wl_{wid}"] = True

            if st.session_state.get(f"_confirm_del_wl_{wid}"):
                st.warning(f"**{w.get('week_name') or wid}** — tüm afişler, eşleştirmeler ve ürünler silinecek!")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("Evet, Sil", key=f"wl_cdel_y_{wid}", type="primary", use_container_width=True):
                        delete_week(wid)
                        _clear_week_session_state(wid)
                        st.rerun()
                with dc2:
                    if st.button("İptal", key=f"wl_cdel_n_{wid}", use_container_width=True):
                        st.session_state.pop(f"_confirm_del_wl_{wid}", None)
                        st.rerun()
    else:
        st.info("Henüz hafta oluşturulmamış. 'Eşleştir' sekmesinden başlayın.")

    # Hafta listesi olmayanları da göster (poster_pages'de var ama poster_weeks'de yok)
    all_week_ids = list_all_weeks()
    known_ids = {w["week_id"] for w in weeks}
    orphan_ids = [wid for wid in all_week_ids if wid not in known_ids]
    if orphan_ids:
        st.markdown("---")
        st.caption("Metadata'sı olmayan haftalar:")
        for oid in orphan_ids:
            oc1, oc2 = st.columns([4, 1])
            with oc1:
                st.markdown(f"`{oid}`")
            with oc2:
                if st.button("Kayıt Oluştur", key=f"wl_fix_{oid}", use_container_width=True):
                    save_week(oid, week_name=oid)
                    st.rerun()


# ---------------------------------------------------------------------------
# ADMIN TAB: Halk Günü (etkinlik yönetimi + afiş/liste modları)
# ---------------------------------------------------------------------------

_HG_SUBSECTIONS = ["Etkinlikler", "Afiş Modu", "Liste Modu", "Bizden Fotoğraflar", "Önizleme"]


def _admin_halkgunu():
    """Halk Günü ana sekmesi — alt sekmeli conditional router."""
    import halkgunu_storage as hgs

    st.subheader("Halk Günü")
    st.caption("Belirli tarihte belirli mağazalarda indirimli ürünler. "
               "Frontend halkgunu.net (ayrı Vercel app), aynı Supabase backend.")

    if "hg_section" not in st.session_state:
        st.session_state["hg_section"] = "Etkinlikler"
    sub_active = st.segmented_control(
        "Mod", _HG_SUBSECTIONS,
        default=st.session_state["hg_section"],
        key="hg_section_ctrl",
        selection_mode="single",
    )
    if sub_active and sub_active != st.session_state["hg_section"]:
        st.session_state["hg_section"] = sub_active
    sub_active = st.session_state["hg_section"]

    # Etkinlikler sekmesi bağımsız; diğerleri için ortak etkinlik seçimi
    if sub_active == "Etkinlikler":
        _admin_halkgunu_events()
        return

    events = hgs.list_events_with_meta()
    if not events:
        st.info("Önce 'Etkinlikler' sekmesinden bir etkinlik oluştur.")
        return

    options = [e["event_id"] for e in events]
    labels = {e["event_id"]: f"{e.get('event_name') or e['event_id']} ({e.get('event_date') or '—'})"
              for e in events}
    cur = st.session_state.get("hg_active_event") or options[0]
    if cur not in options:
        cur = options[0]
    selected = st.selectbox(
        "Etkinlik",
        options,
        index=options.index(cur),
        format_func=lambda x: labels.get(x, x),
        key="hg_event_select",
    )
    if selected != st.session_state.get("hg_active_event"):
        st.session_state["hg_active_event"] = selected
    event_id = st.session_state["hg_active_event"]
    event_meta = next((e for e in events if e["event_id"] == event_id), None)

    if sub_active == "Afiş Modu":
        _admin_halkgunu_poster_mode(event_id, event_meta)
    elif sub_active == "Liste Modu":
        _admin_halkgunu_list_mode(event_id, event_meta)
    elif sub_active == "Bizden Fotoğraflar":
        _admin_halkgunu_photos(event_id, event_meta)
    elif sub_active == "Önizleme":
        st.info("Önizleme yakında — frontend görünümünü buradan test edebileceksin.")


def _admin_halkgunu_events():
    """Etkinlik listesi — oluştur, sırala, durum, sil."""
    import halkgunu_storage as hgs

    st.markdown("#### Etkinlikler")
    st.caption("Sıra numarası küçük olan etkinlik halkgunu.net'te ilk gösterilir. "
               "Sıra 0 ise tarihi en yakın olan varsayılan olur.")

    # ---- YENİ ETKİNLİK ----
    with st.expander("➕ Yeni Etkinlik", expanded=False):
        with st.form("hg_new_event", clear_on_submit=True):
            nc1, nc2 = st.columns(2)
            with nc1:
                new_date = st.date_input("Etkinlik Tarihi", key="hg_new_date")
            with nc2:
                new_name = st.text_input(
                    "Görünen Ad",
                    placeholder="Örn: 15 Mayıs 2026 Halk Günü",
                    key="hg_new_name",
                )
            new_id = st.text_input(
                "Etkinlik ID (boş bırakılırsa tarihten üretilir)",
                placeholder="halkgunu_2026_05_15",
                key="hg_new_id",
            )
            if st.form_submit_button("Oluştur", type="primary", use_container_width=True):
                date_str = new_date.strftime("%Y-%m-%d") if new_date else ""
                event_id = (new_id or "").strip() or (
                    f"halkgunu_{date_str.replace('-', '_')}" if date_str else ""
                )
                if not event_id:
                    st.error("Etkinlik ID veya tarih gerekli.")
                elif hgs.get_event(event_id):
                    st.error(f"`{event_id}` zaten var.")
                else:
                    hgs.save_event(
                        event_id=event_id,
                        event_name=(new_name or event_id).strip(),
                        event_date=date_str,
                        status="draft",
                        sort_order=0,
                    )
                    st.success(f"Etkinlik oluşturuldu: {event_id}")
                    st.rerun()

    events = hgs.list_events_with_meta()
    status_labels = {"draft": "Taslak", "active": "Yayında", "archived": "Arşiv"}
    status_colors = {"draft": "#f0ad4e", "active": "#5cb85c", "archived": "#999"}

    if not events:
        st.info("Henüz etkinlik yok. Yukarıdan ilk etkinliği oluştur.")
        return

    # ---- SIRALAMA FORMU ----
    with st.form("hg_sort_form", clear_on_submit=False):
        for ev in events:
            eid = ev["event_id"]
            sc1, sc2, sc3 = st.columns([0.8, 3, 4])
            with sc1:
                cur_sort = ev.get("sort_order", 0) or 0
                st.text_input(
                    "Sıra", value=str(cur_sort),
                    key=f"hg_sort_{eid}", label_visibility="collapsed",
                )
            with sc2:
                name = _safe_html(ev.get("event_name") or eid)
                s = ev.get("status", "draft")
                label = _safe_html(status_labels.get(s, s))
                color = status_colors.get(s, "#999")
                badge = (
                    f'<span style="background:{color}; color:white; padding:2px 8px; '
                    f'border-radius:10px; font-size:11px; margin-left:8px;">{label}</span>'
                )
                st.markdown(f"**{name}**{badge}", unsafe_allow_html=True)
            with sc3:
                date_str = ev.get("event_date") or "—"
                pg_cnt = ev.get("page_count", 0)
                mp_cnt = ev.get("mapping_count", 0)
                pr_cnt = ev.get("product_count", 0)
                store_cnt = ev.get("store_count", 0)
                st.caption(
                    f"📅 {date_str} · {pg_cnt} sayfa · {mp_cnt} eşleşme · "
                    f"{pr_cnt} satır · {store_cnt} mağaza"
                )

        if st.form_submit_button("Sıralamayı Kaydet", type="primary", use_container_width=True):
            changed = 0
            for ev in events:
                eid = ev["event_id"]
                raw = st.session_state.get(f"hg_sort_{eid}", str(ev.get("sort_order", 0) or 0))
                new_val = int(raw) if str(raw).strip().lstrip("-").isdigit() else (ev.get("sort_order", 0) or 0)
                if new_val != (ev.get("sort_order", 0) or 0):
                    hgs.update_event_sort_order(eid, new_val)
                    changed += 1
            if changed:
                st.success(f"{changed} etkinlik sıralaması güncellendi.")
                st.rerun()
            else:
                st.info("Değişiklik yok.")

    # ---- DURUM & SİLME ----
    st.markdown("---")
    for ev in events:
        eid = ev["event_id"]
        with st.container(border=True):
            wc1, wc2, wc3 = st.columns([3, 2, 1])
            with wc1:
                st.caption(f"{ev.get('event_name') or eid} ({eid})")
            with wc2:
                s = ev.get("status", "draft")
                if s == "draft":
                    if st.button("Yayınla", key=f"hg_pub_{eid}", use_container_width=True):
                        hgs.update_event_status(eid, "active")
                        st.rerun()
                elif s == "active":
                    if st.button("Arşivle", key=f"hg_arch_{eid}", use_container_width=True):
                        hgs.update_event_status(eid, "archived")
                        st.rerun()
                else:
                    if st.button("Taslak Yap", key=f"hg_draft_{eid}", use_container_width=True):
                        hgs.update_event_status(eid, "draft")
                        st.rerun()
            with wc3:
                if st.button("Sil", key=f"hg_del_{eid}", use_container_width=True):
                    st.session_state[f"_confirm_del_hg_{eid}"] = True

        if st.session_state.get(f"_confirm_del_hg_{eid}"):
            st.warning(
                f"**{ev.get('event_name') or eid}** — tüm afişler, eşleştirmeler "
                f"ve indirim listesi silinecek!"
            )
            dc1, dc2 = st.columns(2)
            with dc1:
                if st.button("Evet, Sil", key=f"hg_cdel_y_{eid}", type="primary", use_container_width=True):
                    hgs.delete_event(eid)
                    st.session_state.pop(f"_confirm_del_hg_{eid}", None)
                    st.rerun()
            with dc2:
                if st.button("İptal", key=f"hg_cdel_n_{eid}", use_container_width=True):
                    st.session_state.pop(f"_confirm_del_hg_{eid}", None)
                    st.rerun()


# Excel kolon adlarını fiziksel şema kolonlarımıza eşleyen tablo.
# Kullanıcı "ürün kodu" / "URUN_KODU" / "Sku" yazsa da yakalanır.
_HG_EXCEL_COLUMN_MAP = {
    "urun_kod": ["urun_kod", "urun_kodu", "kod", "sku", "stok_kodu", "barkod_kod"],
    "urun_ad": ["urun_ad", "urun_adi", "urun_ismi", "urun_isim", "urun_aciklamasi", "aciklama", "urun", "ad", "isim"],
    "magaza_kod": ["magaza_kod", "magaza_kodu", "magaza", "store", "store_id", "store_code", "subekod", "sube_kod"],
    "magaza_ad": ["magaza_ad", "magaza_adi", "magaza_isim", "store_name", "sube_adi"],
    "normal_fiyat": ["normal_fiyat", "birim_fiyat", "birim_fiyati", "liste_fiyati", "liste_fiyat", "orijinal_fiyat", "fiyat", "satis_fiyat", "etiket_fiyat"],
    "indirimli_fiyat": ["indirimli_fiyat", "kampanya_fiyati", "kampanya_fiyat", "yeni_fiyat", "indirim_fiyat", "halkgunu_fiyat"],
}


def _hg_normalize_col(name) -> str:
    """Normalize an Excel header for fuzzy matching."""
    # Translate Turkish chars BEFORE lower(): Python's "İ".lower() yields
    # "i̇" (i + combining dot) which then breaks downstream regex.
    s = str(name or "").strip()
    s = s.translate(str.maketrans("ıİğĞüÜşŞöÖçÇ", "iIgGuUsSoOcC"))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _hg_resolve_excel_columns(df_columns) -> dict[str, str]:
    """Map physical schema fields → DataFrame column name (whichever variant is present)."""
    norm = {_hg_normalize_col(c): c for c in df_columns}
    out: dict[str, str] = {}
    for target, aliases in _HG_EXCEL_COLUMN_MAP.items():
        for a in aliases:
            if a in norm:
                out[target] = norm[a]
                break
    return out


# ---------------------------------------------------------------------------
# ADMIN TAB: Halk Günü → Afiş Modu (poster yükleme + sayfa yönetimi)
# ---------------------------------------------------------------------------

def _admin_halkgunu_poster_mode(event_id: str, event_meta: dict | None):
    """Afiş modu — PDF/JPG yükle + sayfa yönetimi + bbox eşleştirme."""
    import halkgunu_storage as hgs

    event_label = (event_meta or {}).get("event_name") or event_id

    # Phase toggle: "manage" (yükle + listele) | "mapping" (bbox eşleştir)
    phase_key = f"hg_poster_phase_{event_id}"
    if phase_key not in st.session_state:
        st.session_state[phase_key] = "manage"

    pc1, pc2, _ = st.columns([1.4, 1.4, 5])
    with pc1:
        if st.button(
            "📋 Sayfa Yönetimi",
            type=("primary" if st.session_state[phase_key] == "manage" else "secondary"),
            key=f"hg_phase_manage_{event_id}",
            use_container_width=True,
        ):
            st.session_state[phase_key] = "manage"
            st.rerun()
    with pc2:
        if st.button(
            "🎯 Bbox Eşleştirme",
            type=("primary" if st.session_state[phase_key] == "mapping" else "secondary"),
            key=f"hg_phase_mapping_{event_id}",
            use_container_width=True,
        ):
            st.session_state[phase_key] = "mapping"
            st.rerun()

    if st.session_state[phase_key] == "mapping":
        _admin_halkgunu_mapping_phase(event_id, event_label)
        return

    st.markdown(f"#### Afiş Modu — {event_label}")
    st.caption(
        "Afiş PDF veya JPG/PNG yükle. İndirim listesi (Excel) zaten 'Liste Modu' "
        "sekmesinde halkgunu_products tablosuna yüklendiği için burada tekrar "
        "yüklenmesine gerek yok."
    )

    # =========================================================================
    # 1) AFİŞ YÜKLE
    # =========================================================================
    with st.expander("📤 Afiş Yükle (PDF / JPG / PNG)", expanded=False):
        uploads = st.file_uploader(
            "Bir veya birden fazla dosya seç",
            type=["pdf", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"hg_poster_up_{event_id}",
        )
        if uploads and st.button(
            f"✅ {len(uploads)} dosyayı yükle ve sayfalara dönüştür",
            type="primary",
            key=f"hg_poster_save_{event_id}",
            use_container_width=True,
        ):
            from pdf_render import (
                render_pdf_bytes_to_pages,
                render_image_bytes_to_page,
                UploadValidationError,
            )
            base_sort = hgs.get_max_page_sort_order(event_id)
            all_pages: list[dict] = []
            rejected: list[str] = []
            img_counter: dict[str, int] = {}
            for f in uploads:
                raw = f.read()
                ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
                try:
                    if ext == "pdf":
                        rendered = render_pdf_bytes_to_pages(raw, zoom=2.0)
                        for p in rendered:
                            all_pages.append({
                                "event_id": event_id,
                                "flyer_filename": f.name,
                                "page_no": p["page_no"],
                                "png_data": p["png_bytes"],
                                "title": "",
                                "sort_order": 0,
                            })
                    elif ext in ("jpg", "jpeg", "png"):
                        page_no = img_counter.get(f.name, 0) + 1
                        img_counter[f.name] = page_no
                        p = render_image_bytes_to_page(raw, f.name, page_no=page_no)
                        all_pages.append({
                            "event_id": event_id,
                            "flyer_filename": f.name,
                            "page_no": p["page_no"],
                            "png_data": p["png_bytes"],
                            "title": "",
                            "sort_order": 0,
                        })
                    else:
                        rejected.append(f"{f.name}: desteklenmeyen uzantı")
                except UploadValidationError as e:
                    rejected.append(f"{f.name}: {e}")
                except Exception as e:
                    rejected.append(f"{f.name}: {e}")

            if rejected:
                st.warning("Bazı dosyalar atlandı:\n- " + "\n- ".join(rejected))

            if all_pages:
                # Yüklenen sayfaları mevcut sırlamanın sonuna ekle (1'er artırarak)
                for i, pg in enumerate(all_pages, start=1):
                    pg["sort_order"] = base_sort + i

                with st.spinner(f"{len(all_pages)} sayfa kaydediliyor…"):
                    hgs.save_pages_bulk(all_pages)
                st.success(f"{len(all_pages)} sayfa yüklendi.")
                st.rerun()

    # =========================================================================
    # 2) SAYFA LİSTESİ — başlık, sıra, sil
    # =========================================================================
    pages = hgs.get_event_pages_meta(event_id)
    if not pages:
        st.info("Bu etkinlik için henüz afiş sayfası yok. Yukarıdan yükle.")
        return

    st.markdown(f"**{len(pages)} sayfa**")

    # ---- Başlık + sıra formu (toplu kaydet) ----
    with st.form(f"hg_pages_form_{event_id}", clear_on_submit=False):
        for pg in pages:
            pid = pg["id"]
            cols = st.columns([1.2, 0.8, 3.5, 1.5])
            with cols[0]:
                if pg.get("url"):
                    st.image(pg["url"], width=120)
                else:
                    st.caption("(önizleme yok)")
            with cols[1]:
                cur_sort = pg.get("sort_order", 0) or 0
                st.text_input(
                    "Sıra",
                    value=str(cur_sort),
                    key=f"hg_pg_sort_{pid}",
                    label_visibility="collapsed",
                )
            with cols[2]:
                cur_title = pg.get("title") or ""
                st.text_input(
                    "Başlık",
                    value=cur_title,
                    key=f"hg_pg_title_{pid}",
                    placeholder="(opsiyonel)",
                    label_visibility="collapsed",
                )
            with cols[3]:
                st.caption(
                    f"{pg.get('flyer_filename','—')}\np.{pg.get('page_no','?')}"
                )

        if st.form_submit_button(
            "Başlık ve Sıralamayı Kaydet",
            type="primary",
            use_container_width=True,
        ):
            changed = 0
            for pg in pages:
                pid = pg["id"]
                raw_sort = st.session_state.get(f"hg_pg_sort_{pid}", str(pg.get("sort_order", 0) or 0))
                new_sort = (
                    int(raw_sort)
                    if str(raw_sort).strip().lstrip("-").isdigit()
                    else (pg.get("sort_order", 0) or 0)
                )
                new_title = st.session_state.get(f"hg_pg_title_{pid}", pg.get("title") or "")
                fields: dict = {}
                if new_sort != (pg.get("sort_order", 0) or 0):
                    fields["sort_order"] = new_sort
                if new_title != (pg.get("title") or ""):
                    fields["title"] = new_title
                if fields:
                    hgs.update_page(pid, fields)
                    changed += 1
            if changed:
                st.success(f"{changed} sayfa güncellendi.")
                st.rerun()
            else:
                st.info("Değişiklik yok.")

    # ---- Silme (form dışında, confirm flow ile) ----
    st.markdown("---")
    st.markdown("**Sayfa Sil**")
    for pg in pages:
        pid = pg["id"]
        with st.container(border=True):
            sc1, sc2, sc3 = st.columns([1, 4, 1])
            with sc1:
                if pg.get("url"):
                    st.image(pg["url"], width=80)
            with sc2:
                st.caption(
                    f"**{pg.get('title') or '(başlık yok)'}** — "
                    f"{pg.get('flyer_filename','?')} · p.{pg.get('page_no','?')} · "
                    f"sıra {pg.get('sort_order',0)}"
                )
            with sc3:
                if st.button("Sil", key=f"hg_pg_del_{pid}", use_container_width=True):
                    st.session_state[f"_confirm_del_hgpg_{pid}"] = True
        if st.session_state.get(f"_confirm_del_hgpg_{pid}"):
            st.warning(
                f"Bu sayfayı (ve sayfaya ait tüm bbox eşleştirmelerini) silmek "
                f"istediğine emin misin?"
            )
            dc1, dc2 = st.columns(2)
            with dc1:
                if st.button(
                    "Evet, Sil",
                    type="primary",
                    key=f"hg_pg_cdel_y_{pid}",
                    use_container_width=True,
                ):
                    hgs.delete_page(pid, event_id=event_id)
                    st.session_state.pop(f"_confirm_del_hgpg_{pid}", None)
                    st.rerun()
            with dc2:
                if st.button("İptal", key=f"hg_pg_cdel_n_{pid}", use_container_width=True):
                    st.session_state.pop(f"_confirm_del_hgpg_{pid}", None)
                    st.rerun()

    st.info(
        "Bbox eşleştirme için yukarıdaki **🎯 Bbox Eşleştirme** sekmesine geç."
    )


# ---------------------------------------------------------------------------
# ADMIN TAB: Halk Günü → Bbox Eşleştirme (Mapping editor)
# ---------------------------------------------------------------------------

def _hgmt_session_keys(event_id: str) -> dict:
    """Session state key map scoped to this event so multiple events don't collide."""
    return {
        "bbox": f"hgmt_bbox_{event_id}",
        "bbox_consumed": f"hgmt_bbox_consumed_{event_id}",
        "queue_kod": f"hgmt_queue_kod_{event_id}",
        "current_page": f"hgmt_current_page_{event_id}",
        "pending_mappings": f"hgmt_pending_mappings_{event_id}",
        "pending_deletes": f"hgmt_pending_deletes_{event_id}",
        "pending_updates": f"hgmt_pending_updates_{event_id}",
        "db_cache": f"hgmt_db_cache_{event_id}",
        "db_mapped_codes": f"hgmt_db_mapped_codes_{event_id}",
        "dirty": f"hgmt_dirty_{event_id}",
        "next_temp_id": f"hgmt_next_temp_id_{event_id}",
        "last_mapping_id": f"hgmt_last_mapping_id_{event_id}",
    }


def _hgmt_init_state(event_id: str) -> None:
    keys = _hgmt_session_keys(event_id)
    defaults = {
        "bbox": None,
        "bbox_consumed": False,
        "queue_kod": None,
        "current_page": None,
        "pending_mappings": [],
        "pending_deletes": [],
        "pending_updates": {},
        "db_cache": {},
        "db_mapped_codes": None,
        "dirty": False,
        "next_temp_id": -1,
        "last_mapping_id": None,
    }
    for short, default in defaults.items():
        full = keys[short]
        if full not in st.session_state:
            st.session_state[full] = default


def _hgmt_save_local(event_id: str, page: dict, bbox: dict,
                     urun_kod: str, urun_ad: str | None, source: str) -> None:
    """Add a new mapping to pending state (in-memory until flush)."""
    keys = _hgmt_session_keys(event_id)
    temp_id = st.session_state[keys["next_temp_id"]]
    st.session_state[keys["next_temp_id"]] = temp_id - 1

    mapping = {
        "mapping_id": temp_id,
        "event_id": event_id,
        "flyer_filename": page["flyer_filename"],
        "page_no": page["page_no"],
        "x0": bbox["x0"], "y0": bbox["y0"],
        "x1": bbox["x1"], "y1": bbox["y1"],
        "urun_kodu": urun_kod,
        "urun_aciklamasi": urun_ad,
        "afis_fiyat": None,
        "ocr_text": None,
        "source": source,
        "status": "matched",
        "created_at": datetime.utcnow().isoformat(),
    }
    st.session_state[keys["pending_mappings"]].append(mapping)
    st.session_state[keys["dirty"]] = True
    st.session_state[keys["last_mapping_id"]] = temp_id
    st.session_state[keys["bbox"]] = None
    st.session_state[keys["bbox_consumed"]] = True
    st.rerun()


def _hg_render_supabase_error(exc: Exception, title: str) -> None:
    """Surface a PostgREST APIError with code/details/hint instead of letting
    Streamlit redact it. Code 42501 = RLS violation."""
    code = getattr(exc, "code", "") or ""
    msg = getattr(exc, "message", "") or str(exc)
    details = getattr(exc, "details", "") or ""
    hint = getattr(exc, "hint", "") or ""
    parts = [f"**{title}**", f"`code={code or '?'}` · {msg}"]
    if details:
        parts.append(f"_details:_ {details}")
    if hint:
        parts.append(f"_hint:_ {hint}")
    if str(code) == "42501":
        parts.append(
            "→ Bu bir RLS (Row Level Security) reddi. "
            "Streamlit secrets'a `SUPABASE_SERVICE_ROLE_KEY` ekleyip Reboot etmiş olman gerek; "
            "veya Supabase'de bu tabloya INSERT/UPDATE policy ekle."
        )
    st.error("\n\n".join(parts))


def _hgmt_flush_to_supabase(event_id: str, page_lookup: dict) -> None:
    """Bulk-flush mapping changes (bbox coordinates only) to Supabase.

    Halk Günü ürün görselleri Liste Modu'ndan elle yükleniyor — bbox
    kırpmasını otomatik upload etmiyoruz, çünkü bu Liste Modu'nda
    yüklenen temiz görsellerin üzerine yazıyor. Bbox koordinatları
    kayıtlı kalıyor (halkgunu.net tıklama haritası için).
    """
    import halkgunu_storage as hgs

    keys = _hgmt_session_keys(event_id)
    pending = st.session_state[keys["pending_mappings"]]
    deletes = st.session_state[keys["pending_deletes"]]
    updates = st.session_state[keys["pending_updates"]]

    insert_rows = []
    for m in pending:
        row = {k: v for k, v in m.items()
               if k not in ("mapping_id", "_norm_text", "_norm_tokens", "_kod", "score")}
        insert_rows.append(row)
    if insert_rows:
        hgs.save_mappings_bulk(insert_rows)

    if deletes:
        hgs.delete_mappings_bulk(deletes, event_id=event_id)
    if updates:
        hgs.update_mappings_bulk(updates)

    # Reset
    st.session_state[keys["pending_mappings"]] = []
    st.session_state[keys["pending_deletes"]] = []
    st.session_state[keys["pending_updates"]] = {}
    st.session_state[keys["db_cache"]] = {}
    st.session_state[keys["db_mapped_codes"]] = None
    st.session_state[keys["dirty"]] = False
    st.session_state[keys["next_temp_id"]] = -1


def _admin_halkgunu_mapping_phase(event_id: str, event_label: str) -> None:
    """Bbox eşleştirme — Ara'nın _mapping_tool_tab eşdeğeri, halkgunu için sadeleştirilmiş."""
    import halkgunu_storage as hgs
    from components.bbox_canvas import bbox_canvas
    from mapping_ui.search import search_products, build_search_index

    _hgmt_init_state(event_id)
    keys = _hgmt_session_keys(event_id)

    st.markdown(f"#### 🎯 Bbox Eşleştirme — {event_label}")

    # Connection mode badge — RLS sorunlarını teşhis için
    from storage import _get_client, get_client_key_source
    _get_client()  # ensure singleton initialised so the source flag is set
    key_src = get_client_key_source()
    if key_src == "service_role":
        st.caption("🔓 Bağlantı: **service_role** (RLS bypass)")
    elif key_src == "anon":
        st.caption("⚠️ Bağlantı: **anon** — yazma için RLS policy'leri aktif olmalı. "
                   "Secrets'a `SUPABASE_SERVICE_ROLE_KEY` ekleyip Reboot tavsiye edilir.")

    # ---- Sayfaları DB'den çek (görseller dahil — canvas için png gerek) ----
    cache_key = f"_hgmt_pages_cache_{event_id}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = hgs.get_event_pages(event_id)
    pages = st.session_state[cache_key]
    if not pages:
        st.warning("Bu etkinlik için afiş sayfası yok. Sayfa Yönetimi sekmesinden yükleyin.")
        return

    # ---- Ürün kuyruğu — halkgunu_products'tan distinct urun_kod ----
    summary = hgs.get_event_product_summary(event_id)
    if not summary:
        st.warning("Ürün listesi yok. Liste Modu'ndan Excel yükleyin.")
        return
    products_raw = [{"urun_kod": s["urun_kod"], "urun_ad": s.get("urun_ad") or ""} for s in summary]
    products = build_search_index(products_raw)

    # ---- DB mapped codes (cached) ----
    if st.session_state[keys["db_mapped_codes"]] is None:
        db_mapped = {m.get("urun_kodu") for m in hgs.list_event_mappings(event_id) if m.get("urun_kodu")}
        st.session_state[keys["db_mapped_codes"]] = db_mapped
    pending_mapped = {m.get("urun_kodu") for m in st.session_state[keys["pending_mappings"]] if m.get("urun_kodu")}
    pending_deletes = set(st.session_state[keys["pending_deletes"]])
    pending_unmapped: set = set()
    if pending_deletes:
        # Find which urun_kodu codes those deletions remove
        for cache_pg_mappings in st.session_state[keys["db_cache"]].values():
            for m in cache_pg_mappings:
                if m["mapping_id"] in pending_deletes and m.get("urun_kodu"):
                    pending_unmapped.add(m["urun_kodu"])
    mapped_codes = (st.session_state[keys["db_mapped_codes"]] | pending_mapped) - pending_unmapped

    # ---- Üst bar: sayfa seç + ilerleme ----
    hdr1, hdr2 = st.columns([4, 4])
    with hdr1:
        page_labels = [f'{p["flyer_filename"]} - s{p["page_no"]}' for p in pages]
        sel_idx = st.selectbox(
            "Sayfa", range(len(pages)),
            format_func=lambda i: page_labels[i],
            key=f"hgmt_sel_page_{event_id}",
        )
    with hdr2:
        total = len(products)
        mapped = len(mapped_codes)
        if total:
            pct = int(mapped / total * 100)
            st.progress(
                pct / 100,
                text=f"{mapped}/{total} eşleşti ({pct}%) — {total - mapped} kaldı",
            )

    page = pages[sel_idx]

    # ---- Reset bbox on page change ----
    page_id = f"{page['flyer_filename']}_p{page['page_no']}"
    if st.session_state.get(keys["current_page"]) != page_id:
        st.session_state[keys["current_page"]] = page_id
        st.session_state[keys["bbox"]] = None

    # ---- Load page mappings (DB cache + pending) ----
    page_key = f'{event_id}_{page["flyer_filename"]}_p{page["page_no"]}'
    cache = st.session_state[keys["db_cache"]]
    if page_key not in cache:
        cache[page_key] = hgs.list_page_mappings(event_id, page["flyer_filename"], page["page_no"])
    db_saved = cache[page_key]
    db_filtered = [m for m in db_saved if m["mapping_id"] not in pending_deletes]
    upd = st.session_state[keys["pending_updates"]]
    for m in db_filtered:
        if m["mapping_id"] in upd:
            m.update(upd[m["mapping_id"]])
    pending_for_page = [
        m for m in st.session_state[keys["pending_mappings"]]
        if m["flyer_filename"] == page["flyer_filename"]
        and m["page_no"] == page["page_no"]
    ]
    saved = db_filtered + pending_for_page
    saved_boxes = [
        {"x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
         "label": m.get("urun_kodu") or "?"}
        for m in saved
    ]

    # ---- LAYOUT ----
    col_img, col_ctrl = st.columns([7, 3])

    with col_img:
        canvas_key = f"hgmt_bbox_{event_id}_{page['flyer_filename']}_p{page['page_no']}"
        png_bytes = page.get("png_data") or b""
        if not png_bytes:
            st.error(
                f"⚠️ Sayfa görseli yüklenemedi: `{page.get('image_path') or '?'}`. "
                f"Storage'da dosya yok ya da indirilemedi. "
                f"Afişi 'Sayfa Yönetimi' sekmesinden yeniden yükle."
            )
            result = None
        else:
            try:
                result = bbox_canvas(
                    page_png_bytes=png_bytes,
                    saved_boxes=saved_boxes,
                    active_bbox=st.session_state[keys["bbox"]],
                    key=canvas_key,
                )
            except Exception as e:
                from PIL import UnidentifiedImageError
                if isinstance(e, UnidentifiedImageError):
                    st.error(
                        f"⚠️ Sayfa görseli geçersiz (PIL açamadı): "
                        f"`{page.get('image_path') or '?'}`. "
                        f"Boyut: {len(png_bytes)} byte. "
                        f"Afişi 'Sayfa Yönetimi' sekmesinden tekrar yükle."
                    )
                    # Cache'i temizle ki tekrar denemede taze indirme olsun
                    st.session_state.pop(f"_bbox_b64_{canvas_key}", None)
                    result = None
                else:
                    raise
        if result and isinstance(result, dict) and "x0" in result:
            if st.session_state.get(keys["bbox_consumed"]):
                st.session_state[keys["bbox_consumed"]] = False
            elif result != st.session_state.get(keys["bbox"]):
                st.session_state[keys["bbox"]] = result

    with col_ctrl:
        bbox = st.session_state[keys["bbox"]]
        if bbox:
            st.success(
                f"Kutu: ({bbox['x0']:.2f},{bbox['y0']:.2f})→"
                f"({bbox['x1']:.2f},{bbox['y1']:.2f})"
            )
        else:
            st.info("Poster üzerinde kutu çizin (ENTER ile onayla)")

        q_remaining, q_search, q_done, q_manual = st.tabs(
            ["Kalan", "Ara", "Tamamlanan", "Manuel"]
        )

        remaining_prods = [(i, p) for i, p in enumerate(products) if p["urun_kod"] not in mapped_codes]
        completed_prods = [(i, p) for i, p in enumerate(products) if p["urun_kod"] in mapped_codes]

        # ── Kalan ──
        with q_remaining:
            if remaining_prods:
                st.caption(f"{len(remaining_prods)} ürün kaldı")
                sel_kod = st.session_state[keys["queue_kod"]]
                rem_idx = {rp["urun_kod"]: i for i, (_, rp) in enumerate(remaining_prods)}
                if sel_kod not in rem_idx:
                    sel_kod = remaining_prods[0][1]["urun_kod"]
                    st.session_state[keys["queue_kod"]] = sel_kod
                q_idx = rem_idx[sel_kod]

                _Q = 15
                start = max(0, q_idx - _Q // 2)
                end = min(len(remaining_prods), start + _Q)
                start = max(0, end - _Q)
                visible = remaining_prods[start:end]
                radio_codes = [rp["urun_kod"] for _, rp in visible]
                radio_labels = {rp["urun_kod"]: f"`{rp['urun_kod']}` — {rp.get('urun_ad','')}"
                                for _, rp in visible}
                idx_in_visible = radio_codes.index(sel_kod) if sel_kod in radio_codes else 0
                sel_radio = st.radio(
                    "Ürün seç:", radio_codes,
                    index=idx_in_visible,
                    format_func=lambda c: radio_labels[c],
                    key=f"hgmt_q_radio_{event_id}",
                    label_visibility="collapsed",
                )
                if sel_radio != sel_kod:
                    st.session_state[keys["queue_kod"]] = sel_radio
                    sel_kod = sel_radio
                    q_idx = rem_idx[sel_kod]
                active_prod = remaining_prods[q_idx][1]
                if len(remaining_prods) > _Q:
                    st.caption(f"Gösterilen: {start+1}–{end} / {len(remaining_prods)}")

                if st.button(
                    "Eşleştir (kutu + bu ürün)",
                    type="primary",
                    disabled=(bbox is None),
                    key=f"hgmt_q_save_{event_id}",
                    use_container_width=True,
                ):
                    _hgmt_save_local(event_id, page, bbox, active_prod["urun_kod"],
                                     active_prod.get("urun_ad"), "manual")

                ac1, ac2 = st.columns(2)
                with ac1:
                    if st.button("Atla →", key=f"hgmt_skip_{event_id}", use_container_width=True):
                        n = (q_idx + 1) % len(remaining_prods)
                        st.session_state[keys["queue_kod"]] = remaining_prods[n][1]["urun_kod"]
                        st.rerun()
                with ac2:
                    if st.button("← Geri", key=f"hgmt_prev_{event_id}", use_container_width=True):
                        n = (q_idx - 1) % len(remaining_prods)
                        st.session_state[keys["queue_kod"]] = remaining_prods[n][1]["urun_kod"]
                        st.rerun()
            else:
                st.success("Tüm ürünler eşleştirildi!")

        # ── Ara ──
        with q_search:
            query = st.text_input("Ürün kodu veya adı:", key=f"hgmt_q_search_{event_id}")
            if query:
                results = search_products(query, products, limit=10)
                if results:
                    sr_codes = [r["urun_kod"] for r in results]
                    sr_lookup = {r["urun_kod"]: r for r in results}
                    sr_labels = {
                        r["urun_kod"]: (
                            f"`{r['urun_kod']}` — {r.get('urun_ad', '')}"
                            f"{' ✓' if r['urun_kod'] in mapped_codes else ''}"
                        )
                        for r in results
                    }
                    sel_sr = st.radio(
                        "Sonuç seç:", sr_codes,
                        format_func=lambda c: sr_labels[c],
                        key=f"hgmt_sr_radio_{event_id}",
                        label_visibility="collapsed",
                    )
                    sel_r = sr_lookup[sel_sr]
                    if st.button(
                        "Eşleştir (kutu + seçili)",
                        type="primary",
                        disabled=(bbox is None),
                        key=f"hgmt_sr_save_{event_id}",
                        use_container_width=True,
                    ):
                        _hgmt_save_local(event_id, page, bbox, sel_r["urun_kod"],
                                         sel_r.get("urun_ad"), "manual")
                else:
                    st.caption("Sonuç bulunamadı")

        # ── Tamamlanan ──
        with q_done:
            if completed_prods:
                st.caption(f"{len(completed_prods)} ürün eşleştirildi")
                for _, cp in completed_prods[:50]:
                    st.markdown(f"~~`{cp['urun_kod']}`~~ {cp.get('urun_ad','')}")
                if len(completed_prods) > 50:
                    st.caption(f"... ve {len(completed_prods)-50} ürün daha")
            else:
                st.caption("Henüz eşleştirme yok")

        # ── Manuel ──
        with q_manual:
            code_in = st.text_input("Ürün Kodu:", key=f"hgmt_man_code_{event_id}")
            desc_in = st.text_input("Açıklama:", key=f"hgmt_man_desc_{event_id}")
            if st.button(
                "Kaydet",
                disabled=(not code_in or bbox is None),
                key=f"hgmt_man_save_{event_id}",
                use_container_width=True,
            ):
                _hgmt_save_local(event_id, page, bbox, code_in.strip(),
                                 desc_in.strip() or None, "manual")

    # ---- Hızlı eylemler: Kaydet + Undo + Toplu sil ----
    st.markdown("---")
    if st.session_state[keys["dirty"]]:
        pc = len(st.session_state[keys["pending_mappings"]])
        dc = len(st.session_state[keys["pending_deletes"]])
        uc = len(st.session_state[keys["pending_updates"]])
        parts = []
        if pc: parts.append(f"{pc} yeni")
        if dc: parts.append(f"{dc} silme")
        if uc: parts.append(f"{uc} güncelleme")
        text = ", ".join(parts)
        sc1, sc2 = st.columns([3, 5])
        with sc1:
            if st.button(
                f"Kaydet ({text})",
                type="primary",
                key=f"hgmt_flush_{event_id}",
                use_container_width=True,
            ):
                page_lookup = {(p["flyer_filename"], p["page_no"]): p["png_data"] for p in pages}
                try:
                    with st.spinner("Supabase'e yazılıyor…"):
                        _hgmt_flush_to_supabase(event_id, page_lookup)
                except Exception as e:
                    _hg_render_supabase_error(e, "Eşleştirmeler kaydedilemedi")
                else:
                    st.session_state.pop(cache_key, None)
                    st.success("Tüm değişiklikler kaydedildi!")
                    st.rerun()
        with sc2:
            st.caption("Kaydedilmemiş değişiklikleriniz var")

    uc1, uc2, _ = st.columns([2, 2, 4])
    with uc1:
        last_mid = st.session_state[keys["last_mapping_id"]]
        if last_mid is not None and st.button(
            "Geri Al (Son)",
            key=f"hgmt_undo_{event_id}",
            use_container_width=True,
        ):
            target = next((m for m in saved if m["mapping_id"] == last_mid), None)
            if last_mid < 0:
                st.session_state[keys["pending_mappings"]] = [
                    m for m in st.session_state[keys["pending_mappings"]]
                    if m["mapping_id"] != last_mid
                ]
            else:
                st.session_state[keys["pending_deletes"]].append(last_mid)
            st.session_state[keys["dirty"]] = True
            st.session_state[keys["last_mapping_id"]] = None
            st.rerun()
    with uc2:
        if saved and st.button(
            f"Tümünü Sil ({len(saved)})",
            key=f"hgmt_clear_{event_id}",
            use_container_width=True,
        ):
            st.session_state[f"_hgmt_confirm_clear_{event_id}_{page_id}"] = True
    if st.session_state.get(f"_hgmt_confirm_clear_{event_id}_{page_id}"):
        st.warning(f"Bu sayfadaki **{len(saved)}** eşleştirme silinecek!")
        yc1, yc2 = st.columns(2)
        with yc1:
            if st.button("Evet, Sil", type="primary", key=f"hgmt_clear_y_{event_id}", use_container_width=True):
                st.session_state[keys["pending_mappings"]] = [
                    m for m in st.session_state[keys["pending_mappings"]]
                    if not (m["flyer_filename"] == page["flyer_filename"]
                            and m["page_no"] == page["page_no"])
                ]
                for m in db_filtered:
                    st.session_state[keys["pending_deletes"]].append(m["mapping_id"])
                st.session_state[keys["dirty"]] = True
                st.session_state.pop(f"_hgmt_confirm_clear_{event_id}_{page_id}", None)
                st.rerun()
        with yc2:
            if st.button("İptal", key=f"hgmt_clear_n_{event_id}", use_container_width=True):
                st.session_state.pop(f"_hgmt_confirm_clear_{event_id}_{page_id}", None)
                st.rerun()

    # ---- Saved mappings selectbox + edit form ----
    if saved:
        with st.expander(f"Bu Sayfadaki Eşleştirmeler ({len(saved)})", expanded=False):
            mid_list = [m["mapping_id"] for m in saved]
            mid_to_m = {m["mapping_id"]: m for m in saved}
            mid_labels = {
                mid: (
                    f"{('*'+str(abs(mid))) if mid < 0 else ('#'+str(mid))}  "
                    f"{m.get('urun_kodu') or '?'} — {m.get('urun_aciklamasi') or ''}"
                )
                for mid, m in mid_to_m.items()
            }
            sel_mid = st.selectbox(
                "Eşleştirme seç:", mid_list,
                format_func=lambda m: mid_labels[m],
                key=f"hgmt_map_select_{event_id}",
            )
            sel_m = mid_to_m[sel_mid]
            is_pending = sel_mid < 0

            new_kod = st.text_input(
                "Kod", value=sel_m.get("urun_kodu") or "",
                key=f"hgmt_ek_{event_id}_{sel_mid}",
            )
            new_desc = st.text_input(
                "Açıklama", value=sel_m.get("urun_aciklamasi") or "",
                key=f"hgmt_ed_{event_id}_{sel_mid}",
            )
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("Güncelle", key=f"hgmt_eu_{event_id}", use_container_width=True):
                    if is_pending:
                        for pm in st.session_state[keys["pending_mappings"]]:
                            if pm["mapping_id"] == sel_mid:
                                pm["urun_kodu"] = new_kod.strip()
                                pm["urun_aciklamasi"] = new_desc.strip() or None
                                break
                    else:
                        st.session_state[keys["pending_updates"]][sel_mid] = {
                            "urun_kodu": new_kod.strip(),
                            "urun_aciklamasi": new_desc.strip() or None,
                        }
                    st.session_state[keys["dirty"]] = True
                    st.rerun()
            with ec2:
                if st.button("Sil", key=f"hgmt_edel_{event_id}", use_container_width=True):
                    if is_pending:
                        st.session_state[keys["pending_mappings"]] = [
                            pm for pm in st.session_state[keys["pending_mappings"]]
                            if pm["mapping_id"] != sel_mid
                        ]
                    else:
                        st.session_state[keys["pending_deletes"]].append(sel_mid)
                    st.session_state[keys["dirty"]] = True
                    st.rerun()


# ---------------------------------------------------------------------------
# ADMIN TAB: Halk Günü → Liste Modu
# ---------------------------------------------------------------------------

def _admin_halkgunu_list_mode(event_id: str, event_meta: dict | None):
    """Liste modu — Excel yükle + ürün resimleri tek/toplu yükle."""
    import halkgunu_storage as hgs

    event_label = (event_meta or {}).get("event_name") or event_id

    st.markdown(f"#### Liste Modu — {event_label}")
    st.caption("Excel'den indirimli ürün listesi yükle, eksik ürün resimlerini tek tek "
               "veya toplu yükle.")

    # =========================================================================
    # 1) EXCEL YÜKLEME
    # =========================================================================
    with st.expander("📄 Excel Yükle (indirim listesi)", expanded=False):
        st.caption(
            "Beklenen kolonlar: **ürün kodu**, ürün adı, **mağaza kodu**, "
            "normal fiyat, indirimli fiyat. (Kolon başlıkları büyük/küçük harf "
            "duyarsız, Türkçe karakter farketmez.)"
        )
        upload = st.file_uploader(
            "Excel dosyası (.xlsx)",
            type=["xlsx", "xls"],
            key=f"hg_xlsx_{event_id}",
        )
        if upload is not None:
            try:
                df = pd.read_excel(upload)
            except Exception as e:
                st.error(f"Excel okunamadı: {e}")
                df = None
            if df is not None and not df.empty:
                col_map = _hg_resolve_excel_columns(df.columns)
                missing_required = [k for k in ("urun_kod", "magaza_kod") if k not in col_map]
                if missing_required:
                    st.error(
                        "Zorunlu kolonlar eksik: "
                        + ", ".join(missing_required)
                        + ". Bulunan kolonlar: " + ", ".join(map(str, df.columns))
                    )
                else:
                    # Map to schema fields, keep only known
                    rename = {v: k for k, v in col_map.items()}
                    parsed = df.rename(columns=rename)[list(col_map.keys())].copy()
                    # Cast text columns to str for stable display
                    for c in ("urun_kod", "magaza_kod", "urun_ad", "magaza_ad"):
                        if c in parsed.columns:
                            parsed[c] = parsed[c].astype(str).str.strip()
                            parsed.loc[parsed[c] == "nan", c] = ""

                    st.markdown("**Önizleme** (ilk 20 satır)")
                    st.dataframe(parsed.head(20), use_container_width=True, hide_index=True)

                    unique_codes = sorted({c for c in parsed["urun_kod"].dropna().astype(str) if c.strip()})
                    img_check = hgs.check_product_images_for_codes(unique_codes)
                    have_count = sum(1 for v in img_check.values() if v)
                    missing_count = len(unique_codes) - have_count

                    pc1, pc2, pc3, pc4 = st.columns(4)
                    pc1.metric("Toplam satır", f"{len(parsed):,}")
                    pc2.metric("Benzersiz ürün", f"{parsed['urun_kod'].nunique():,}")
                    pc3.metric("Benzersiz mağaza", f"{parsed['magaza_kod'].nunique():,}")
                    pc4.metric("Görseli hazır", f"{have_count:,} / {len(unique_codes):,}")

                    if missing_count > 0:
                        st.info(
                            f"ℹ️ {have_count} ürünün görseli `product-images` bucket'ında zaten yüklü. "
                            f"Kalan {missing_count} ürün için afiş kırpma veya tek tek/toplu yükleme gerekir."
                        )
                    elif unique_codes:
                        st.success("🎉 Tüm ürünlerin görseli `product-images` bucket'ında hazır.")

                    if st.button(
                        "✅ Yükle (mevcut listeyi değiştirir)",
                        type="primary",
                        key=f"hg_xlsx_save_{event_id}",
                        use_container_width=True,
                    ):
                        rows = parsed.to_dict("records")
                        with st.spinner("Veritabanına yazılıyor…"):
                            inserted = hgs.save_event_products(event_id, rows)
                        st.success(
                            f"{inserted} satır yüklendi. "
                            f"{have_count}/{len(unique_codes)} ürünün görseli hazır."
                        )
                        st.rerun()

    # =========================================================================
    # 1.5) TEK ÜRÜN EKLE (manuel, listeyi sıfırlamadan)
    # =========================================================================
    with st.expander("➕ Ürün Ekle (manuel — listeyi sıfırlamaz)", expanded=False):
        magazalar_list = hgs.list_magazalar()
        magaza_options = [m["magaza_kod"] for m in magazalar_list]
        magaza_label = {
            m["magaza_kod"]: f"{m['magaza_kod']} — {m.get('magaza_adi') or m['magaza_kod']}"
            for m in magazalar_list
        }

        with st.form(key=f"hg_add_product_form_{event_id}", clear_on_submit=True):
            ac1, ac2 = st.columns([1, 2])
            with ac1:
                add_urun_kod = st.text_input("Ürün Kodu *", key=f"hg_add_kod_{event_id}")
            with ac2:
                add_urun_ad = st.text_input("Ürün Adı", key=f"hg_add_ad_{event_id}")

            add_magazalar = st.multiselect(
                "Mağaza(lar) *",
                magaza_options,
                format_func=lambda k: magaza_label.get(k, k),
                key=f"hg_add_magazalar_{event_id}",
                help="Birden fazla mağaza seçersen her mağaza için ayrı satır eklenir.",
            )

            ac3, ac4 = st.columns(2)
            with ac3:
                add_normal = st.text_input(
                    "Normal Fiyat", key=f"hg_add_normal_{event_id}", placeholder="örn. 125",
                )
            with ac4:
                add_indirimli = st.text_input(
                    "İndirimli Fiyat", key=f"hg_add_indirimli_{event_id}", placeholder="örn. 95",
                )

            submitted = st.form_submit_button("✅ Ekle", type="primary", use_container_width=True)
            if submitted:
                kod = (add_urun_kod or "").strip()
                if not kod:
                    st.error("Ürün kodu zorunlu.")
                elif not add_magazalar:
                    st.error("En az bir mağaza seçmelisin.")
                else:
                    new_rows = [
                        {
                            "urun_kod": kod,
                            "urun_ad": add_urun_ad,
                            "magaza_kod": m,
                            "normal_fiyat": add_normal,
                            "indirimli_fiyat": add_indirimli,
                        }
                        for m in add_magazalar
                    ]
                    res = hgs.add_event_products(event_id, new_rows)
                    msg = f"{res['inserted']} satır eklendi"
                    if res["skipped"]:
                        msg += f" · {res['skipped']} satır zaten mevcuttu (atlandı)"
                    st.success(msg)
                    st.rerun()

    # =========================================================================
    # 2) ÜRÜN ÖZET TABLOSU
    # =========================================================================
    summary = hgs.get_event_product_summary(event_id)
    if not summary:
        st.info("Bu etkinlik için henüz ürün yüklenmemiş.")
        return

    img_status = hgs.list_event_product_image_status(event_id)
    missing_codes: list[str] = [s["urun_kod"] for s in summary if not img_status.get(s["urun_kod"], False)]

    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Ürün", f"{len(summary):,}")
    sc2.metric("Resimli", f"{len(summary) - len(missing_codes):,}")
    sc3.metric("Resimsiz", f"{len(missing_codes):,}")

    # =========================================================================
    # 3) ÜRÜN LİSTESİ — satır bazlı yükle/güncelle/sil
    # =========================================================================
    st.markdown("**Ürün Listesi** — her satırın yanından resim yükle / güncelle / sil")

    fc1, fc2, fc3 = st.columns([2, 1, 1])
    with fc1:
        search_q = st.text_input(
            "🔍 Ara (kod veya ad)", key=f"hg_row_search_{event_id}",
            placeholder="örn. 11001808 veya patates",
        ).strip().lower()
    with fc2:
        only_missing = st.checkbox(
            "Sadece resimsizler", value=bool(missing_codes),
            key=f"hg_row_only_missing_{event_id}",
        )
    with fc3:
        page_size = st.selectbox(
            "Sayfa boyutu", [10, 20, 50, 100], index=1,
            key=f"hg_row_page_size_{event_id}",
        )

    # Sort: missing first, then by code
    ordered = sorted(
        summary,
        key=lambda s: (img_status.get(s["urun_kod"], False), s["urun_kod"]),
    )

    if only_missing:
        ordered = [s for s in ordered if not img_status.get(s["urun_kod"], False)]
    if search_q:
        ordered = [
            s for s in ordered
            if search_q in s["urun_kod"].lower() or search_q in (s.get("urun_ad") or "").lower()
        ]

    total_filtered = len(ordered)
    if total_filtered == 0:
        st.info("Filtreyle eşleşen ürün yok.")
    else:
        page_key = f"hg_row_page_{event_id}"
        if page_key not in st.session_state:
            st.session_state[page_key] = 1
        total_pages = max(1, (total_filtered + page_size - 1) // page_size)
        # clamp page after filter changes
        st.session_state[page_key] = max(1, min(st.session_state[page_key], total_pages))

        page = st.session_state[page_key]
        start = (page - 1) * page_size
        end = start + page_size
        page_items = ordered[start:end]

        st.caption(f"Sayfa {page} / {total_pages} · Toplam {total_filtered} ürün")

        for s in page_items:
            kod = s["urun_kod"]
            ad = s.get("urun_ad") or "—"
            has = img_status.get(kod, False)

            with st.container(border=True):
                cols = st.columns([0.6, 3, 2.4, 0.8])

                with cols[0]:
                    if has:
                        st.image(hgs.get_event_product_image_url(kod), width=64)
                    else:
                        st.markdown("❌")

                with cols[1]:
                    icon = "✅" if has else "❌"
                    st.markdown(f"**{icon} {kod}**")
                    st.caption(ad)
                    if s.get("min_indirimli") is not None:
                        st.caption(
                            f"Normal: {s.get('max_normal') or '—'} · "
                            f"İndirimli: {s.get('min_indirimli')}"
                        )

                with cols[2]:
                    f = st.file_uploader(
                        "Yükle/Güncelle",
                        type=_HG_PRODUCT_IMG_EXTS,
                        key=f"hg_row_up_{event_id}_{kod}",
                        label_visibility="collapsed",
                    )
                    if f is not None:
                        try:
                            jpeg = _hg_image_to_jpeg(f.getvalue(), filename=f.name)
                            hgs.upload_event_product_image(kod, jpeg)
                            st.success(f"{kod} resmi {'güncellendi' if has else 'yüklendi'}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"{kod}: {e}")

                with cols[3]:
                    if has:
                        confirm_key = f"hg_row_del_confirm_{event_id}_{kod}"
                        if st.session_state.get(confirm_key):
                            if st.button("✓ Onayla", key=f"hg_row_del_yes_{event_id}_{kod}",
                                         type="primary", use_container_width=True):
                                hgs.delete_event_product_image(kod)
                                st.session_state.pop(confirm_key, None)
                                st.success(f"{kod} resmi silindi.")
                                st.rerun()
                            if st.button("İptal", key=f"hg_row_del_no_{event_id}_{kod}",
                                         use_container_width=True):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                        else:
                            if st.button("🗑️ Sil", key=f"hg_row_del_{event_id}_{kod}",
                                         use_container_width=True,
                                         help="Bu ürünün resmini bucket'tan kaldır"):
                                st.session_state[confirm_key] = True
                                st.rerun()

        # Pagination controls
        if total_pages > 1:
            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("◀ Önceki", disabled=(page <= 1),
                             key=f"hg_row_prev_{event_id}", use_container_width=True):
                    st.session_state[page_key] -= 1
                    st.rerun()
            with nav2:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px'>{page} / {total_pages}</div>",
                    unsafe_allow_html=True,
                )
            with nav3:
                if st.button("Sonraki ▶", disabled=(page >= total_pages),
                             key=f"hg_row_next_{event_id}", use_container_width=True):
                    st.session_state[page_key] += 1
                    st.rerun()

    # =========================================================================
    # 4) RESİM YÜKLEME — TOPLU
    # =========================================================================
    with st.expander("📦 Toplu Resim Yükle", expanded=False):
        st.caption(
            "Dosya adı **ürün kodu** olmalı (örn: `12345.jpg`, `12345.png`). "
            "Listede olmayan kodlar atlanır."
        )
        bulk = st.file_uploader(
            "Birden çok dosya seçin (JPG/PNG/WEBP/TIFF/BMP/GIF/PDF)",
            type=_HG_PRODUCT_IMG_EXTS,
            accept_multiple_files=True,
            key=f"hg_img_bulk_{event_id}",
        )
        if bulk:
            valid_codes = {s["urun_kod"] for s in summary}
            ext_strip = re.compile(
                r"\.(" + "|".join(_HG_PRODUCT_IMG_EXTS) + r")$", re.I,
            )
            preview_rows = []
            for f in bulk:
                stem = ext_strip.sub("", f.name).strip()
                in_list = stem in valid_codes
                already = img_status.get(stem, False)
                preview_rows.append({
                    "Dosya": f.name,
                    "Ürün Kodu": stem,
                    "Listede": "✅" if in_list else "❌",
                    "Mevcut": "Var (üzerine yazılır)" if already else "—",
                })
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

            if st.button(
                f"✅ {len(bulk)} dosyayı yükle",
                type="primary",
                key=f"hg_img_bulk_save_{event_id}",
                use_container_width=True,
            ):
                done, skipped, errors = 0, 0, 0
                progress = st.progress(0)
                for i, f in enumerate(bulk):
                    stem = ext_strip.sub("", f.name).strip()
                    if stem not in valid_codes:
                        skipped += 1
                    else:
                        try:
                            jpeg_bytes = _hg_image_to_jpeg(f.getvalue(), filename=f.name)
                            hgs.upload_event_product_image(stem, jpeg_bytes)
                            done += 1
                        except Exception as e:
                            log.warning("Halk Günü bulk upload (%s): %s", f.name, e)
                            errors += 1
                    progress.progress((i + 1) / len(bulk))
                st.success(f"{done} yüklendi · {skipped} atlandı · {errors} hata")
                st.rerun()


_HG_PRODUCT_IMG_EXTS = ["jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp", "gif", "pdf"]


def _hg_image_to_jpeg(raw_bytes: bytes, quality: int = 88,
                      filename: str | None = None) -> bytes:
    """Convert an uploaded file (image or PDF) to JPEG bytes for the product bucket.

    Accepted: jpg/jpeg/png/webp/tif(f)/bmp/gif (via Pillow) and pdf (PyMuPDF, first page).
    PyMuPDF is also used as a fallback for TIFF/JP2 variants Pillow can't decode.
    """
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    if not raw_bytes:
        raise ValueError("Boş dosya")

    head = raw_bytes[:1024]
    name_lower = (filename or "").lower()
    is_pdf = b"%PDF" in head or name_lower.endswith(".pdf")

    img = None
    if is_pdf:
        from pdf_render import render_pdf_bytes_to_pages
        pages = render_pdf_bytes_to_pages(raw_bytes, zoom=2.0, jpeg_quality=quality)
        if not pages:
            raise ValueError("PDF render edilemedi (sayfa yok).")
        img = Image.open(BytesIO(pages[0]["png_bytes"]))
        img.load()
    else:
        try:
            img = Image.open(BytesIO(raw_bytes))
            img.load()
        except (UnidentifiedImageError, OSError) as pil_err:
            # Fallback: PyMuPDF supports many image formats Pillow doesn't
            # (or fails on due to compression variants — common with TIFF).
            try:
                import fitz
                ext = name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""
                doc = fitz.open(stream=raw_bytes, filetype=ext or None)
                if doc.page_count == 0:
                    raise ValueError("Dosya boş")
                pix = doc[0].get_pixmap(alpha=False, dpi=200)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                doc.close()
            except Exception as fitz_err:
                sig = head[:12].hex()
                raise ValueError(
                    f"Dosya formatı tanınamadı (uzantı: .{ext or '?'}, ilk byte: {sig}). "
                    f"Pillow: {pil_err.__class__.__name__}; PyMuPDF: {fitz_err.__class__.__name__}. "
                    "Desteklenen: JPG/PNG/WEBP/TIFF/BMP/GIF/PDF. "
                    "HEIC/HEIF/AVIF/SVG ise lütfen JPG/PNG'ye çevirip tekrar yükleyin."
                ) from None

    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    out = BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()

    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    out = BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------------------
# ADMIN TAB: Halk Günü → Bizden Fotoğraflar (halkgunu_photos)
# ---------------------------------------------------------------------------

_HG_PHOTO_NO_STORE = "__none__"


def _admin_halkgunu_photos(event_id: str, event_meta: dict | None):
    """Mağaza ziyaretlerinde çekilen fotoğraflar — yükle/listele/düzenle/sil."""
    import halkgunu_storage as hgs

    event_label = (event_meta or {}).get("event_name") or event_id

    st.markdown(f"#### Bizden Fotoğraflar — {event_label}")
    st.caption(
        "halkgunu.net üzerindeki yeşil **Bizden Fotoğraflar** sekmesini besler. "
        "Mağaza seçimi opsiyoneldir; mağaza seçilmezse foto sadece görsel + caption "
        "olarak görünür. Sekme yalnızca bu etkinlikte en az bir foto varken kullanıcılara açılır."
    )
    if (event_meta or {}).get("status") != "active":
        st.warning(
            "⚠️ Bu etkinlik henüz **yayında değil**. Foto yükleyebilirsin ama "
            "halkgunu.net'te ancak etkinlik 'Yayında' olduğunda görünür."
        )

    magazalar = hgs.list_magazalar()
    magaza_label = {m["magaza_kod"]: f"{m['magaza_kod']} — {m.get('magaza_adi') or m['magaza_kod']}"
                    for m in magazalar}
    magaza_options = [_HG_PHOTO_NO_STORE] + [m["magaza_kod"] for m in magazalar]

    def _fmt_magaza(opt: str) -> str:
        return "(mağaza yok)" if opt == _HG_PHOTO_NO_STORE else magaza_label.get(opt, opt)

    # =========================================================================
    # 1) YENİ FOTOĞRAF YÜKLE
    # =========================================================================
    with st.expander("➕ Yeni Fotoğraf Yükle", expanded=True):
        files = st.file_uploader(
            "Fotoğraflar (.jpg / .jpeg / .png) — birden fazla seçebilirsin",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"hg_photo_uploader_{event_id}",
        )
        uc1, uc2 = st.columns([3, 1])
        with uc1:
            sel_magaza = st.selectbox(
                "Mağaza (opsiyonel)",
                magaza_options,
                index=0,
                format_func=_fmt_magaza,
                key=f"hg_photo_new_magaza_{event_id}",
            )
        with uc2:
            sort_raw = st.text_input(
                "Sıra (boşsa sona eklenir)",
                value="",
                key=f"hg_photo_new_sort_{event_id}",
                placeholder="auto",
            )
        caption = st.text_input(
            "Caption (opsiyonel — tüm yüklenen dosyalara aynı metin)",
            value="",
            key=f"hg_photo_new_caption_{event_id}",
        )

        if files:
            st.caption(f"Yüklenecek: {len(files)} dosya")
            if st.button(
                f"✅ {len(files)} fotoğrafı yükle",
                type="primary",
                key=f"hg_photo_save_{event_id}",
                use_container_width=True,
            ):
                magaza_val = None if sel_magaza == _HG_PHOTO_NO_STORE else sel_magaza
                base_sort: int | None = None
                if sort_raw.strip().lstrip("-").isdigit():
                    base_sort = int(sort_raw.strip())
                done, errors = 0, 0
                progress = st.progress(0)
                for i, f in enumerate(files):
                    try:
                        raw = f.getvalue()
                        # Always normalize to JPEG to keep bucket consistent and small
                        jpeg = _hg_image_to_jpeg(raw)
                        path = hgs._hg_photo_path(event_id, f.name)
                        # Ensure .jpg extension since we re-encoded
                        if not path.endswith(".jpg"):
                            path = path.rsplit(".", 1)[0] + ".jpg"
                        ok = hgs._hg_upload_photo(path, jpeg, content_type="image/jpeg")
                        if not ok:
                            errors += 1
                            continue
                        sort_for_row = (base_sort + i) if base_sort is not None else None
                        hgs.save_photo(
                            event_id=event_id,
                            image_path=path,
                            magaza_kod=magaza_val,
                            caption=(caption or None),
                            sort_order=sort_for_row,
                        )
                        done += 1
                    except Exception as e:
                        log.warning("Halk Günü photo upload (%s): %s", f.name, e)
                        errors += 1
                    progress.progress((i + 1) / len(files))
                if done:
                    st.success(f"{done} foto yüklendi" + (f" · {errors} hata" if errors else ""))
                else:
                    st.error(f"Yükleme başarısız ({errors} hata).")
                st.rerun()

    # =========================================================================
    # 2) MEVCUT FOTOĞRAFLAR
    # =========================================================================
    photos = hgs.list_event_photos(event_id)

    pc1, pc2 = st.columns(2)
    pc1.metric("Toplam foto", f"{len(photos):,}")
    pc2.metric("Mağaza atamalı", f"{sum(1 for p in photos if p.get('magaza_kod')):,}")

    if not photos:
        st.info("Henüz foto yok. Yukarıdan ilk fotoğrafları yükle.")
        return

    st.markdown("**Mevcut Fotoğraflar**")
    st.caption("Her satırda mağaza/caption/sıra düzenlenip 'Kaydet' ile gönderilir. "
               "Silme işlemi DB satırını ve storage'daki dosyayı kaldırır.")

    for p in photos:
        pid = p["id"]
        url = hgs.get_photo_public_url(p.get("image_path") or "")
        with st.container(border=True):
            ic1, ic2 = st.columns([1, 3])
            with ic1:
                if url:
                    st.image(url, use_container_width=True)
                else:
                    st.caption("(görsel yok)")
                st.caption(f"ID: {pid}")
            with ic2:
                cur_magaza = p.get("magaza_kod") or _HG_PHOTO_NO_STORE
                if cur_magaza != _HG_PHOTO_NO_STORE and cur_magaza not in magaza_label:
                    # Eski/silinmiş mağaza referansı — yine de seçenekler arasında göster
                    magaza_options_row = magaza_options + [cur_magaza]
                else:
                    magaza_options_row = magaza_options
                idx = magaza_options_row.index(cur_magaza) if cur_magaza in magaza_options_row else 0
                new_magaza = st.selectbox(
                    "Mağaza",
                    magaza_options_row,
                    index=idx,
                    format_func=_fmt_magaza,
                    key=f"hg_photo_magaza_{pid}",
                )
                new_caption = st.text_input(
                    "Caption",
                    value=p.get("caption") or "",
                    key=f"hg_photo_caption_{pid}",
                )
                new_sort = st.number_input(
                    "Sıra",
                    value=int(p.get("sort_order") or 0),
                    step=1,
                    key=f"hg_photo_sort_{pid}",
                )

                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("Kaydet", key=f"hg_photo_upd_{pid}",
                                 type="primary", use_container_width=True):
                        magaza_val = None if new_magaza == _HG_PHOTO_NO_STORE else new_magaza
                        hgs.update_photo(pid, {
                            "magaza_kod": magaza_val,
                            "caption": new_caption.strip() or None,
                            "sort_order": int(new_sort),
                        })
                        st.success("Güncellendi.")
                        st.rerun()
                with bc2:
                    if st.button("Sil", key=f"hg_photo_del_{pid}",
                                 use_container_width=True):
                        st.session_state[f"_confirm_del_hgphoto_{pid}"] = True

            if st.session_state.get(f"_confirm_del_hgphoto_{pid}"):
                st.warning("Foto silinecek (DB + storage).")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("Evet, Sil", key=f"hg_photo_cdel_y_{pid}",
                                 type="primary", use_container_width=True):
                        hgs.delete_photo(pid, also_storage=True)
                        st.session_state.pop(f"_confirm_del_hgphoto_{pid}", None)
                        st.rerun()
                with dc2:
                    if st.button("İptal", key=f"hg_photo_cdel_n_{pid}",
                                 use_container_width=True):
                        st.session_state.pop(f"_confirm_del_hgphoto_{pid}", None)
                        st.rerun()


# ---------------------------------------------------------------------------
# ADMIN TAB: Analitikler (mevcut arama log paneli)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _fetch_analytics_data(baslangic: str):
    """Fetch analytics data with 5-min cache to avoid re-querying on every rerun."""
    client = get_supabase_client()
    if not client:
        return []
    all_data = []
    page_size = 1000
    offset = 0
    while True:
        result = client.table('arama_log')\
            .select('*')\
            .gte('tarih', baslangic)\
            .order('id', desc=True)\
            .range(offset, offset + page_size - 1)\
            .execute()
        if not result.data:
            break
        all_data.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return all_data


def _admin_tab_analytics(df_to_xlsx):
    """Arama analitikleri sekmesi."""
    st.subheader("Arama Analitikleri")

    client = get_supabase_client()
    if not client:
        st.error("Veritabanı bağlantısı yok")
        return

    gun_sayisi = st.selectbox("Dönem:", [7, 14, 30], format_func=lambda x: f"Son {x} gün")

    try:
        today = datetime.now().strftime('%Y-%m-%d')
        baslangic = (datetime.now() - timedelta(days=gun_sayisi)).strftime('%Y-%m-%d')

        all_data = _fetch_analytics_data(baslangic)

        if not all_data:
            st.warning("Henüz veri yok")
            return

        df = pd.DataFrame(all_data)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Toplam Arama", f"{df['arama_sayisi'].sum():,}")
        with col2:
            st.metric("Benzersiz Terim", f"{len(df['arama_terimi'].unique()):,}")
        with col3:
            sonucsuz = df[df['sonuc_sayisi'] == 0]['arama_sayisi'].sum()
            st.metric("Sonuçsuz", f"{sonucsuz:,}")

        st.markdown("---")

        # ---- EN ÇOK ARANANLAR ----
        st.subheader("En Çok Arananlar")
        top_full = df.groupby('arama_terimi').agg(
            {'arama_sayisi': 'sum', 'sonuc_sayisi': 'last'}
        ).reset_index()
        top_full = top_full.sort_values('arama_sayisi', ascending=False)
        top_full.columns = ['Terim', 'Arama', 'Sonuç']

        st.dataframe(top_full.head(20), use_container_width=True, hide_index=True)

        st.download_button(
            "Tümünü İndir (xlsx)",
            data=df_to_xlsx(top_full),
            file_name=f"en_cok_arananlar_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_top"
        )

        # ---- SONUÇ BULUNAMAYANLAR ----
        st.subheader("Sonuç Bulunamayanlar")
        sonucsuz_full = df[df['sonuc_sayisi'] == 0].groupby('arama_terimi').agg(
            {'arama_sayisi': 'sum'}
        ).reset_index()
        sonucsuz_full = sonucsuz_full.sort_values('arama_sayisi', ascending=False)
        sonucsuz_full.columns = ['Terim', 'Arama']

        if sonucsuz_full.empty:
            st.success("Tüm aramalarda sonuç bulunmuş!")
        else:
            st.dataframe(sonucsuz_full.head(20), use_container_width=True, hide_index=True)

            st.download_button(
                "Tümünü İndir (xlsx)",
                data=df_to_xlsx(sonucsuz_full),
                file_name=f"sonucsuz_aramalar_{today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_sonucsuz"
            )

        # ---- BUGÜN ARANANLAR ----
        st.subheader("Bugün Arananlar")
        bugun = datetime.now().strftime('%Y-%m-%d')
        bugun_full = df[df['tarih'] == bugun].copy()

        if bugun_full.empty:
            st.info("Bugün henüz arama yapılmamış")
        else:
            sort_col = 'son_arama_zamani' if 'son_arama_zamani' in bugun_full.columns else 'id'
            bugun_full = bugun_full.sort_values(sort_col, ascending=False)
            bugun_show = bugun_full[['arama_terimi', 'arama_sayisi', 'sonuc_sayisi']].copy()
            bugun_show.columns = ['Terim', 'Arama', 'Sonuç']

            st.dataframe(bugun_show.head(50), use_container_width=True, hide_index=True)

            st.download_button(
                "Tümünü İndir (xlsx)",
                data=df_to_xlsx(bugun_show),
                file_name=f"bugun_aramalar_{today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_bugun"
            )

    except Exception as e:
        st.error(f"Hata: {e}")


# ---------------------------------------------------------------------------
# ADMIN TAB 2: Afiş Yükle & İşle
# ---------------------------------------------------------------------------

def _admin_tab_poster_upload():
    """Haftalık Excel + çoklu PDF yükle, toplu eşleştir."""
    from poster.db import upsert_poster, get_poster_items as _get_items
    from poster.excel_import import read_excel
    from poster.match import process_single_poster
    from poster.hotspot_gen import get_pdf_page_count

    st.subheader("Dosya Yükleme")
    st.caption("Excel'i bir kez, PDF'leri toplu yükleyin. Her PDF otomatik eşleştirilir.")

    week_date = st.date_input("Hafta Tarihi", value=datetime.now(), key="pu_date")

    col_excel, col_pdf = st.columns(2)
    with col_excel:
        excel_file = st.file_uploader(
            "Excel Ürün Listesi (tüm afişler)",
            type=["xlsx", "xls"],
            key="pu_excel",
        )
    with col_pdf:
        pdf_files = st.file_uploader(
            "PDF Afişler (çoklu seçim)",
            type=["pdf"],
            accept_multiple_files=True,
            key="pu_pdfs",
        )

    if not excel_file:
        st.info("Haftalık Excel dosyasını yükleyin.")
        return
    if not pdf_files:
        st.info("En az bir PDF afiş yükleyin.")
        return

    st.markdown(f"**{len(pdf_files)} PDF** yüklendi.")

    if st.button(
        f"Tümünü İşle ({len(pdf_files)} afiş)",
        type="primary",
        use_container_width=True,
        key="pu_run",
    ):
        # 1. Excel'i bir kez oku (bellekte tut)
        try:
            excel_df = read_excel(excel_file)
        except Exception as e:
            st.error(f"Excel okuma hatası: {e}")
            return

        st.success(f"Excel okundu: {len(excel_df)} satır")

        # 2. Her PDF için sırayla işle
        progress = st.progress(0, text="Başlanıyor...")
        total_matched = 0
        total_review = 0
        total_hotspots = 0
        all_orphans: dict[str, list[str]] = {}  # poster_name → orphan_needles

        for i, pdf_file in enumerate(pdf_files):
            pdf_name = pdf_file.name.replace(".pdf", "").replace(".PDF", "")
            progress.progress(
                (i) / len(pdf_files),
                text=f"İşleniyor: {pdf_name} ({i+1}/{len(pdf_files)})",
            )

            pdf_bytes = pdf_file.read()
            page_count = get_pdf_page_count(pdf_bytes)

            # Poster kaydı oluştur
            pdf_url = _upload_pdf_to_storage(pdf_bytes, pdf_name, str(week_date))
            poster_id = upsert_poster(
                title=pdf_name,
                week_date=str(week_date),
                pdf_url=pdf_url,
                page_count=page_count,
            )
            if not poster_id:
                st.error(f"Afiş kaydedilemedi: {pdf_name}")
                continue

            # PDF bytes'ı session_state'e cache'le (viewer için fallback)
            if "pdf_cache" not in st.session_state:
                st.session_state["pdf_cache"] = {}
            st.session_state["pdf_cache"][poster_id] = pdf_bytes

            # Tam pipeline (needle → skorla → batch insert → hotspot)
            result = process_single_poster(poster_id, pdf_bytes, excel_df)

            total_matched += result["items_inserted"]
            total_review += result["review"]
            total_hotspots += result["hotspots_found"]

            # Orphan needle'ları topla
            if result.get("orphan_needles"):
                all_orphans[pdf_name] = result["orphan_needles"]

            # Sonucu göster
            orphan_count = len(result.get("orphan_needles", []))
            with st.expander(
                f"{pdf_name} — {result['items_inserted']} eklendi, "
                f"{result['hotspots_found']} hotspot"
                + (f", {orphan_count} KAYIP" if orphan_count else ""),
                expanded=(orphan_count > 0),
            ):
                items = _get_items(poster_id)
                if items:
                    st.markdown("**Eşleşen ürünler:**")
                    for it in items:
                        kod = it.get("urun_kodu") or "-"
                        aciklama = (it.get("urun_aciklamasi") or "")[:60]
                        conf = int((it.get("match_confidence") or 0) * 100)
                        st.markdown(f"- `{kod}` — {aciklama} (%{conf})")

                if result.get("orphan_needles"):
                    st.markdown("**PDF'de var ama Excel'de eşleşmedi (KAYIP):**")
                    for needle in result["orphan_needles"]:
                        st.markdown(f"- `{needle}` — Excel'de karşılığı yok!")

            st.session_state["last_poster_id"] = poster_id

        progress.progress(1.0, text="Tamamlandı!")

        # Özet
        total_orphans = sum(len(v) for v in all_orphans.values())
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Afişler", len(pdf_files))
        col2.metric("Eşleşen", total_matched)
        col3.metric("Hotspot", total_hotspots)
        col4.metric("Kayıp Ürün", total_orphans, delta_color="inverse")

        # Kayıp ürünlerin toplu raporu
        if all_orphans:
            st.markdown("---")
            st.warning(
                f"{total_orphans} ürün PDF'lerde görünüyor ama Excel listesinde "
                f"eşleşmedi. Bunları Excel'de kontrol edin."
            )
            for poster_name, orphans in all_orphans.items():
                st.markdown(f"**{poster_name}:** {', '.join(f'`{o}`' for o in orphans)}")
        else:
            st.balloons()


def _upload_pdf_to_storage(pdf_bytes: bytes, title: str, week_date: str) -> str:
    """PDF'i Supabase Storage'a yükle, public URL döndür."""
    from poster.db import get_supabase
    import logging

    client = get_supabase()
    if not client:
        logging.warning("PDF upload: Supabase client yok")
        return ""

    bucket = "posters"
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
    file_path = f"{week_date}/{safe_title}.pdf"

    try:
        # Önce mevcut dosyayı silmeyi dene (upsert için)
        try:
            client.storage.from_(bucket).remove([file_path])
        except Exception:
            pass

        client.storage.from_(bucket).upload(
            file_path,
            pdf_bytes,
            file_options={"content-type": "application/pdf"},
        )
        url = client.storage.from_(bucket).get_public_url(file_path)
        logging.info(f"PDF upload OK: {file_path} → {url}")
        return url
    except Exception as e:
        logging.error(f"PDF upload hatası: {e}")
        return ""


# ---------------------------------------------------------------------------
# ADMIN TAB 3: Afiş İncele & Düzelt
# ---------------------------------------------------------------------------

def _admin_tab_poster_review():
    """Hafta bazlı birleşik eşleşme inceleme ekranı."""
    from poster.db import get_posters, get_poster_items, update_poster_item, upsert_hotspot

    st.subheader("Hafta Seç")

    posters = get_posters(limit=50)
    if not posters:
        st.info("Henüz afiş yok.")
        return

    # Haftaları grupla
    weeks: dict[str, list[dict]] = {}
    for p in posters:
        wd = p.get("week_date") or "Tarihsiz"
        weeks.setdefault(wd, []).append(p)

    week_labels = list(weeks.keys())
    selected_week = st.selectbox("Hafta", week_labels, key="pr_week_select")
    week_posters = weeks[selected_week]

    st.markdown(f"**{selected_week}** — {len(week_posters)} afiş")

    # Tüm afişlerin ürünlerini topla
    all_items: list[dict] = []
    items_by_poster: dict[str, list[dict]] = {}
    for p in week_posters:
        pid = p["poster_id"]
        ptitle = p.get("title", f"Afiş {pid}")
        items = get_poster_items(pid)
        for it in items:
            it["_poster_title"] = ptitle
        all_items.extend(items)
        items_by_poster[ptitle] = items

    if not all_items:
        st.info("Bu haftada ürün yok.")
        return

    # Toplam durum özeti
    count_by_status: dict[str, int] = {}
    for it in all_items:
        s = it.get("status") or "pending"
        count_by_status[s] = count_by_status.get(s, 0) + 1

    cols = st.columns(4)
    cols[0].metric("Eşleşen", count_by_status.get("matched", 0))
    cols[1].metric("İncelenmeli", count_by_status.get("review", 0))
    cols[2].metric("Eşleşmedi", count_by_status.get("unmatched", 0))
    cols[3].metric("Toplam", len(all_items))

    st.markdown("---")

    # Görünüm seçimi
    view_mode = st.radio(
        "Görünüm",
        ["Afiş bazlı", "Tüm ürünler (birleşik)"],
        horizontal=True,
        key="pr_view_mode",
    )

    filter_status = st.multiselect(
        "Durum Filtresi",
        ["matched", "review", "unmatched", "pending"],
        default=["matched", "review", "unmatched", "pending"],
        key="pr_status_filter",
    )

    if view_mode == "Afiş bazlı":
        for ptitle, items in items_by_poster.items():
            filtered = [it for it in items if it.get("status") in filter_status]
            if not filtered:
                continue
            matched_c = sum(1 for it in filtered if it.get("status") == "matched")
            with st.expander(
                f"{ptitle} — {matched_c}/{len(filtered)} eşleşti",
                expanded=(matched_c < len(filtered)),
            ):
                for item in filtered:
                    _render_review_card(item)
    else:
        filtered = [it for it in all_items if it.get("status") in filter_status]
        if not filtered:
            st.info("Filtreye uyan kayıt yok.")
            return
        st.markdown(f"**{len(filtered)} ürün listeleniyor**")
        for item in filtered:
            _render_review_card(item)


def _render_review_card(item: dict):
    """Tek bir ürün inceleme kartını çiz."""
    from poster.db import update_poster_item, upsert_hotspot

    item_id = item["id"]
    urun_kodu = item.get("urun_kodu") or "-"
    urun_aciklamasi = item.get("urun_aciklamasi") or "-"
    afis_fiyat = item.get("afis_fiyat") or "-"
    status = item.get("status") or "pending"
    match_sku = item.get("match_sku_id") or ""
    search_term = item.get("search_term") or ""
    confidence = item.get("match_confidence") or 0
    page_no = item.get("page_no") or "-"

    status_icon = {"matched": "++", "review": "!!", "unmatched": "XX", "pending": ".."}
    icon = status_icon.get(status, "..")

    with st.expander(
        f"[{icon}] {urun_kodu} – {urun_aciklamasi[:50]} "
        f"[{status.upper()} %{int(confidence*100)}]",
        expanded=(status != "matched"),
    ):
        col_info, col_edit = st.columns([1, 1])

        with col_info:
            st.markdown(f"""
- **Ürün Kodu:** {urun_kodu}
- **Açıklama:** {urun_aciklamasi}
- **Fiyat:** {afis_fiyat}
- **Sayfa:** {page_no}
- **Eşleşen SKU:** {match_sku or '—'}
- **Arama Terimi:** {search_term or '—'}
- **Güven:** %{int(confidence*100)}
            """)

        with col_edit:
            st.markdown("**Manuel Düzeltme:**")

            new_sku = st.text_input(
                "Doğru Ürün Kodu (SKU)",
                value=match_sku,
                key=f"pr_sku_{item_id}",
            )
            new_search = st.text_input(
                "Arama Terimi",
                value=search_term,
                key=f"pr_search_{item_id}",
            )
            new_price = st.text_input(
                "Afiş Fiyatı",
                value=afis_fiyat if afis_fiyat != "-" else "",
                key=f"pr_price_{item_id}",
            )

            st.markdown("**Hotspot (opsiyonel):**")
            hs_cols = st.columns(4)
            hs_x0 = hs_cols[0].number_input("x0", 0.0, 1.0, 0.0, 0.01, key=f"pr_hx0_{item_id}")
            hs_y0 = hs_cols[1].number_input("y0", 0.0, 1.0, 0.0, 0.01, key=f"pr_hy0_{item_id}")
            hs_x1 = hs_cols[2].number_input("x1", 0.0, 1.0, 0.0, 0.01, key=f"pr_hx1_{item_id}")
            hs_y1 = hs_cols[3].number_input("y1", 0.0, 1.0, 0.0, 0.01, key=f"pr_hy1_{item_id}")

            hs_page = st.number_input(
                "Hotspot Sayfa No",
                min_value=1, max_value=20,
                value=int(page_no) if page_no != "-" else 1,
                key=f"pr_hpage_{item_id}",
            )

            if st.button("Kaydet", key=f"pr_save_{item_id}", type="primary"):
                updates = {}
                if new_sku and new_sku != match_sku:
                    updates["match_sku_id"] = new_sku
                    updates["search_term"] = new_sku
                    updates["match_confidence"] = 1.0
                    updates["status"] = "matched"
                if new_search and new_search != search_term:
                    updates["search_term"] = new_search
                if new_price:
                    updates["afis_fiyat"] = new_price
                if not updates and new_sku:
                    updates["status"] = "matched"
                    updates["match_confidence"] = 1.0

                if updates:
                    update_poster_item(item_id, updates)
                    st.success("Ürün güncellendi!")

                if hs_x1 > hs_x0 and hs_y1 > hs_y0:
                    upsert_hotspot(
                        poster_item_id=item_id,
                        page_no=hs_page,
                        x0=hs_x0, y0=hs_y0, x1=hs_x1, y1=hs_y1,
                        source="manual",
                        updated_by="admin",
                    )
                    st.success("Hotspot kaydedildi!")

                st.rerun()


# ---------------------------------------------------------------------------
# ADMIN TAB 4: Afiş Görüntüle (hotspot önizleme)
# ---------------------------------------------------------------------------

def _admin_tab_poster_view():
    """Afiş sayfasını hotspot'larla birlikte önizle."""
    import base64
    import streamlit.components.v1 as components
    from poster.db import get_posters, get_hotspots_for_page
    from poster.hotspot_gen import render_page_image

    st.subheader("Afiş Önizleme")

    posters = get_posters(limit=20)
    if not posters:
        st.info("Henüz afiş yok.")
        return

    last_pid = st.session_state.get("last_poster_id")
    poster_options = {f"{p['title']} ({p['week_date']})": p for p in posters}
    labels = list(poster_options.keys())

    default_idx = 0
    if last_pid:
        for i, p in enumerate(posters):
            if p["poster_id"] == last_pid:
                default_idx = i
                break

    selected_label = st.selectbox("Afiş", labels, index=default_idx, key="pv_poster_select")
    poster = poster_options[selected_label]
    poster_id = poster["poster_id"]
    page_count = poster.get("page_count", 1) or 1

    if page_count > 1:
        page_no = st.slider("Sayfa", 1, page_count, 1, key="pv_page")
    else:
        page_no = 1

    # PDF'i al: önce session cache, sonra URL'den indir
    pdf_cache = st.session_state.get("pdf_cache", {})
    pdf_bytes = pdf_cache.get(poster_id)

    if not pdf_bytes:
        pdf_url = poster.get("pdf_url", "")
        if pdf_url:
            pdf_bytes = _fetch_pdf_bytes_cached(pdf_url)

    if not pdf_bytes:
        st.warning(
            "PDF bulunamadı. Afiş Yükleme sekmesinden tekrar yükleyin. "
            "(Yükleme sonrası aynı oturumda görüntüleyebilirsiniz.)"
        )
        return

    # Sayfayı render et
    try:
        png_bytes = render_page_image(pdf_bytes, page_no, dpi=150)
    except Exception:
        logging.exception("render_page_image failed")
        st.error("Sayfa görüntülenemedi. Lütfen kısa süre sonra tekrar deneyin.")
        return

    # Hotspot'ları getir
    hotspots = get_hotspots_for_page(poster_id, page_no)

    if not hotspots:
        st.warning("Bu sayfada hotspot yok.")
        st.image(png_bytes, use_container_width=True)
        return

    # HTML overlay ile göster
    img_b64 = base64.b64encode(png_bytes).decode()
    hotspot_divs = []
    for hs in hotspots:
        x0 = hs.get("x0", 0) * 100
        y0 = hs.get("y0", 0) * 100
        w = (hs.get("x1", 0) - hs.get("x0", 0)) * 100
        h = (hs.get("y1", 0) - hs.get("y0", 0)) * 100

        urun_aciklamasi = hs.get("urun_aciklamasi", "") or ""
        afis_fiyat = hs.get("afis_fiyat", "") or ""
        tooltip = urun_aciklamasi[:60]
        if afis_fiyat:
            tooltip += f" - {afis_fiyat}"

        hotspot_divs.append(f"""
        <div class="hotspot" title="{tooltip}" style="
            left:{x0:.2f}%; top:{y0:.2f}%; width:{w:.2f}%; height:{h:.2f}%;
        "></div>
        """)

    html = f"""
    <!DOCTYPE html><html><head><style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    .poster-wrap {{ position:relative; display:inline-block; width:100%; line-height:0; }}
    .poster-wrap img {{ width:100%; height:auto; display:block; }}
    .hotspot {{
        position:absolute;
        border:2px solid rgba(102,126,234,0.6);
        border-radius:8px;
        background:rgba(102,126,234,0.1);
        cursor:pointer;
        transition:all .2s;
    }}
    .hotspot:hover {{
        background:rgba(102,126,234,0.3);
        border-color:rgba(102,126,234,1);
        box-shadow:0 0 12px rgba(102,126,234,0.5);
    }}
    </style></head><body>
    <div class="poster-wrap">
        <img src="data:image/png;base64,{img_b64}" alt="Poster" />
        {"".join(hotspot_divs)}
    </div>
    </body></html>
    """
    components.html(html, height=1200, scrolling=True)
    st.caption(f"{len(hotspots)} hotspot mevcut. Üzerine gelin / dokunun.")


@st.cache_data(ttl=300)
def _fetch_pdf_bytes_cached(pdf_url: str):
    """PDF'i URL'den indir (5dk cache)."""
    if not pdf_url:
        return None
    try:
        import httpx
        resp = httpx.get(pdf_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    params = st.query_params

    if params.get("admin") == "true":
        admin_panel()
    elif params.get("mode") == "flyer" or params.get("pick_region") or params.get("pick_cluster"):
        # Mağaza personeli: afiş görüntüleyici (Price-Anchored v3)
        from flyer.viewer import viewer_page
        viewer_page()
    elif params.get("mode") == "poster" or params.get("pick"):
        # Eski afiş görüntüleyici (PDF-based, legacy)
        from poster.viewer import poster_viewer_page
        poster_viewer_page()
    else:
        main()
