"""
ÜRÜN ARAMA UYGULAMASI (Server-Side Search)
==========================================
Tüm arama işlemleri PostgreSQL'de yapılır. RAM kullanımı minimal.
"""

import streamlit as st
import pandas as pd
import os
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
    Arama terimini temizle ve kökleri bul.
    'kedi maması tavuklu' -> 'kedi mama tavuk'
    """
    if not text:
        return ""

    # Türkçe -> ASCII dönüşümü
    tr_map = {
        'İ': 'i', 'I': 'i', 'ı': 'i',
        'Ğ': 'g', 'ğ': 'g',
        'Ü': 'u', 'ü': 'u',
        'Ş': 's', 'ş': 's',
        'Ö': 'o', 'ö': 'o',
        'Ç': 'c', 'ç': 'c'
    }

    clean_text = text
    for tr, eng in tr_map.items():
        clean_text = clean_text.replace(tr, eng)

    # Türkçe ekler (uzundan kısaya)
    ekler = [
        'lari', 'leri', 'lar', 'ler',
        'lık', 'lik', 'luk', 'lük',
        'si', 'su', 'sı', 'sü',
        'lu', 'lü', 'li', 'lı',
        'cu', 'cü', 'ci', 'cı',
        'daki', 'deki', 'taki', 'teki',
        'dan', 'den', 'tan', 'ten',
        'da', 'de', 'ta', 'te',
        'nın', 'nin', 'nun', 'nün',
        'in', 'ın', 'un', 'ün',
        'yi', 'yu', 'yı', 'yü',
    ]

    kelimeler = clean_text.lower().split()
    temiz_kelimeler = []

    for kelime in kelimeler:
        kok = kelime
        # Sadece 4+ karakterlik kelimelerde ek temizle
        if len(kelime) > 4:
            for ek in ekler:
                if kelime.endswith(ek):
                    olasi_kok = kelime[:-len(ek)]
                    if len(olasi_kok) >= 3:  # Kök en az 3 karakter olsun
                        kok = olasi_kok
                        break
        temiz_kelimeler.append(kok)

    return " ".join(temiz_kelimeler)


# ============================================================================
# URUN ARAMA (SERVER-SIDE)
# ============================================================================

def ara_urun(arama_text: str) -> Optional[pd.DataFrame]:
    """
    SERVER-SIDE SEARCH:
    1. Python'da kökleri bul (mamasi -> mama)
    2. SQL'e temizlenmiş sorguyu gönder
    3. Sonuçları döndür

    RAM'e veri yüklemez, anlık sorgular.
    """
    if not arama_text or len(arama_text) < 2:
        return None

    try:
        client = get_supabase_client()
        if not client:
            return None

        # 1. Kökleri bul
        optimize_sorgu = temizle_ve_kok_bul(arama_text)

        # 2. Supabase RPC çağır
        result = client.rpc('hizli_urun_ara', {'arama_terimi': optimize_sorgu}).execute()

        if result.data:
            df = pd.DataFrame(result.data)
            df = df.drop_duplicates(subset=['magaza_kod', 'urun_kod'])
            return df

        return pd.DataFrame()

    except Exception as e:
        st.error(f"Arama hatası: {e}")
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
    sonuc_sayisi = 0 if df is None or df.empty else len(df['urun_kod'].unique())
    log_arama(arama_text, sonuc_sayisi)

    if df is None or df.empty:
        st.warning(f"'{arama_text}' için sonuç bulunamadı.")
        return

    # Ürün bazlı grupla
    urunler = df.groupby('urun_kod').agg({
        'urun_ad': 'first',
        'nitelik': 'first',
        'stok_adet': lambda x: (x > 0).sum()
    }).reset_index()
    urunler.columns = ['urun_kod', 'urun_ad', 'nitelik', 'stoklu_magaza']

    st.success(f"**{len(urunler)}** ürün bulundu")

    for _, urun in urunler.iterrows():
        urun_kod = urun['urun_kod']
        urun_ad = urun['urun_ad'] or urun_kod
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
                    seviye, _, renk = get_stok_seviye(row['stok_adet'])
                    adet = int(row['stok_adet'])
                    magaza_ad = row.get('magaza_ad', row['magaza_kod']) or row['magaza_kod']
                    sm = row.get('sm_kod', '-') or '-'
                    bs = row.get('bs_kod', '-') or '-'

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
                            <div style="font-weight: 600; font-size: 1rem; color: #1e3a5f;">{magaza_ad}</div>
                            <div style="font-size: 0.85rem; color: #666; margin-top: 4px;">SM: {sm}  •  BS: {bs}</div>
                        </div>
                        <div style="
                            background: {renk};
                            color: white;
                            padding: 6px 14px;
                            border-radius: 20px;
                            font-weight: 600;
                            font-size: 0.9rem;
                            white-space: nowrap;
                        ">
                            {adet} Adet ({seviye})
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
    arama_text = st.text_input(
        "Arama",
        placeholder="Ürün kodu veya adı yazın (örn: kedi mama, tv 55)...",
        label_visibility="collapsed",
        key="arama_input"
    )

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
