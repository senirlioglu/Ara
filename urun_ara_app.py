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
from datetime import datetime, timedelta
from typing import Optional
from PIL import Image
import threading
from pathlib import Path

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
    .stApp { background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%); }
    header[data-testid="stHeader"] { background: transparent; }
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 1rem;
        border-radius: 0 0 20px 20px;
        margin: -1rem -1rem 1.5rem -1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 { color: white !important; font-size: 1.8rem !important; font-weight: 700 !important; margin: 0 !important; }
    .main-header p { color: rgba(255,255,255,0.85); font-size: 0.9rem; margin: 0.5rem 0 0 0; }
    .search-container { background: white; padding: 1rem; border-radius: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); margin-bottom: 1rem; }
    .stTextInput > div > div > input { border-radius: 12px !important; border: 2px solid #e0e0e0 !important; padding: 0.75rem 1rem !important; font-size: 1rem !important; }
    .stTextInput > div > div > input:focus { border-color: #667eea !important; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important; }

    /* Button styling (Ara butonu - orijinal boyut) */
    .stButton > button { border-radius: 12px !important; padding: 0.75rem 1.5rem !important; font-weight: 600 !important; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; border: none !important; }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important; }

    /* Pill satırları: 3+ kolonlu yatay bloklar kaydırılabilir olsun */
    [data-testid="stHorizontalBlock"]:has(> :nth-child(3)) {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
        -ms-overflow-style: none;
        gap: 4px !important;
        padding-bottom: 4px;
    }
    [data-testid="stHorizontalBlock"]:has(> :nth-child(3))::-webkit-scrollbar { display: none; }
    [data-testid="stHorizontalBlock"]:has(> :nth-child(3)) > [data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: fit-content !important;
    }
    /* Pill satırlarındaki butonlar küçük pill olsun */
    [data-testid="stHorizontalBlock"]:has(> :nth-child(3)) .stButton > button {
        background: #f0f1f6 !important;
        color: #555 !important;
        border: 1px solid #e0e2ea !important;
        border-radius: 20px !important;
        padding: 0.4rem 1rem !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        white-space: nowrap !important;
        min-height: unset !important;
        line-height: 1.4 !important;
    }
    [data-testid="stHorizontalBlock"]:has(> :nth-child(3)) .stButton > button:hover {
        background: #e4e5f0 !important;
        border-color: #667eea !important;
        color: #667eea !important;
        transform: none !important;
        box-shadow: none !important;
    }

    .popular-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #333;
        margin: 0.8rem 0 0.3rem 0.2rem;
    }

    .info-card { background: white; padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.85rem; color: #666; text-align: center; margin-bottom: 1rem; }
    .streamlit-expanderHeader { background: white !important; border-radius: 12px !important; border: none !important; box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important; padding: 0.75rem 1rem !important; font-weight: 500 !important; }
    .streamlit-expanderContent { background: white !important; border-radius: 0 0 12px 12px !important; border: none !important; padding: 0.5rem !important; }

    /* Poster butonları - pill stili */
    .stExpander [data-testid="stHorizontalBlock"] .stButton > button {
        background: linear-gradient(135deg, #667eea22, #764ba222) !important;
        color: #667eea !important;
        border: 1px solid #667eea44 !important;
        border-radius: 20px !important;
        padding: 0.4rem 1rem !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
    }
    .stExpander [data-testid="stHorizontalBlock"] .stButton > button:hover {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        transform: none !important;
    }

    @media (max-width: 768px) {
        .block-container { padding: 0.5rem !important; }
        [data-testid="stHorizontalBlock"]:has(> :nth-child(3)) .stButton > button {
            padding: 0.35rem 0.75rem !important;
            font-size: 0.8rem !important;
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
                    parts = entry.split(' - ', 1)
                    kod = parts[0].strip()
                    ad = parts[1].strip()
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
                st.error(f"Beklenmeyen Hata: {e}")

        # Hata kontrolü (result nesnesi üzerinden)
        if 'result' in locals() and getattr(result, 'error', None):
            err_msg = str(result.error)
            if not ("timeout" in err_msg.lower() or "57014" in err_msg):
                st.error(f"Arama hatası (RPC): {result.error}")

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

    except Exception as e:
        st.error(f"Beklenmeyen Hata: {e}")
        return None


def log_arama(arama_terimi: str, sonuc_sayisi: int):
    """Arama logla (sessiz çalışır)"""
    try:
        client = get_supabase_client()
        if client and arama_terimi:
            terim = arama_terimi.strip().lower()[:100]
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
    except:
        pass


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
            # Saf ürün kodlarını filtrele (kullanıcıya anlamsız)
            terimler = [r['arama_terimi'] for r in result.data
                        if not r['arama_terimi'].strip().isdigit()]
            return list(dict.fromkeys(terimler))[:10]
    except:
        pass
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
    """Cached wrapper"""
    liste, _ = _get_oneri_listesi_impl()
    return liste



# ============================================================================
# AFİŞ SİSTEMİ - Tıklanabilir Ürün Alanları
# ============================================================================

@st.cache_data(ttl=600)
def get_poster_list():
    """Aktif afişleri yükle"""
    try:
        poster_path = Path('data/posters.json')
        if poster_path.exists():
            with poster_path.open('r', encoding='utf-8') as f:
                posters = json.load(f)
            return [p for p in posters if p.get('active', True)]
    except Exception:
        pass
    return []


def render_poster_viewer(poster):
    """
    Afiş'i tıklanabilir ürün alanları ile interaktif göster.
    Ürüne tıklayınca arama inputuna yazar ve formu gönderir.
    """
    import base64
    import streamlit.components.v1 as components

    image_src = poster.get('image', '')

    # Lokal dosya ise base64'e çevir
    if image_src and not image_src.startswith(('http://', 'https://', 'data:')):
        local_path = Path(image_src)
        if local_path.exists():
            with open(local_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode()
            ext = local_path.suffix.lower().lstrip('.')
            mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
            image_src = f'data:{mime};base64,{img_data}'
        else:
            image_src = ''

    products = poster.get('products', [])
    has_coords = products and any('x_percent' in p for p in products)

    # Eğer resim yoksa çık
    if not image_src:
        return

    # Yeni format: koordinatsız afişler - sadece resmi göster
    if not has_coords:
        poster_html = f'''
        <div style="width:100%; border-radius:12px; overflow:hidden; box-shadow:0 4px 15px rgba(0,0,0,0.1);">
            <img src="{image_src}" style="width:100%; display:block; border-radius:12px;" />
        </div>
        '''
        components.html(poster_html, height=520, scrolling=True)
        return

    # Eski format: koordinatlı hotspot'lar
    if not products:
        return

    # Hotspot HTML oluştur
    hotspots_html = ''
    for p in products:
        label_esc = html.escape(p.get('label', p['search_query']))
        query_esc = html.escape(p['search_query'])
        hotspots_html += f'''
        <div class="poster-hotspot"
             data-search="{query_esc}"
             style="
                position: absolute;
                left: {p['x_percent']}%;
                top: {p['y_percent']}%;
                width: {p['width_percent']}%;
                height: {p['height_percent']}%;
                cursor: pointer;
                border: 2px dashed rgba(102,126,234,0.4);
                border-radius: 8px;
                transition: all 0.25s ease;
                z-index: 10;
                display: flex;
                align-items: flex-end;
                justify-content: center;
             ">
            <div class="hotspot-label" style="
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                padding: 3px 10px;
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
                white-space: nowrap;
                margin-bottom: 4px;
                opacity: 0.7;
                transition: opacity 0.25s, transform 0.25s;
                pointer-events: none;
            ">{label_esc}</div>
        </div>'''

    poster_html = f'''
    <style>
        .poster-hotspot:hover {{
            border-color: #667eea !important;
            background: rgba(102,126,234,0.12) !important;
            box-shadow: 0 0 12px rgba(102,126,234,0.3);
        }}
        .poster-hotspot:hover .hotspot-label {{
            opacity: 1 !important;
            transform: scale(1.05);
        }}
        .poster-hotspot:active {{
            background: rgba(102,126,234,0.25) !important;
        }}
    </style>
    <div id="poster-container" style="
        position: relative;
        display: inline-block;
        width: 100%;
        border-radius: 12px;
        overflow: visible;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    ">
        <img src="{image_src}" style="width:100%; display:block; border-radius:12px;" />
        {hotspots_html}
    </div>
    <script>
    (function() {{
        try {{
            var pd = window.parent.document;
            var hotspots = document.querySelectorAll('.poster-hotspot');

            hotspots.forEach(function(el) {{
                el.addEventListener('click', function() {{
                    var query = this.getAttribute('data-search');
                    if (!query) return;

                    // Arama input'una değer yaz (autocomplete ile aynı teknik)
                    var inp = pd.querySelector('input[placeholder*="Ürün kodu"]');
                    if (inp) {{
                        var setter = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype, 'value'
                        ).set;
                        setter.call(inp, query);
                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}

                    // Form submit butonunu tıkla
                    setTimeout(function() {{
                        var submitBtn = pd.querySelector(
                            '[data-testid="stFormSubmitButton"] button'
                        );
                        if (submitBtn) {{
                            submitBtn.click();
                            // Sayfanın üstüne scroll
                            setTimeout(function() {{
                                pd.querySelector('[data-testid="stAppViewContainer"]')
                                    .scrollTo({{top: 0, behavior: 'smooth'}});
                            }}, 200);
                        }}
                    }}, 150);
                }});
            }});
        }} catch(e) {{}}
    }})();
    </script>
    '''

    # Poster yüksekliğini resim oranına göre ayarla (mobil uyumlu)
    components.html(poster_html, height=520, scrolling=False)


def render_poster_section():
    """Ana sayfada afiş bölümünü göster"""
    posters = get_poster_list()
    if not posters:
        return

    st.markdown(
        '<div class="popular-title" style="margin-top:0.5rem;">📋 Aktüel Afişler</div>',
        unsafe_allow_html=True
    )

    # Birden fazla afiş varsa tab ile göster
    if len(posters) == 1:
        poster = posters[0]
        with st.expander(f"📌 {poster.get('title', 'Afiş')}", expanded=False):
            render_poster_viewer(poster)
            # Ürün listesini buton olarak da göster (erişilebilirlik)
            products = poster.get('products', [])
            if products:
                st.markdown(
                    '<div style="font-size:0.82rem;color:#888;margin:8px 0 4px;">Ürüne tıklayarak arayın:</div>',
                    unsafe_allow_html=True
                )
                btn_cols = st.columns(min(len(products), 4))
                for i, p in enumerate(products):
                    col_idx = i % min(len(products), 4)
                    if btn_cols[col_idx].button(
                        p.get('label', p['search_query']),
                        key=f"poster_{poster['id']}_{i}",
                        use_container_width=True
                    ):
                        st.session_state.arama_input = p['search_query']
                        st.session_state._poster_arama = p['search_query']
    else:
        for poster in posters:
            with st.expander(f"📌 {poster.get('title', 'Afiş')}", expanded=False):
                render_poster_viewer(poster)
                products = poster.get('products', [])
                if products:
                    st.markdown(
                        '<div style="font-size:0.82rem;color:#888;margin:8px 0 4px;">Ürüne tıklayarak arayın:</div>',
                        unsafe_allow_html=True
                    )
                    btn_cols = st.columns(min(len(products), 4))
                    for i, p in enumerate(products):
                        col_idx = i % min(len(products), 4)
                        if btn_cols[col_idx].button(
                            p.get('label', p['search_query']),
                            key=f"poster_{poster['id']}_{i}",
                            use_container_width=True
                        ):
                            st.session_state.arama_input = p['search_query']
                            st.session_state._poster_arama = p['search_query']


# ============================================================================
# AFİŞ YÖNETİMİ - Ürün Tespiti ve Eşleştirme
# ============================================================================

@st.cache_data(ttl=3600)
def load_urun_master_df():
    """Ürün master verisini DataFrame olarak yükle (parquet > json)"""
    try:
        p = Path('data/urun_master.parquet')
        if p.exists():
            return pd.read_parquet(p)
    except Exception:
        pass
    try:
        p = Path('data/urun_master.json')
        if p.exists():
            with p.open('r', encoding='utf-8') as f:
                data = json.load(f)
            return pd.DataFrame(data)
    except Exception:
        pass
    return pd.DataFrame()


def parse_poster_text(raw_text):
    """
    Afiş metninden ürün adayı terimleri çıkar.
    Model numaraları, ürün kodları ve ürün isimlerini tespit eder.
    """
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

    # Skip patterns (marketing, disclaimers)
    skip_re = re.compile(
        r'(^\*\s*(kampanya|yasal|ürün stok|bu afiş)|'
        r'peşin fiyatına|taksit|0850\s|444\s|'
        r'kampanya kazanımı|detaylar\s|www\.|\.com\.tr|'
        r'kredi kart|banka\s|ekstre|hadi\s)',
        re.IGNORECASE
    )

    # Model number pattern (alphanumeric with optional dashes)
    model_re = re.compile(r'\b([A-Za-z]+[\-]?[0-9]+[A-Za-z0-9\-]*)\b')

    # Price pattern
    price_re = re.compile(r'^\d{1,3}(\.\d{3})*(,\d+)?\s*(TL)?$')

    # Product category/brand keywords
    product_kw = [
        'tv', 'telefon', 'tablet', 'laptop', 'klima', 'buzdolabi', 'camasir',
        'bulasik', 'supurge', 'ampul', 'hoparlor', 'hoparlör', 'kulaklik',
        'kulaklık', 'klavye', 'mouse', 'gimbal', 'bluetooth', 'samsung',
        'philips', 'vestel', 'arcelik', 'arçelik', 'beko', 'led', 'qled',
        'oled', 'smart', 'android', 'whale', 'galaxy', 'iphone', 'xiaomi',
        'robot', 'ütü', 'utu', 'fırın', 'firin', 'ocak', 'aspiratör',
        'pil', 'şarj', 'sarj', 'kablo', 'adaptör', 'monitor', 'kamera',
        'drone', 'termos', 'vantilatör', 'saat', 'kulaklık', 'hoparlör',
        'deterjan', 'mama', 'bezi', 'kahve', 'nescafe', 'çay', 'cay',
    ]

    candidates = []

    for line in lines:
        if skip_re.search(line):
            continue
        if len(line) < 3:
            continue
        if price_re.match(line.strip()):
            continue
        if re.match(r'^[\d\.\,\s\"\'\*°]+$', line):
            continue

        # Model numbers in line
        models = model_re.findall(line)
        for m in models:
            if len(m) >= 5 and any(c.isdigit() for c in m) and any(c.isalpha() for c in m):
                candidates.append(m.upper())

        # Product name lines
        line_norm = temizle_ve_kok_bul(line)
        if any(kw in line_norm for kw in product_kw):
            clean = re.sub(r'[\*\•\■\●]', '', line).strip()
            if clean and 3 < len(clean) < 100:
                candidates.append(clean)

    # Deduplicate
    seen = set()
    unique = []
    for c in candidates:
        key = temizle_ve_kok_bul(c)
        if key not in seen and len(key) > 2:
            seen.add(key)
            unique.append(c)

    return unique


def search_urun_master_local(query, urun_df):
    """urun_master DataFrame'de ürün ara. En iyi eşleşmeleri döndür."""
    if urun_df.empty or not query:
        return []

    query_norm = temizle_ve_kok_bul(query)
    if not query_norm or len(query_norm) < 2:
        return []

    results = []

    # 1. Exact code match
    mask = urun_df['urun_kod'] == query_norm
    for _, row in urun_df[mask].iterrows():
        results.append({'urun_kod': row['urun_kod'], 'urun_ad': row['urun_ad'], 'score': 1000})
    if results:
        return results[:5]

    # 2. Full query as substring in product name
    mask = urun_df['urun_ad_normalized'].str.contains(query_norm, na=False, regex=False)
    matched = urun_df[mask]
    for _, row in matched.head(10).iterrows():
        s = 500 if query_norm == row['urun_ad_normalized'] else 400
        results.append({'urun_kod': row['urun_kod'], 'urun_ad': row['urun_ad'], 'score': s})
    if results:
        return sorted(results, key=lambda x: -x['score'])[:5]

    # 3. All words match
    words = [w for w in query_norm.split() if len(w) > 1]
    if words and len(words) <= 8:
        mask = urun_df['urun_ad_normalized'].apply(
            lambda x: all(w in str(x) for w in words) if pd.notna(x) else False
        )
        for _, row in urun_df[mask].head(10).iterrows():
            results.append({'urun_kod': row['urun_kod'], 'urun_ad': row['urun_ad'], 'score': 200})
    if results:
        return sorted(results, key=lambda x: -x['score'])[:5]

    # 4. Any word matches (longest word first for precision)
    words_sorted = sorted([w for w in query_norm.split() if len(w) > 2], key=len, reverse=True)
    for word in words_sorted[:3]:
        mask = urun_df['urun_ad_normalized'].str.contains(word, na=False, regex=False)
        for _, row in urun_df[mask].head(5).iterrows():
            results.append({'urun_kod': row['urun_kod'], 'urun_ad': row['urun_ad'], 'score': 50})
        if results:
            break

    return sorted(results, key=lambda x: -x['score'])[:5]


def admin_poster_yonetimi():
    """Afiş oluşturma ve yönetim arayüzü"""
    st.subheader("Afiş Yönetimi")

    urun_df = load_urun_master_df()
    if urun_df.empty:
        st.error("Ürün master verisi yüklenemedi!")
        return

    tab_yeni, tab_mevcut = st.tabs(["Yeni Afiş", "Mevcut Afişler"])

    with tab_yeni:
        st.markdown("#### Yeni Afiş Oluştur")

        afis_baslik = st.text_input("Afiş Başlığı:", placeholder="Örn: Aktüel Ürünler - 27 Şubat")
        afis_resim = st.file_uploader("Afiş Resmi (opsiyonel):", type=['jpg', 'jpeg', 'png', 'webp'])

        st.markdown("---")
        st.markdown("#### Ürün Tespiti")

        input_method = st.radio(
            "Giriş yöntemi:",
            ["Metin Yapıştır (PDF'ten kopyala)", "Excel Yükle", "Manuel Giriş"],
            horizontal=True
        )

        search_terms = []

        if input_method.startswith("Metin"):
            poster_text = st.text_area(
                "Afiş metnini yapıştırın:",
                height=200,
                placeholder="PDF'ten kopyaladığınız ürün bilgilerini buraya yapıştırın...",
                key="poster_text_input"
            )

            if st.button("Ürünleri Tespit Et", type="primary", key="btn_detect") and poster_text:
                candidates = parse_poster_text(poster_text)
                if candidates:
                    st.session_state['poster_candidates'] = candidates
                    st.info(f"{len(candidates)} aday terim tespit edildi. Eşleştirme yapılıyor...")
                else:
                    st.warning("Metinden ürün adayı tespit edilemedi. Manuel giriş deneyin.")

        elif input_method.startswith("Excel"):
            excel_file = st.file_uploader("Excel dosyası:", type=['xlsx', 'xls'], key="poster_excel")
            if excel_file:
                try:
                    excel_df = pd.read_excel(excel_file)
                    st.dataframe(excel_df.head(10), use_container_width=True)
                    col_options = list(excel_df.columns)
                    match_col = st.selectbox("Eşleşme için sütun:", col_options)
                    if st.button("Ürünleri Eşleştir", type="primary", key="btn_excel_match"):
                        terms = excel_df[match_col].dropna().astype(str).tolist()
                        st.session_state['poster_candidates'] = [t.strip() for t in terms if t.strip()]
                except Exception as e:
                    st.error(f"Excel okuma hatası: {e}")

        else:  # Manuel giriş
            manual_text = st.text_area(
                "Ürün isimlerini/kodlarını alt alta yazın:",
                height=150,
                placeholder="WHALE TV\nGALAXY A16\nBluetooth Hoparlör\n...",
                key="poster_manual_input"
            )
            if st.button("Ara", type="primary", key="btn_manual_match") and manual_text:
                terms = [l.strip() for l in manual_text.split('\n') if l.strip()]
                st.session_state['poster_candidates'] = terms

        # === Eşleştirme ve İnceleme ===
        if 'poster_candidates' in st.session_state and st.session_state['poster_candidates']:
            candidates = st.session_state['poster_candidates']

            # Eşleştirme yap (cache results in session)
            if 'poster_match_results' not in st.session_state or st.session_state.get('_candidates_changed'):
                all_matches = []
                for candidate in candidates:
                    matches = search_urun_master_local(candidate, urun_df)
                    all_matches.append({
                        'search_term': candidate,
                        'matches': matches
                    })
                st.session_state['poster_match_results'] = all_matches
                st.session_state['_candidates_changed'] = False

            match_results = st.session_state['poster_match_results']
            found_count = sum(1 for r in match_results if r['matches'])

            st.markdown("---")
            st.markdown(f"#### Eşleşme Sonuçları ({found_count}/{len(match_results)} eşleşme)")
            st.markdown("Doğru eşleşmeleri isaretleyin, yanlışları düzenleyin:")

            selected_products = []

            for i, result in enumerate(match_results):
                term = result['search_term']
                matches = result['matches']

                if matches:
                    best = matches[0]
                    with st.container():
                        col_check, col_info, col_edit = st.columns([0.08, 0.55, 0.37])
                        with col_check:
                            checked = st.checkbox("", key=f"sel_{i}", value=True)
                        with col_info:
                            st.markdown(f"**{term}**")
                            if len(matches) > 1:
                                options = [f"[{m['urun_kod']}] {m['urun_ad']}" for m in matches]
                                selected_idx = st.selectbox(
                                    "Eşleşme:",
                                    range(len(options)),
                                    format_func=lambda x: options[x],
                                    key=f"match_select_{i}",
                                    label_visibility="collapsed"
                                )
                                best = matches[selected_idx]
                            else:
                                st.caption(f"[{best['urun_kod']}] {best['urun_ad']}")
                        with col_edit:
                            custom_label = st.text_input(
                                "Buton etiketi:",
                                value=best['urun_ad'][:50],
                                key=f"label_{i}",
                                label_visibility="collapsed"
                            )

                        if checked:
                            selected_products.append({
                                'label': custom_label,
                                'search_query': best['urun_ad'],
                                'urun_kod': best['urun_kod']
                            })
                else:
                    st.markdown(f"~~{term}~~ - *eşleşme bulunamadı*")

            # Manuel ürün ekleme
            st.markdown("---")
            st.markdown("#### Eksik Ürün Ekle")
            extra_query = st.text_input("Ürün ara:", placeholder="Ürün adı veya kodu...", key="extra_product")
            if extra_query and len(extra_query) >= 2:
                extra_results = search_urun_master_local(extra_query, urun_df)
                if extra_results:
                    for j, m in enumerate(extra_results[:5]):
                        c1, c2 = st.columns([0.08, 0.92])
                        with c1:
                            if st.checkbox("", key=f"extra_{j}"):
                                selected_products.append({
                                    'label': m['urun_ad'][:50],
                                    'search_query': m['urun_ad'],
                                    'urun_kod': m['urun_kod']
                                })
                        with c2:
                            st.caption(f"[{m['urun_kod']}] {m['urun_ad']}")
                else:
                    st.caption("Sonuç bulunamadı")

            # Kaydet
            st.markdown("---")
            st.info(f"Seçili ürün: **{len(selected_products)}**")

            if st.button("Afişi Kaydet", type="primary", key="btn_save_poster"):
                if not selected_products:
                    st.error("En az 1 ürün seçin!")
                else:
                    # Save poster image
                    image_path = ""
                    if afis_resim:
                        poster_dir = Path('data/posters')
                        poster_dir.mkdir(parents=True, exist_ok=True)
                        ext = afis_resim.name.rsplit('.', 1)[-1] if '.' in afis_resim.name else 'jpg'
                        fname = f"afis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                        image_path = f"data/posters/{fname}"
                        with open(image_path, 'wb') as f:
                            f.write(afis_resim.getbuffer())

                    new_poster = {
                        'id': f"afis_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        'title': afis_baslik or f"Afiş - {datetime.now().strftime('%d.%m.%Y')}",
                        'image': image_path,
                        'active': True,
                        'products': selected_products
                    }

                    # Load existing & append
                    poster_path = Path('data/posters.json')
                    posters = []
                    if poster_path.exists():
                        try:
                            with poster_path.open('r', encoding='utf-8') as f:
                                posters = json.load(f)
                        except Exception:
                            pass

                    posters.append(new_poster)

                    with poster_path.open('w', encoding='utf-8') as f:
                        json.dump(posters, f, ensure_ascii=False, indent=2)

                    get_poster_list.clear()

                    # Temizle
                    for key in ['poster_candidates', 'poster_match_results', '_candidates_changed']:
                        st.session_state.pop(key, None)

                    st.success(f"Afiş kaydedildi! {len(selected_products)} ürün eklendi.")
                    st.rerun()

    with tab_mevcut:
        st.markdown("#### Mevcut Afişler")
        poster_path = Path('data/posters.json')
        posters = []
        if poster_path.exists():
            try:
                with poster_path.open('r', encoding='utf-8') as f:
                    posters = json.load(f)
            except Exception:
                pass

        if not posters:
            st.info("Henüz afiş eklenmemiş.")
        else:
            for i, poster in enumerate(posters):
                aktif = poster.get('active', True)
                title = poster.get('title', 'Afiş')
                urun_sayisi = len(poster.get('products', []))
                icon = "ON" if aktif else "OFF"

                with st.expander(f"[{icon}] {title} ({urun_sayisi} ürün)"):
                    new_active = st.checkbox(
                        "Aktif", value=aktif, key=f"active_{i}"
                    )

                    for j, p in enumerate(poster.get('products', [])):
                        kod = p.get('urun_kod', '')
                        st.text(f"  {j+1}. [{kod}] {p['label']}")

                    col_del, col_toggle = st.columns(2)
                    with col_del:
                        if st.button("Sil", key=f"del_{i}"):
                            posters.pop(i)
                            with poster_path.open('w', encoding='utf-8') as f:
                                json.dump(posters, f, ensure_ascii=False, indent=2)
                            get_poster_list.clear()
                            st.rerun()

                    if new_active != aktif:
                        posters[i]['active'] = new_active
                        with poster_path.open('w', encoding='utf-8') as f:
                            json.dump(posters, f, ensure_ascii=False, indent=2)
                        get_poster_list.clear()


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
        urun_kod = urun['urun_kod']
        urun_ad = urun['urun_ad'] if urun['urun_ad'] else urun_kod
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
                st.markdown(f'<div style="margin-bottom:12px;">{badges_html}</div>', unsafe_allow_html=True)
            if urun_df_stoklu.empty:
                st.error("Bu ürün hiçbir mağazada stokta yok!")
            else:
                html_cards = []
                for _, row in urun_df_stoklu.iterrows():
                    try:
                        seviye, _, renk = get_stok_seviye(row['stok_adet'])
                    except:
                        seviye, renk = "Normal", "#3498db"

                    magaza_ad = html.escape(str(row['magaza_ad'] or row['magaza_kod']))

                    # Güvenli Veri Çekme
                    sm = html.escape(str(row.get('sm_kod') or "-"))
                    bs = html.escape(str(row.get('bs_kod') or "-"))
                    magaza_kod = html.escape(str(row.get('magaza_kod') or "-"))
                    seviye_escaped = html.escape(str(seviye))

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
                st.markdown("".join(html_cards), unsafe_allow_html=True)


# ============================================================================
# ANA UYGULAMA
# ============================================================================

def main():
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Ürün Ara</h1>
        <p>Hangi mağazada ürün var? Hızlıca öğren!</p>
    </div>
    """, unsafe_allow_html=True)

    client = get_supabase_client()
    if not client:
        st.error("⚠️ Veritabanı bağlantısı kurulamadı.")
        st.info("Lütfen ayarları kontrol edin.")
        return

    # Arama kutusu (form ile - her tuşta DB çağrısı yok, sadece Enter/buton)
    with st.form("arama_form", clear_on_submit=False):
        col1, col2 = st.columns([5, 1])
        with col1:
            arama_text = st.text_input(
                "Arama",
                placeholder="Ürün kodu veya adı yazın (örn: kedi mama, tv 55)...",
                label_visibility="collapsed",
                key="arama_input"
            )
        with col2:
            ara_btn = st.form_submit_button("🔍 Ara", use_container_width=True, type="primary")

    # Autocomplete önerileri (client-side, performans dostu)
    oneriler = get_oneri_listesi()
    if oneriler:
        import json
        import streamlit.components.v1 as components
        _ac_data = json.dumps(oneriler, ensure_ascii=False)
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
  var sep=t.indexOf(' - ');
  var ad=(sep>-1 ? t.slice(sep+3).trim() : t.trim());
  var kod=(sep>-1 ? t.slice(0,sep).trim() : '');
  // Input'a ürün adını yaz (kullanıcı kodu görmesin)
  var st=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
  st.call(inp,ad);
  // Seçilen kodu gizli attribute'ta sakla
  inp.setAttribute('data-selected-kod', kod);
  inp.dispatchEvent(new Event('input',{bubbles:true}));
  setTimeout(function(){inp.dispatchEvent(new Event('change',{bubbles:true}));inp.blur();},50);
  dd.style.display='none';
});

function esc(s){return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');}
function norm(s){
  var map={'İ':'i','I':'i','ı':'i','Ğ':'g','ğ':'g','Ü':'u','ü':'u','Ş':'s','ş':'s','Ö':'o','ö':'o','Ç':'c','ç':'c'};
  var out='';
  for(var i=0;i<s.length;i++){out+=map[s[i]]||s[i];}
  if(out.normalize){out=out.normalize('NFD').replace(/[\u0300-\u036f]/g,'');}
  return out.toLowerCase().replace(/\s+/g,' ').trim();
}

var IDX=S.map(function(raw){
  var sep=raw.indexOf(' - ');
  var kod=sep>-1?raw.slice(0,sep):'';
  var ad=sep>-1?raw.slice(sep+3):raw;
  var nKod=norm(kod);
  var nAd=norm(ad);
  return {raw:raw,kod:kod,ad:ad,nKod:nKod,nAd:nAd};
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

    // Kısa sorgularda (ke/ac gibi) gürültüyü azalt:
    // sadece kelime başlangıcı eşleşmelerini göster.
    if(!isShort && ad.indexOf(q)!==-1) return 560;

    if(kod && kod.indexOf(q)===0) return isShort ? 280 : 320;
    if(!isShort && kod && kod.indexOf(q)!==-1) return 180;

    // Kısa sorguda alakasız ortadan-eşleşmeleri bastır.
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
    if(sc>0){m.push({s:it.raw,sc:sc});}
  }
  m.sort(function(a,b){return b.sc-a.sc || a.s.length-b.s.length;});
  m=m.slice(0,12).map(function(x){return x.s;});
  if(!m.length){dd.style.display='none';return;}
  dd.innerHTML=m.map(function(s){
    var sep=s.indexOf(' - ');
    var kod=(sep>-1 ? s.slice(0,sep).trim() : '');
    var ad=(sep>-1 ? s.slice(sep+3).trim() : s);
    var label=(kod ? '<span style="color:#999;font-size:0.8rem;min-width:68px;">'+esc(kod)+'</span><span style="color:#999;padding:0 4px;">-</span><span style="color:#333;font-size:0.92rem;">'+esc(ad)+'</span>' : '<span style="color:#333;font-size:0.92rem;">'+esc(s)+'</span>');
    return '<div data-t="'+esc(s)+'" style="padding:10px 16px;cursor:pointer;display:flex;align-items:center;gap:12px;border-bottom:1px solid #f5f5f5;transition:background 0.15s;" onmouseover="this.style.background=\\'#f5f5fa\\'" onmouseout="this.style.background=\\'white\\'">'
    +'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#999" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
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
        st.session_state.arama_input = term
        st.session_state._pop_arama = term

    populer = get_populer_terimler()

    if populer:
        st.markdown('<div class="popular-title">🔥 Popüler Aramalar</div>', unsafe_allow_html=True)
        cols_pop = st.columns(len(populer))
        for i, p in enumerate(populer):
            cols_pop[i].button(p, use_container_width=True, key=f"pop_{p}_{i}", on_click=set_search_and_run, args=(p,))

    # Aktüel Afişler (tıklanabilir ürün alanları)
    render_poster_section()

    # Arama tetikleyicileri: Popüler pill / Poster buton / Ara butonu
    if st.session_state.get('_pop_arama'):
        pop_term = st.session_state.pop('_pop_arama')
        with st.spinner("Aranıyor..."):
            df = ara_urun(pop_term)
            goster_sonuclar(df, pop_term)
    elif st.session_state.get('_poster_arama'):
        poster_term = st.session_state.pop('_poster_arama')
        with st.spinner("Aranıyor..."):
            df = ara_urun(poster_term)
            goster_sonuclar(df, poster_term)
    elif ara_btn:
        if arama_text and len(arama_text) >= 2:
            with st.spinner("Aranıyor..."):
                df = ara_urun(arama_text)
                goster_sonuclar(df, arama_text)
        elif arama_text:
            st.info("En az 2 karakter girin.")



# ============================================================================
# ADMIN PANEL
# ============================================================================

def admin_panel():
    """Admin paneli - arama analitikleri"""
    from io import BytesIO

    admin_pass = os.environ.get('ADMIN_PASSWORD') or st.secrets.get('ADMIN_PASSWORD')

    if not admin_pass:
        st.error("Admin şifresi ayarlanmamış! Lütfen çevre değişkenlerini kontrol edin.")
        return

    if not st.session_state.get('admin_auth', False):
        st.title("🔐 Admin Girişi")
        password = st.text_input("Şifre:", type="password")
        if st.button("Giriş"):
            if password == admin_pass:
                st.session_state.admin_auth = True
                st.query_params["admin"] = "true"
                st.rerun()
            else:
                st.error("Yanlış şifre!")
        return

    def df_to_xlsx(dataframe):
        """DataFrame'i xlsx byte'larına çevir"""
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            dataframe.to_excel(writer, index=False, sheet_name='Veri')
        return output.getvalue()

    st.title("Admin Paneli")

    tab_analitik, tab_afis = st.tabs(["Analitikler", "Afiş Yönetimi"])

    with tab_afis:
        admin_poster_yonetimi()

    with tab_analitik:
        client = get_supabase_client()
        if not client:
            st.error("Veritabanı bağlantısı yok")
        else:
            gun_sayisi = st.selectbox("Dönem:", [7, 14, 30], format_func=lambda x: f"Son {x} gün")

            try:
                today = datetime.now().strftime('%Y-%m-%d')
                baslangic = (datetime.now() - timedelta(days=gun_sayisi)).strftime('%Y-%m-%d')

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

                if not all_data:
                    st.warning("Henüz veri yok")
                else:
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

    if st.button("Çıkış"):
        st.session_state.admin_auth = False
        st.rerun()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    params = st.query_params
    if params.get("admin") == "true":
        admin_panel()
    else:
        main()
