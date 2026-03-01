"""Review UI — per-flyer cluster review, recluster, fix matches.

Updated: Shows only clusters with product signal (price/model/brand).
Provides eps slider + "Rebuild (no re-OCR)" button.
Skipped/noise clusters hidden by default.
"""

from __future__ import annotations

import json

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


def _parse_keys(keys_json) -> dict:
    """Parse keys_json from DB (could be str or dict)."""
    if isinstance(keys_json, str):
        try:
            return json.loads(keys_json)
        except Exception:
            return {}
    return keys_json or {}


def _has_product_signal(cluster: dict) -> bool:
    """Check if a cluster has price/model/brand signals worth reviewing."""
    keys = _parse_keys(cluster.get("keys_json", {}))
    return bool(
        keys.get("model_codes")
        or keys.get("prices")
        or keys.get("brands")
        or keys.get("code4")
    )


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

    # Separate clusters with product signal vs noise
    signal_clusters = [c for c in clusters if _has_product_signal(c)]
    noise_clusters = [c for c in clusters if not _has_product_signal(c)]

    # Summary
    statuses = [c.get("_match", {}).get("status", "unmatched") for c in signal_clusters]
    matched_c = statuses.count("matched")
    review_c = statuses.count("review")
    unmatched_c = statuses.count("unmatched")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Ürün Cluster", len(signal_clusters))
    col2.metric("Eşleşen", matched_c)
    col3.metric("İncelenmeli", review_c)
    col4.metric("Eşleşmedi", unmatched_c, delta_color="inverse")
    col5.metric("Gürültü (gizli)", len(noise_clusters))

    # --- Recluster controls ---
    st.markdown("---")
    with st.expander("Yeniden Kümeleme (OCR'sız Yeniden İşle)", expanded=False):
        st.caption("OCR sonuçları önbellekte. Sadece kümeleme ve eşleştirme yeniden yapılır.")

        c1, c2 = st.columns(2)
        with c1:
            eps = st.slider(
                "DBSCAN eps (piksel mesafesi)",
                min_value=20.0,
                max_value=300.0,
                value=80.0,
                step=10.0,
                key="rv_eps",
            )
        with c2:
            min_samp = st.slider(
                "Min samples",
                min_value=2,
                max_value=10,
                value=3,
                step=1,
                key="rv_min_samples",
            )

        if st.button("Yeniden Kümele (OCR'sız)", key="rv_recluster", type="primary"):
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
                    min_samples=min_samp,
                )
                if "error" in result:
                    st.error(result["error"])
                else:
                    skipped = result.get("skipped", 0)
                    st.success(
                        f"Yeniden kümeleme: {result['clusters_count']} cluster "
                        f"({result['matched']} eşleşti, {result['review']} incelenmeli"
                        f"{f', {skipped} gürültü atlandı' if skipped else ''})"
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

    show_noise = st.checkbox("Gürültü cluster'ları da göster", value=False, key="rv_show_noise")

    # Filter clusters to display
    display_clusters = signal_clusters if not show_noise else clusters
    filtered = [
        c for c in display_clusters
        if c.get("_match", {}).get("status", "unmatched") in filter_status
    ]

    if not filtered:
        st.info("Filtreye uyan cluster yok.")
        return

    st.markdown(f"**{len(filtered)} cluster gösteriliyor** (toplam {len(clusters)})")

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

    # Parse keys for display
    keys = _parse_keys(cluster.get("keys_json", {}))
    has_signal = _has_product_signal(cluster)

    icon = {
        "matched": "++",
        "review": "!!",
        "unmatched": "XX",
        "skip": "..",
    }.get(status, "..")

    signal_tag = "" if has_signal else " [gürültü]"
    label = f"[{icon}] Cluster #{cid}: {ocr_text[:60]}{signal_tag}"

    with st.expander(label, expanded=(status != "matched")):
        col_info, col_fix = st.columns([1, 1])

        with col_info:
            # Bbox info
            x0 = cluster.get("x0", 0)
            y0 = cluster.get("y0", 0)
            x1 = cluster.get("x1", 0)
            y1 = cluster.get("y1", 0)

            # Key signals
            signals = []
            if keys.get("model_codes"):
                signals.append(f"Model: {', '.join(keys['model_codes'][:3])}")
            if keys.get("brands"):
                signals.append(f"Marka: {', '.join(keys['brands'][:2])}")
            if keys.get("prices"):
                signals.append(f"Fiyat: {', '.join(keys['prices'][:2])}")
            if keys.get("code4"):
                signals.append(f"Kod: {', '.join(keys['code4'][:3])}")
            if keys.get("sizes"):
                signals.append(f"Boyut: {', '.join(keys['sizes'][:2])}")

            signal_str = " | ".join(signals) if signals else "Sinyal yok"

            st.markdown(f"""
**OCR Text:** {ocr_text[:200]}
**Sinyaller:** {signal_str}
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
