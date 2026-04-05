"""Bulk Import UI — upload Excel + PDFs, process all pages.

Pipeline per page:
  PDF render → Vision OCR → Price detect → Region build → Match → Save
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from flyer.storage_supabase import (
    upsert_week,
    batch_insert_weekly_products,
    delete_weekly_products,
    insert_flyer,
    delete_regions_for_flyer,
    batch_insert_regions,
    batch_insert_matches,
    upload_to_storage,
)
from flyer.excel_import import read_weekly_excel
from flyer.pdf_render import page_count, render_page
from flyer.vision_ocr import run_ocr
from flyer.price_detect import find_prices
from flyer.region_builder import build_regions
from flyer.match_excel import match_regions

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Full pipeline for a single page
# ---------------------------------------------------------------------------

def process_page(
    flyer_id: int,
    png_bytes: bytes,
    img_w: int,
    img_h: int,
    excel_df: pd.DataFrame,
    force_ocr: bool = False,
) -> dict:
    """Full pipeline for one flyer page.

    Returns:
        {words, prices, regions, matched, review, unmatched}
    """
    # 1. OCR
    words = run_ocr(flyer_id, png_bytes, force=force_ocr)

    # 2. Price detection
    prices = find_prices(words, img_w, img_h)

    # 3. Region building
    regions = build_regions(words, prices, img_w, img_h)

    # 4. Save regions
    delete_regions_for_flyer(flyer_id)
    saved_regions = batch_insert_regions(flyer_id, regions)

    if not saved_regions:
        return {
            "words": len(words),
            "prices": len(prices),
            "regions": 0,
            "matched": 0,
            "review": 0,
            "unmatched": 0,
        }

    # 5. Match to Excel
    match_results = match_regions(saved_regions, excel_df)

    # 6. Save matches
    match_rows = []
    stats = {"matched": 0, "review": 0, "unmatched": 0}
    for mr in match_results:
        best = mr["best_match"]
        st_val = best.get("status", "unmatched")
        match_rows.append({
            "region_id": mr["region_id"],
            "urun_kodu": best.get("urun_kodu"),
            "urun_aciklamasi": best.get("urun_aciklamasi"),
            "afis_fiyat": best.get("afis_fiyat"),
            "confidence": best.get("confidence", 0),
            "status": st_val,
            "candidates": mr.get("candidates", []),
        })
        stats[st_val] = stats.get(st_val, 0) + 1

    batch_insert_matches(match_rows)

    return {
        "words": len(words),
        "prices": len(prices),
        "regions": len(saved_regions),
        **stats,
    }


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def bulk_import_page():
    """Main bulk import UI."""
    st.subheader("Haftalık Toplu Yükleme")
    st.caption("1 Excel + PDF dosyaları. Her PDF sayfası ayrı işlenir.")

    # --- Inputs ---
    week_date = st.date_input("Hafta Tarihi", value=datetime.now(), key="bi_date")

    col_excel, col_pdfs = st.columns(2)
    with col_excel:
        excel_file = st.file_uploader(
            "Excel Ürün Listesi",
            type=["xlsx", "xls"],
            key="bi_excel",
        )
    with col_pdfs:
        pdf_files = st.file_uploader(
            "PDF Dosyaları (çoklu)",
            type=["pdf"],
            accept_multiple_files=True,
            key="bi_pdfs",
        )

    if not excel_file:
        st.info("Haftalık Excel dosyasını yükleyin.")
        return
    if not pdf_files:
        st.info("En az bir PDF dosyası yükleyin.")
        return

    zoom = st.slider("Render Zoom", min_value=2.0, max_value=5.0, value=3.5, step=0.5, key="bi_zoom")

    # Count total pages
    total_pages = 0
    pdf_data: list[tuple[str, bytes, int]] = []
    for f in pdf_files:
        raw = f.read()
        n = page_count(raw)
        pdf_data.append((f.name, raw, n))
        total_pages += n

    st.markdown(f"**{len(pdf_files)} PDF**, toplam **{total_pages} sayfa** işlenecek.")

    # --- Process button ---
    if st.button(
        f"Tümünü İşle ({total_pages} sayfa)",
        type="primary",
        use_container_width=True,
        key="bi_run",
    ):
        _run_bulk(str(week_date), excel_file, pdf_data, zoom)


def _run_bulk(
    week_date: str,
    excel_file,
    pdf_data: list[tuple[str, bytes, int]],
    zoom: float,
):
    """Execute the full bulk import pipeline."""

    # 1. Create week
    week_id = upsert_week(week_date)
    if not week_id:
        st.error("Hafta kaydı oluşturulamadı!")
        return

    # 2. Read Excel
    try:
        excel_df = read_weekly_excel(excel_file)
    except Exception as e:
        st.error(f"Excel okuma hatası: {e}")
        return

    st.success(f"Excel okundu: {len(excel_df)} ürün")

    # 3. Import Excel to weekly_products
    delete_weekly_products(week_id)
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

    # 4. Process each PDF page
    progress = st.progress(0, text="Başlanıyor...")
    results_table = []

    if "flyer_cache" not in st.session_state:
        st.session_state["flyer_cache"] = {}

    page_idx = 0
    total = sum(n for _, _, n in pdf_data)

    for pdf_name, pdf_bytes, n_pages in pdf_data:
        for page_no in range(1, n_pages + 1):
            page_idx += 1
            label = f"{pdf_name} s.{page_no}"
            progress.progress(
                page_idx / total,
                text=f"İşleniyor: {label} ({page_idx}/{total})",
            )

            try:
                # Render
                png_bytes, img_w, img_h = render_page(pdf_bytes, page_no, zoom=zoom)

                # Upload to storage
                safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in pdf_name)
                storage_path = f"{week_date}/{safe_name}_s{page_no}.png"
                image_url = upload_to_storage("flyers", storage_path, png_bytes, "image/png")

                # Create flyer record
                flyer_id = insert_flyer(
                    week_id, pdf_name, page_no,
                    image_url, img_w, img_h, zoom,
                )
                if not flyer_id:
                    results_table.append({"Sayfa": label, "Durum": "HATA: kayıt oluşturulamadı"})
                    continue

                # Cache for viewer/review
                st.session_state["flyer_cache"][flyer_id] = png_bytes

                # Run pipeline
                result = process_page(flyer_id, png_bytes, img_w, img_h, excel_df)
                results_table.append({
                    "Sayfa": label,
                    "Kelime": result["words"],
                    "Fiyat": result["prices"],
                    "Bölge": result["regions"],
                    "Eşleşen": result["matched"],
                    "İncelenmeli": result["review"],
                    "Eşleşmedi": result["unmatched"],
                })

            except Exception as e:
                log.error(f"Pipeline error for {label}: {e}")
                results_table.append({"Sayfa": label, "Durum": f"HATA: {e}"})

    progress.progress(1.0, text="Tamamlandı!")

    # 5. Results table
    if results_table:
        st.markdown("---")
        st.markdown("### Sonuç Tablosu")
        st.dataframe(pd.DataFrame(results_table), use_container_width=True, hide_index=True)

        total_regions = sum(r.get("Bölge", 0) for r in results_table)
        total_matched = sum(r.get("Eşleşen", 0) for r in results_table)
        total_review = sum(r.get("İncelenmeli", 0) for r in results_table)
        total_unmatched = sum(r.get("Eşleşmedi", 0) for r in results_table)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam Bölge", total_regions)
        c2.metric("Eşleşen", total_matched)
        c3.metric("İncelenmeli", total_review)
        c4.metric("Eşleşmedi", total_unmatched, delta_color="inverse")

        if total_review > 0 or total_unmatched > 0:
            st.warning(
                f"{total_review + total_unmatched} bölge incelenmeli. "
                f"'İncele & Düzelt' sekmesinden düzeltme yapın."
            )
        else:
            st.balloons()

    st.session_state["last_week_id"] = week_id
