"""Review UI — per-flyer cluster review, recluster, fix matches."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from flyer.db import (
    get_weeks,
    get_flyers_for_week,
    get_flyer,
    get_clusters_with_matches,
    get_weekly_products,
    update_match,
)
from flyer.pipeline import recluster_flyer
from flyer.excel_import import read_weekly_excel


def review_page():
    """Flyer review page — select week → select flyer → review clusters."""
    st.subheader("Afiş İncele & Düzelt")

    # --- Week selector ---
    weeks = get_weeks(limit=20)
    if not weeks:
        st.info("Henüz hafta yok. Önce toplu yükleme yapın.")
        return

    last_wid = st.session_state.get("last_week_id")
    week_map = {f"Hafta {w['week_date']}": w["week_id"] for w in weeks}
    week_labels = list(week_map.keys())

    default_idx = 0
    if last_wid:
        for i, w in enumerate(weeks):
            if w["week_id"] == last_wid:
                default_idx = i
                break

    selected_week_label = st.selectbox("Hafta", week_labels, index=default_idx, key="rv_week")
    week_id = week_map[selected_week_label]

    # --- Flyer selector ---
    flyers = get_flyers_for_week(week_id)
    if not flyers:
        st.info("Bu haftada afiş yok.")
        return

    flyer_map = {f['filename']: f for f in flyers}
    selected_fname = st.selectbox("Afiş", list(flyer_map.keys()), key="rv_flyer")
    flyer = flyer_map[selected_fname]
    flyer_id = flyer["flyer_id"]

    # --- Clusters + matches ---
    clusters = get_clusters_with_matches(flyer_id)

    if not clusters:
        st.info("Bu afişte cluster yok. Yeniden işleyin.")
        return

    # Summary
    statuses = [c.get("_match", {}).get("status", "unmatched") for c in clusters]
    matched_c = statuses.count("matched")
    review_c = statuses.count("review")
    unmatched_c = statuses.count("unmatched")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cluster", len(clusters))
    col2.metric("Eşleşen", matched_c)
    col3.metric("İncelenmeli", review_c)
    col4.metric("Eşleşmedi", unmatched_c, delta_color="inverse")

    # --- Recluster controls ---
    st.markdown("---")
    with st.expander("Yeniden Kümeleme (eps ayarı)", expanded=False):
        eps = st.slider(
            "DBSCAN eps (piksel mesafesi)",
            min_value=20.0,
            max_value=300.0,
            value=80.0,
            step=10.0,
            key="rv_eps",
        )
        if st.button("Yeniden Kümele", key="rv_recluster"):
            # Need Excel for re-matching
            products = get_weekly_products(week_id)
            if not products:
                st.error("Bu haftanın ürün listesi bulunamadı.")
            else:
                excel_df = pd.DataFrame(products)
                result = recluster_flyer(
                    flyer_id,
                    flyer.get("img_w", 1),
                    flyer.get("img_h", 1),
                    excel_df,
                    eps=eps,
                )
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(
                        f"Yeniden kümeleme: {result['clusters_count']} cluster, "
                        f"{result['matched']} eşleşti, {result['review']} incelenmeli"
                    )
                    st.rerun()

    # --- Cluster list ---
    st.markdown("---")
    filter_status = st.multiselect(
        "Durum Filtresi",
        ["matched", "review", "unmatched", "pending"],
        default=["review", "unmatched"],
        key="rv_filter",
    )

    filtered = [
        c for c in clusters
        if c.get("_match", {}).get("status", "unmatched") in filter_status
    ]

    if not filtered:
        st.info("Filtreye uyan cluster yok.")
        return

    st.markdown(f"**{len(filtered)} cluster gösteriliyor**")

    # Get weekly products for candidate dropdown
    products = get_weekly_products(week_id)
    product_options = {}
    if products:
        for p in products:
            kod = p.get("urun_kodu") or ""
            aciklama = (p.get("urun_aciklamasi") or "")[:50]
            label = f"{kod} — {aciklama}"
            product_options[label] = p

    for cl in filtered:
        _render_cluster_card(cl, product_options)


def _render_cluster_card(cluster: dict, product_options: dict):
    """Render a single cluster review card."""
    cid = cluster.get("cluster_id", "?")
    ocr_text = cluster.get("ocr_text", "")
    match = cluster.get("_match", {})
    match_id = match.get("match_id")
    status = match.get("status", "unmatched")
    confidence = match.get("confidence", 0)
    matched_kod = match.get("urun_kodu") or ""
    matched_desc = match.get("urun_aciklamasi") or ""

    icon = {"matched": "++", "review": "!!", "unmatched": "XX"}.get(status, "..")
    label = f"[{icon}] Cluster #{cid}: {ocr_text[:60]}"

    with st.expander(label, expanded=(status != "matched")):
        col_info, col_fix = st.columns([1, 1])

        with col_info:
            # Bbox info
            x0 = cluster.get("x0", 0)
            y0 = cluster.get("y0", 0)
            x1 = cluster.get("x1", 0)
            y1 = cluster.get("y1", 0)
            st.markdown(f"""
**OCR Text:** {ocr_text[:200]}
**Bbox:** ({x0:.3f}, {y0:.3f}) → ({x1:.3f}, {y1:.3f})
**Eşleşen:** {matched_kod or '—'} — {matched_desc[:50] or '—'}
**Güven:** %{int(confidence * 100)} [{status}]
            """)

        with col_fix:
            if not match_id:
                st.info("Match kaydı yok.")
                return

            st.markdown("**Manuel Düzeltme:**")

            # Product dropdown
            options = ["(Değiştirme)"] + list(product_options.keys())
            selected = st.selectbox(
                "Doğru Ürün",
                options,
                key=f"rv_fix_{cid}",
            )

            if st.button("Kaydet", key=f"rv_save_{cid}", type="primary"):
                if selected != "(Değiştirme)":
                    product = product_options[selected]
                    update_match(match_id, {
                        "urun_kodu": product.get("urun_kodu"),
                        "urun_aciklamasi": product.get("urun_aciklamasi"),
                        "afis_fiyat": product.get("afis_fiyat"),
                        "confidence": 1.0,
                        "status": "matched",
                    })
                    st.success("Düzeltildi!")
                    st.rerun()

            # Quick "unmatched" button
            if status != "unmatched":
                if st.button("Eşleşme Yok", key=f"rv_unmatch_{cid}"):
                    update_match(match_id, {
                        "urun_kodu": None,
                        "urun_aciklamasi": None,
                        "confidence": 0,
                        "status": "unmatched",
                    })
                    st.rerun()
