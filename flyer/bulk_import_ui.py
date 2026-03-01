"""Bulk Import UI — Weekly Excel + multiple flyer images/PDFs in one run."""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from flyer.db import (
    upsert_week,
    batch_insert_weekly_products,
    delete_weekly_products,
    insert_flyer,
)
from flyer.excel_import import read_weekly_excel
from flyer.pipeline import process_flyer, get_image_dimensions
from flyer.pdf_utils import pdf_to_jpegs

log = logging.getLogger(__name__)


def _upload_image_to_storage(image_bytes: bytes, filename: str, week_date: str) -> str:
    """Upload flyer image to Supabase Storage."""
    from flyer.db import get_supabase
    client = get_supabase()
    if not client:
        return ""

    bucket = "flyers"
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)
    path = f"{week_date}/{safe_name}"

    # Detect content type from extension
    lower = filename.lower()
    if lower.endswith(".png"):
        content_type = "image/png"
    else:
        content_type = "image/jpeg"

    try:
        try:
            client.storage.from_(bucket).remove([path])
        except Exception:
            pass
        client.storage.from_(bucket).upload(
            path, image_bytes,
            file_options={"content-type": content_type},
        )
        return client.storage.from_(bucket).get_public_url(path)
    except Exception as e:
        log.error(f"Image upload failed: {e}")
        return ""


def _expand_uploads(uploaded_files: list) -> list[tuple[str, bytes]]:
    """Expand uploaded files: PDFs become one entry per page, images pass through.

    Returns:
        List of (filename, image_bytes_jpeg) tuples ready for pipeline.
    """
    expanded: list[tuple[str, bytes]] = []
    for f in uploaded_files:
        raw = f.read()
        lower = f.name.lower()
        if lower.endswith(".pdf"):
            # Convert each PDF page to JPEG
            pages = pdf_to_jpegs(raw, dpi=200)
            base = f.name.rsplit(".", 1)[0]
            for label, jpeg in pages:
                fname = f"{base}_{label}.jpg"
                expanded.append((fname, jpeg))
        else:
            # Regular image — pass through
            expanded.append((f.name, raw))
    return expanded


def bulk_import_page():
    """Main bulk import UI."""
    st.subheader("Haftalık Toplu Yükleme")
    st.caption("1 Excel + afiş dosyaları (JPEG/PNG/PDF). PDF'ler sayfa sayfa işlenir.")

    # --- Inputs ---
    week_date = st.date_input("Hafta Tarihi", value=datetime.now(), key="bi_date")

    col_excel, col_images = st.columns(2)
    with col_excel:
        excel_file = st.file_uploader(
            "Excel Ürün Listesi",
            type=["xlsx", "xls"],
            key="bi_excel",
        )
    with col_images:
        image_files = st.file_uploader(
            "Afiş Dosyaları (çoklu)",
            type=["jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=True,
            key="bi_images",
        )

    if not excel_file:
        st.info("Haftalık Excel dosyasını yükleyin.")
        return
    if not image_files:
        st.info("En az bir afiş dosyası yükleyin (JPEG, PNG veya PDF).")
        return

    # Count PDFs for info
    pdf_count = sum(1 for f in image_files if f.name.lower().endswith(".pdf"))
    img_count = len(image_files) - pdf_count
    parts = []
    if img_count:
        parts.append(f"{img_count} görsel")
    if pdf_count:
        parts.append(f"{pdf_count} PDF")
    st.markdown(f"**{' + '.join(parts)}** yüklendi.")
    if pdf_count:
        st.info("PDF dosyaları sayfa sayfa JPEG'e dönüştürülecek.")

    # --- Process button ---
    if st.button(
        f"Tümünü İşle ({len(image_files)} dosya)",
        type="primary",
        use_container_width=True,
        key="bi_run",
    ):
        _run_bulk_import(str(week_date), excel_file, image_files)


def _run_bulk_import(week_date: str, excel_file, image_files: list):
    """Execute full bulk import pipeline."""

    # 1. Create week
    week_id = upsert_week(week_date)
    if not week_id:
        st.error("Hafta kaydı oluşturulamadı!")
        return

    # 2. Read Excel once
    try:
        excel_df = read_weekly_excel(excel_file)
    except Exception as e:
        st.error(f"Excel okuma hatası: {e}")
        return

    st.success(f"Excel okundu: {len(excel_df)} ürün")

    # 3. Import Excel to weekly_products (batch)
    delete_weekly_products(week_id)  # Clean re-import
    product_rows = []
    for _, row in excel_df.iterrows():
        kod = str(row.get("urun_kodu", "") or "").strip()
        if kod.endswith(".0") and kod[:-2].isdigit():
            kod = kod[:-2]
        aciklama = str(row.get("urun_aciklamasi", "") or "").strip()
        fiyat = str(row.get("afis_fiyat", "") or "").strip()
        if not kod and not aciklama:
            continue
        product_rows.append({
            "urun_kodu": kod or None,
            "urun_aciklamasi": aciklama or None,
            "afis_fiyat": fiyat or None,
        })

    if product_rows:
        batch_insert_weekly_products(week_id, product_rows)

    # 4. Expand PDFs to individual page images
    with st.spinner("PDF dosyaları dönüştürülüyor..."):
        expanded = _expand_uploads(image_files)
    st.info(f"Toplam {len(expanded)} afiş sayfası işlenecek.")

    # 5. Process each flyer image
    progress = st.progress(0, text="Başlanıyor...")
    results_table = []

    # Cache image bytes + flyer IDs in session for viewer
    if "flyer_cache" not in st.session_state:
        st.session_state["flyer_cache"] = {}

    for i, (fname, image_bytes) in enumerate(expanded):
        progress.progress(
            i / len(expanded),
            text=f"İşleniyor: {fname} ({i+1}/{len(expanded)})",
        )

        img_w, img_h = get_image_dimensions(image_bytes)

        # Upload image
        image_url = _upload_image_to_storage(image_bytes, fname, week_date)

        # Create flyer record
        flyer_id = insert_flyer(week_id, fname, image_url, img_w, img_h)
        if not flyer_id:
            results_table.append({
                "Dosya": fname,
                "Durum": "HATA: kayıt oluşturulamadı",
            })
            continue

        # Cache for viewer
        st.session_state["flyer_cache"][flyer_id] = image_bytes

        # Run pipeline: OCR → Cluster → Match → Save
        try:
            result = process_flyer(
                flyer_id, image_bytes, img_w, img_h, excel_df,
            )
            results_table.append({
                "Dosya": fname,
                "OCR Blok": result["ocr_word_count"],
                "Cluster": result["clusters_count"],
                "Eşleşen": result["matched"],
                "İncelenmeli": result["review"],
                "Eşleşmedi": result["unmatched"],
                "Atlanan": result.get("skipped", 0),
            })
        except Exception as e:
            log.error(f"Pipeline error for {fname}: {e}")
            results_table.append({
                "Dosya": fname,
                "Durum": f"HATA: {e}",
            })

    progress.progress(1.0, text="Tamamlandı!")

    # 6. Show results table
    if results_table:
        st.markdown("---")
        st.markdown("### Sonuç Tablosu")
        df_results = pd.DataFrame(results_table)
        st.dataframe(df_results, use_container_width=True, hide_index=True)

        # Summary metrics
        total_clusters = sum(r.get("Cluster", 0) for r in results_table)
        total_matched = sum(r.get("Eşleşen", 0) for r in results_table)
        total_review = sum(r.get("İncelenmeli", 0) for r in results_table)
        total_unmatched = sum(r.get("Eşleşmedi", 0) for r in results_table)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Cluster", total_clusters)
        col2.metric("Eşleşen", total_matched)
        col3.metric("İncelenmeli", total_review)
        col4.metric("Eşleşmedi", total_unmatched, delta_color="inverse")

        if total_review > 0 or total_unmatched > 0:
            st.warning(
                f"{total_review + total_unmatched} cluster incelenmeli. "
                f"'Afiş İncele' sekmesinden düzeltme yapın."
            )
        else:
            st.balloons()

    st.session_state["last_week_id"] = week_id
