"""
ARAMA ANALİTİKLERİ
==================
Arama loglarını görüntüleme sayfası.
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Admin - Arama Analitikleri",
    page_icon="📊",
    layout="wide"
)

# Basit şifre koruması
def check_password():
    """Basit şifre kontrolü"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Admin Girişi")
        password = st.text_input("Şifre:", type="password")
        if st.button("Giriş"):
            # Şifreyi secrets'dan al veya varsayılan kullan
            admin_pass = os.environ.get('ADMIN_PASSWORD', st.secrets.get('ADMIN_PASSWORD', 'admin123'))
            if password == admin_pass:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Yanlış şifre!")
        return False
    return True


def get_supabase_client():
    """Supabase client"""
    try:
        from supabase import create_client
        url = os.environ.get('SUPABASE_URL') or st.secrets.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY') or st.secrets.get('SUPABASE_KEY')
        if url and key:
            return create_client(url, key)
    except:
        pass
    return None


def load_arama_log(gun_sayisi=7):
    """Son X günün arama loglarını yükle"""
    client = get_supabase_client()
    if not client:
        return None

    try:
        baslangic = (datetime.now() - timedelta(days=gun_sayisi)).strftime('%Y-%m-%d')
        result = client.table('arama_log')\
            .select('*')\
            .gte('tarih', baslangic)\
            .order('tarih', desc=True)\
            .order('arama_sayisi', desc=True)\
            .execute()

        if result.data:
            return pd.DataFrame(result.data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Veri yükleme hatası: {e}")
        return None


def main():
    if not check_password():
        return

    st.title("📊 Arama Analitikleri")
    st.markdown("---")

    # Filtre
    col1, col2 = st.columns([1, 3])
    with col1:
        gun_sayisi = st.selectbox("Dönem:", [7, 14, 30], format_func=lambda x: f"Son {x} gün")

    # Veri yükle
    df = load_arama_log(gun_sayisi)

    if df is None or df.empty:
        st.warning("Henüz arama verisi yok.")
        return

    # Özet metrikler
    st.subheader("📈 Özet")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        toplam_arama = df['arama_sayisi'].sum()
        st.metric("Toplam Arama", f"{toplam_arama:,}")

    with col2:
        benzersiz_terim = len(df['arama_terimi'].unique())
        st.metric("Benzersiz Terim", f"{benzersiz_terim:,}")

    with col3:
        sonucsuz = df[df['sonuc_sayisi'] == 0]['arama_sayisi'].sum()
        st.metric("Sonuçsuz Arama", f"{sonucsuz:,}")

    with col4:
        sonucsuz_oran = (sonucsuz / toplam_arama * 100) if toplam_arama > 0 else 0
        st.metric("Sonuçsuz Oran", f"%{sonucsuz_oran:.1f}")

    st.markdown("---")

    # Sekmeler
    tab1, tab2, tab3 = st.tabs(["🔥 En Çok Arananlar", "❌ Sonuç Bulunamayanlar", "📋 Tüm Veriler"])

    with tab1:
        st.subheader("En Çok Aranan Terimler")
        top_df = df.groupby('arama_terimi').agg({
            'arama_sayisi': 'sum',
            'sonuc_sayisi': 'last'
        }).reset_index()
        top_df = top_df.sort_values('arama_sayisi', ascending=False).head(20)
        top_df.columns = ['Arama Terimi', 'Arama Sayısı', 'Son Sonuç Sayısı']
        st.dataframe(top_df, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("Sonuç Bulunamayan Aramalar")
        st.caption("Bu ürünler stokta olmayabilir veya yanlış yazılmış olabilir.")
        sonucsuz_df = df[df['sonuc_sayisi'] == 0].groupby('arama_terimi').agg({
            'arama_sayisi': 'sum'
        }).reset_index()
        sonucsuz_df = sonucsuz_df.sort_values('arama_sayisi', ascending=False).head(20)
        sonucsuz_df.columns = ['Arama Terimi', 'Arama Sayısı']

        if sonucsuz_df.empty:
            st.success("Tüm aramalarda sonuç bulunmuş!")
        else:
            st.dataframe(sonucsuz_df, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Tüm Arama Verileri")
        display_df = df[['tarih', 'arama_terimi', 'arama_sayisi', 'sonuc_sayisi']].copy()
        display_df.columns = ['Tarih', 'Arama Terimi', 'Arama Sayısı', 'Sonuç Sayısı']
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Çıkış butonu
    st.markdown("---")
    if st.button("🚪 Çıkış"):
        st.session_state.authenticated = False
        st.rerun()


if __name__ == "__main__":
    main()
