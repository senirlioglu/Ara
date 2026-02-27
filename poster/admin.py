"""Poster Admin UI – weekly workflow for uploading, matching, and reviewing posters."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from poster.db import (
    get_supabase,
    upsert_poster,
    get_posters,
    get_poster_items,
    update_poster_item,
    upsert_hotspot,
)
from poster.excel_import import import_excel_to_poster_items
from poster.match import run_auto_match
from poster.hotspot_gen import (
    generate_hotspots_for_poster,
    get_pdf_page_count,
)


def poster_admin_page():
    """Main admin page for poster management."""
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 1.2rem 1rem;
        border-radius: 0 0 20px 20px;
        margin: -1rem -1rem 1.2rem -1rem;
        text-align: center;
    ">
        <h1 style="color: white; font-size: 1.5rem; font-weight: 700; margin: 0;">
            Afiş Yönetimi (Admin)
        </h1>
    </div>
    """, unsafe_allow_html=True)

    tab_upload, tab_review = st.tabs(["Yükle & İşle", "İncele & Düzelt"])

    with tab_upload:
        _tab_upload()
    with tab_review:
        _tab_review()


# ---------------------------------------------------------------------------
# TAB 1: Upload & Process
# ---------------------------------------------------------------------------

def _tab_upload():
    """Upload weekly Excel + PDF, run auto-match and hotspot generation."""
    st.subheader("1. Afiş Bilgileri")

    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("Afiş Başlığı", placeholder="Örn: Hafta 9 Afişi")
    with col2:
        week_date = st.date_input("Hafta Tarihi", value=datetime.now())

    st.markdown("---")
    st.subheader("2. Dosya Yükleme")

    col_pdf, col_excel = st.columns(2)
    with col_pdf:
        pdf_file = st.file_uploader("PDF Afiş Dosyası", type=["pdf"], key="pdf_upload")
    with col_excel:
        excel_file = st.file_uploader("Excel Ürün Listesi", type=["xlsx", "xls"], key="excel_upload")

    if not title:
        st.info("Afiş başlığı girin.")
        return

    # --- Step A: Create/update poster record ---
    if st.button("Afişi Kaydet & İşle", type="primary", use_container_width=True):
        if not pdf_file:
            st.error("PDF dosyası gerekli.")
            return
        if not excel_file:
            st.error("Excel dosyası gerekli.")
            return

        with st.spinner("İşleniyor..."):
            # Read PDF bytes
            pdf_bytes = pdf_file.read()
            pdf_file.seek(0)
            page_count = get_pdf_page_count(pdf_bytes)

            # Store PDF (for now we store as data URL; in production use Supabase Storage)
            # For simplicity: upload to Supabase Storage or store reference
            pdf_url = _upload_pdf_to_storage(pdf_bytes, title, str(week_date))

            # Create poster record
            poster_id = upsert_poster(
                title=title,
                week_date=str(week_date),
                pdf_url=pdf_url,
                page_count=page_count,
            )
            if not poster_id:
                st.error("Afiş kaydedilemedi!")
                return

            st.success(f"Afiş kaydedildi (ID: {poster_id}, {page_count} sayfa)")

            # --- Step B: Import Excel ---
            st.markdown("**Excel import...**")
            try:
                inserted, skipped = import_excel_to_poster_items(excel_file, poster_id)
                st.success(f"Excel import: {inserted} ürün eklendi, {skipped} atlandı")
            except Exception as e:
                st.error(f"Excel import hatası: {e}")
                return

            # --- Step C: Auto-match ---
            st.markdown("**Otomatik eşleştirme...**")
            stats = run_auto_match(poster_id)
            st.success(
                f"Eşleştirme: {stats['matched']} eşleşti, "
                f"{stats['review']} incelenmeli, "
                f"{stats['unmatched']} eşleşmedi"
            )

            # --- Step D: Generate hotspots ---
            st.markdown("**Hotspot üretimi...**")
            hs_stats = generate_hotspots_for_poster(poster_id, pdf_bytes)
            st.success(
                f"Hotspot: {hs_stats['found']} bulundu, "
                f"{hs_stats['missing']} bulunamadı"
            )

            st.balloons()
            st.info(
                f"Toplam {stats['total']} ürün işlendi. "
                f"İncelenmesi gereken {stats['review'] + stats['unmatched']} ürün var. "
                f"'İncele & Düzelt' sekmesinden kontrol edin."
            )

            # Store poster_id in session for review tab
            st.session_state["last_poster_id"] = poster_id


def _upload_pdf_to_storage(pdf_bytes: bytes, title: str, week_date: str) -> str:
    """Upload PDF to Supabase Storage and return public URL.

    Falls back to empty string if storage is not configured.
    """
    client = get_supabase()
    if not client:
        return ""

    bucket = "posters"
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
    file_path = f"{week_date}/{safe_title}.pdf"

    try:
        # Try to upload to Supabase Storage
        client.storage.from_(bucket).upload(
            file_path,
            pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        # Get public URL
        url_resp = client.storage.from_(bucket).get_public_url(file_path)
        return url_resp
    except Exception:
        # Storage not configured – return empty (PDF can be re-uploaded)
        return ""


# ---------------------------------------------------------------------------
# TAB 2: Review & Fix
# ---------------------------------------------------------------------------

def _tab_review():
    """Review and fix matching and hotspot issues."""
    st.subheader("Afiş Seç")

    posters = get_posters(limit=20)
    if not posters:
        st.info("Henüz afiş yok.")
        return

    # Default to last processed poster
    last_pid = st.session_state.get("last_poster_id")
    poster_options = {f"{p['title']} ({p['week_date']})": p["poster_id"] for p in posters}
    labels = list(poster_options.keys())

    # Find default index
    default_idx = 0
    if last_pid:
        for i, (label, pid) in enumerate(poster_options.items()):
            if pid == last_pid:
                default_idx = i
                break

    selected_label = st.selectbox("Afiş", labels, index=default_idx, key="review_poster_select")
    poster_id = poster_options[selected_label]

    items = get_poster_items(poster_id)
    if not items:
        st.info("Bu afişte ürün yok.")
        return

    # Status filter
    filter_status = st.multiselect(
        "Durum Filtresi",
        ["matched", "review", "unmatched", "pending"],
        default=["review", "unmatched"],
    )

    filtered = [it for it in items if it.get("status") in filter_status]

    if not filtered:
        st.success("Filtreye uyan kayıt yok – tüm ürünler eşleşmiş!")
        return

    st.markdown(f"**{len(filtered)} ürün listeleniyor**")

    # Render review table
    for item in filtered:
        _render_review_card(item)


def _render_review_card(item: dict):
    """Render a single review card with edit controls."""
    item_id = item["id"]
    urun_kodu = item.get("urun_kodu") or "-"
    urun_aciklamasi = item.get("urun_aciklamasi") or "-"
    afis_fiyat = item.get("afis_fiyat") or "-"
    status = item.get("status") or "pending"
    match_sku = item.get("match_sku_id") or ""
    search_term = item.get("search_term") or ""
    confidence = item.get("match_confidence") or 0
    page_no = item.get("page_no") or "-"

    status_colors = {
        "matched": "#27ae60",
        "review": "#f39c12",
        "unmatched": "#e74c3c",
        "pending": "#999",
    }
    color = status_colors.get(status, "#999")

    with st.expander(
        f"{'🟢' if status == 'matched' else '🟡' if status == 'review' else '🔴'} "
        f"{urun_kodu} – {urun_aciklamasi[:50]} "
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
                key=f"sku_{item_id}",
            )
            new_search = st.text_input(
                "Arama Terimi",
                value=search_term,
                key=f"search_{item_id}",
            )
            new_price = st.text_input(
                "Afiş Fiyatı",
                value=afis_fiyat if afis_fiyat != "-" else "",
                key=f"price_{item_id}",
            )

            # Hotspot manual entry
            st.markdown("**Hotspot (opsiyonel):**")
            hs_cols = st.columns(4)
            hs_x0 = hs_cols[0].number_input("x0", 0.0, 1.0, 0.0, 0.01, key=f"hx0_{item_id}")
            hs_y0 = hs_cols[1].number_input("y0", 0.0, 1.0, 0.0, 0.01, key=f"hy0_{item_id}")
            hs_x1 = hs_cols[2].number_input("x1", 0.0, 1.0, 0.0, 0.01, key=f"hx1_{item_id}")
            hs_y1 = hs_cols[3].number_input("y1", 0.0, 1.0, 0.0, 0.01, key=f"hy1_{item_id}")

            hs_page = st.number_input(
                "Hotspot Sayfa No",
                min_value=1, max_value=20, value=int(page_no) if page_no != "-" else 1,
                key=f"hpage_{item_id}",
            )

            if st.button("Kaydet", key=f"save_{item_id}", type="primary"):
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

                # Save hotspot if coordinates provided
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
