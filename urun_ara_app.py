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
import unicodedata
from datetime import datetime, timedelta
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
    .stButton > button { border-radius: 12px !important; padding: 0.75rem 1.5rem !important; font-weight: 600 !important; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; border: none !important; }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important; }
    .info-card { background: white; padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.85rem; color: #666; text-align: center; margin-bottom: 1rem; }
    .streamlit-expanderHeader { background: white !important; border-radius: 12px !important; border: none !important; box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important; padding: 0.75rem 1rem !important; font-weight: 500 !important; }
    .streamlit-expanderContent { background: white !important; border-radius: 0 0 12px 12px !important; border: none !important; padding: 0.5rem !important; }
    @media (max-width: 768px) { .block-container { padding: 1rem !important; } }
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
    elif adet == 1:
        return "Kritik", "stok-kritik", "#ff4444"
    elif adet <= 5:
        return "Düşük", "stok-dusuk", "#ff9800"
    elif adet <= 10:
        return "Normal", "stok-normal", "#4caf50"
    else:
        return "Yüksek", "stok-yuksek", "#2196f3"


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

def ara_urun(arama_text: str) -> Optional[pd.DataFrame]:
    """
    SERVER-SIDE SEARCH - Tüm arama SQL'de yapılır.
    Python sadece normalize + negatif filtre uygular.
    """
    if not arama_text or len(arama_text) < 2:
        return None

    try:
        client = get_supabase_client()
        if not client:
            return None

        # Sayıysa normalize yapma
        arama_raw = arama_text.strip()
        if arama_raw.isdigit():
            optimize_sorgu = arama_raw
        else:
            optimize_sorgu = temizle_ve_kok_bul(arama_raw)

        # RPC Çağrısı
        result = client.rpc('hizli_urun_ara', {'arama_terimi': optimize_sorgu}).execute()

        # Hata kontrolü
        if getattr(result, 'error', None):
            st.error(f"Arama hatası (RPC): {result.error}")
            return None

        if result.data:
            df = pd.DataFrame(result.data)

            # out_ prefix temizle (güvenlik için)
            df.columns = [col.replace('out_', '') for col in df.columns]

            # PYTHON TARAFI NEGATİF FİLTRELEME (CPU)
            arama_lower = optimize_sorgu.lower()
            if arama_lower in ['tv', 'televizyon']:
                yasakli = ['battaniye', 'battanıye', 'ünite', 'unite', 'sehpa',
                           'koltuk', 'kılıf', 'kumanda', 'askı', 'aparat', 'kablo',
                           'atv', 'oyuncak', 'lisanslı', 'tvk']
                for yasak in yasakli:
                    df = df[~df['urun_ad'].str.contains(yasak, case=False, na=False)]

            df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])
            return df

        # Sonuç yoksa boş DataFrame
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

            if result.data:
                kayit = result.data[0]
                client.table('arama_log')\
                    .update({'arama_sayisi': kayit['arama_sayisi'] + 1, 'sonuc_sayisi': sonuc_sayisi})\
                    .eq('id', kayit['id'])\
                    .execute()
            else:
                client.table('arama_log').insert({
                    'tarih': bugun,
                    'arama_terimi': terim,
                    'arama_sayisi': 1,
                    'sonuc_sayisi': sonuc_sayisi
                }).execute()
    except:
        pass


def goster_sonuclar(df: pd.DataFrame, arama_text: str):
    """Sonuçları kartlar halinde göster"""
    # Hata varsa (None) sessizce çık - hata mesajı zaten basıldı
    if df is None:
        return

    sonuc_sayisi = 0 if df.empty else len(df['urun_kod'].unique())
    log_arama(arama_text, sonuc_sayisi)

    # Sonuç yoksa (empty) kullanıcıya bildir
    if df.empty:
        st.warning(f"'{arama_text}' için sonuç bulunamadı.")
        return

    # Pandas Gruplama
    urunler = df.groupby('urun_kod').agg({
        'urun_ad': 'first',
        'stok_adet': lambda x: (x > 0).sum()
    }).reset_index()

    urunler.columns = ['urun_kod', 'urun_ad', 'stoklu_magaza']

    st.success(f"**{len(urunler)}** farklı ürün bulundu")

    for _, urun in urunler.iterrows():
        urun_kod = urun['urun_kod']
        urun_ad = urun['urun_ad'] if urun['urun_ad'] else urun_kod
        stoklu_magaza = int(urun['stoklu_magaza'])

        urun_df = df[df['urun_kod'] == urun_kod].copy()
        urun_df_stoklu = urun_df[urun_df['stok_adet'] > 0].sort_values('stok_adet', ascending=False)

        icon = "📦" if stoklu_magaza > 0 else "❌"
        baslik = f"{icon} {urun_kod}  •  {urun_ad[:40]}  •  🏪 {stoklu_magaza} mağaza"

        with st.expander(baslik, expanded=False):
            if urun_df_stoklu.empty:
                st.error("Bu ürün hiçbir mağazada stokta yok!")
            else:
                for _, row in urun_df_stoklu.iterrows():
                    try:
                        seviye, _, renk = get_stok_seviye(row['stok_adet'])
                    except:
                        seviye, renk = "Normal", "#3498db"

                    adet = int(row['stok_adet'])
                    magaza_ad = row['magaza_ad'] or row['magaza_kod']

                    # Güvenli Veri Çekme
                    sm = row.get('sm_kod') or "-"
                    bs = row.get('bs_kod') or "-"

                    # Fiyat Gösterimi (0 ise gösterme)
                    ham_fiyat = row.get('birim_fiyat')
                    if ham_fiyat and float(ham_fiyat) > 0:
                        fiyat_str = f"{float(ham_fiyat):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"
                    else:
                        fiyat_str = ""

                    # Harita Linki
                    lat = row.get('latitude')
                    lon = row.get('longitude')

                    if lat and lon:
                        harita_ikonu = (
                            f'<a href="https://www.google.com/maps?q={lat},{lon}" '
                            'target="_blank" '
                            'style="text-decoration:none; margin-left:8px; padding:4px 8px; '
                            'border-radius:12px; background:#eef2ff; color:#374151; font-size:0.78rem;" '
                            'title="Yol tarifi al">'
                            '📍 Yol tarifi</a>'
                        )
                    else:
                        harita_ikonu = ""

                    st.markdown(f"""
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
                                <span style="font-weight:normal; color:#2ecc71; font-size:0.9rem; margin-left:10px;">{fiyat_str}</span>
                            </div>
                            <div style="font-size: 0.85rem; color: #666; margin-top: 4px;">
                                <b>SM:</b> {sm}  •  <b>BS:</b> {bs}  •  <i>{row.get('magaza_kod')}</i>
                            </div>
                        </div>
                        <div style="background: {renk}; color: white; padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 0.9rem;">
                            {adet} Adet
                        </div>
                    </div>
                    """, unsafe_allow_html=True)


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

    # Arama kutusu
    col1, col2 = st.columns([5, 1])
    with col1:
        arama_text = st.text_input(
            "Arama",
            placeholder="Ürün kodu veya adı yazın (örn: kedi mama, tv 55)...",
            label_visibility="collapsed",
            key="arama_input"
        )
    with col2:
        ara_btn = st.button("🔍 Ara", use_container_width=True, type="primary")

    if arama_text and len(arama_text) >= 2:
        with st.spinner("Aranıyor..."):
            df = ara_urun(arama_text)
            goster_sonuclar(df, arama_text)
    elif arama_text and len(arama_text) < 2:
        st.info("En az 2 karakter girin.")


# ============================================================================
# ADMIN PANEL
# ============================================================================

def admin_panel():
    """Admin paneli - arama analitikleri"""
    import hashlib

    admin_pass = os.environ.get('ADMIN_PASSWORD') or st.secrets.get('ADMIN_PASSWORD', 'admin123')
    today = datetime.now().strftime('%Y-%m-%d')
    valid_token = hashlib.md5(f"{admin_pass}{today}".encode()).hexdigest()[:16]

    params = st.query_params
    url_token = params.get("token", "")

    if url_token == valid_token:
        st.session_state.admin_auth = True

    if not st.session_state.get('admin_auth', False):
        st.title("🔐 Admin Girişi")
        password = st.text_input("Şifre:", type="password")
        if st.button("Giriş"):
            if password == admin_pass:
                st.session_state.admin_auth = True
                st.query_params["admin"] = "true"
                st.query_params["token"] = valid_token
                st.rerun()
            else:
                st.error("Yanlış şifre!")
        return

    st.title("📊 Arama Analitikleri")

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

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Toplam Arama", f"{df['arama_sayisi'].sum():,}")
        with col2:
            st.metric("Benzersiz Terim", f"{len(df['arama_terimi'].unique()):,}")
        with col3:
            sonucsuz = df[df['sonuc_sayisi'] == 0]['arama_sayisi'].sum()
            st.metric("Sonuçsuz", f"{sonucsuz:,}")

        st.markdown("---")

        st.subheader("🔥 En Çok Arananlar")
        top_df = df.groupby('arama_terimi').agg({'arama_sayisi': 'sum', 'sonuc_sayisi': 'last'}).reset_index()
        top_df = top_df.sort_values('arama_sayisi', ascending=False).head(20)
        top_df.columns = ['Terim', 'Arama', 'Sonuç']
        st.dataframe(top_df, use_container_width=True, hide_index=True)

        st.subheader("❌ Sonuç Bulunamayanlar")
        sonucsuz_df = df[df['sonuc_sayisi'] == 0].groupby('arama_terimi')['arama_sayisi'].sum().reset_index()
        sonucsuz_df = sonucsuz_df.sort_values('arama_sayisi', ascending=False).head(20)
        sonucsuz_df.columns = ['Terim', 'Arama']
        if sonucsuz_df.empty:
            st.success("Tüm aramalarda sonuç bulunmuş!")
        else:
            st.dataframe(sonucsuz_df, use_container_width=True, hide_index=True)

        # Bugün arananlar
        st.subheader("🕐 Bugün Arananlar")
        bugun = datetime.now().strftime('%Y-%m-%d')
        bugun_df = df[df['tarih'] == bugun].sort_values('arama_sayisi', ascending=False)
        if bugun_df.empty:
            st.info("Bugün henüz arama yapılmamış")
        else:
            bugun_df = bugun_df[['arama_terimi', 'arama_sayisi', 'sonuc_sayisi']].head(30)
            bugun_df.columns = ['Terim', 'Arama', 'Sonuç']
            st.dataframe(bugun_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Hata: {e}")

    if st.button("🚪 Çıkış"):
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
