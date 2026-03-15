"""Review UI — per-page region review, rebuild, re-OCR, fix matches.

Shows each detected product region with:
  - Crop preview from flyer image
  - Detected price + keys
  - Current match + confidence
  - Top 5 candidates dropdown for manual correction

Actions:
  - Re-render (zoom selector)
  - Rebuild regions from cached OCR (no re-OCR)
  - Re-OCR (explicit, re-calls Vision API)
  - Reset page (delete all regions + matches)
"""

from __future__ import annotations

import json
import logging
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

from flyer.storage_supabase import (
    get_weeks,
    get_flyers_for_week,
    get_regions_with_matches,
    get_clusters_with_matches,
    get_weekly_products,
    get_ocr_cache,
    update_match,
    update_flyer,
    delete_regions_for_flyer,
    delete_ocr_cache,
    batch_insert_regions,
    batch_insert_matches,
)
from flyer.admin_bulk_import import process_page
from flyer.price_detect import find_prices
from flyer.region_builder import build_regions
from flyer.match_excel import match_regions
from flyer.pdf_render import render_page

log = logging.getLogger(__name__)


def _make_flyer_label(flyer: dict) -> str:
    """Build a safe, user-friendly label for flyer selection."""
    filename = flyer.get("pdf_filename") or flyer.get("image_url") or "Dosya adı yok"
    page_no = flyer.get("page_no")
    if page_no is None:
        return str(filename)
    return f"{filename} s.{page_no}"


def _build_flyer_label_map(flyers: list[dict]) -> dict[str, dict]:
    """Map unique labels to flyer records without KeyError risk."""
    label_map: dict[str, dict] = {}
    for flyer in flyers:
        base_label = _make_flyer_label(flyer)
        label = base_label
        counter = 2
        while label in label_map:
            label = f"{base_label} ({counter})"
            counter += 1
        label_map[label] = flyer
    return label_map


def _parse_keys(keys_json) -> dict:
    if isinstance(keys_json, str):
        try:
            return json.loads(keys_json)
        except Exception:
            return {}
    return keys_json or {}


def _get_image_bytes(flyer: dict) -> bytes | None:
    """Get image bytes from cache or URL."""
    flyer_id = flyer["flyer_id"]
    cache = st.session_state.get("flyer_cache", {})
    if flyer_id in cache:
        return cache[flyer_id]

    url = flyer.get("image_url", "")
    if not url:
        return None
    try:
        import httpx
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        data = resp.content
        # Cache for next time
        if "flyer_cache" not in st.session_state:
            st.session_state["flyer_cache"] = {}
        st.session_state["flyer_cache"][flyer_id] = data
        return data
    except Exception:
        return None


def _crop_region(image_bytes: bytes, region: dict) -> bytes | None:
    """Crop a region from the flyer image. Returns PNG bytes."""
    try:
        img = Image.open(BytesIO(image_bytes))
        w, h = img.size
        x0 = int(region.get("x0", 0) * w)
        y0 = int(region.get("y0", 0) * h)
        x1 = int(region.get("x1", 0) * w)
        y1 = int(region.get("y1", 0) * h)
        cropped = img.crop((x0, y0, x1, y1))
        buf = BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def review_page():
    """Flyer review page — per-page region review."""
    st.subheader("İncele & Düzelt")

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

    # --- Flyer/page selector ---
    try:
        flyers = get_flyers_for_week(week_id)
    except Exception as e:
        st.error(f"Afiş verileri yüklenirken hata oluştu: {e}")
        return
    if not flyers:
        st.info("Bu haftada afiş yok.")
        return

    flyer_labels = _build_flyer_label_map(flyers)
    selected_label = st.selectbox("Sayfa", list(flyer_labels.keys()), key="rv_flyer")
    flyer = flyer_labels[selected_label]
    flyer_id = flyer["flyer_id"]

    # --- Regions (v3) or clusters (v2 legacy) ---
    regions = get_regions_with_matches(flyer_id)
    using_legacy = False

    if not regions:
        # Fallback to old clusters
        regions = get_clusters_with_matches(flyer_id)
        if regions:
            using_legacy = True

    # Summary
    if regions:
        if using_legacy:
            st.caption("Eski (v2) cluster verisi gösteriliyor. Yeni veri için yeniden yükleme yapın.")
        statuses = [r.get("_match", {}).get("status", "unmatched") for r in regions]
        matched_c = statuses.count("matched")
        review_c = statuses.count("review")
        unmatched_c = statuses.count("unmatched")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Bölge", len(regions))
        c2.metric("Eşleşen", matched_c)
        c3.metric("İncelenmeli", review_c)
        c4.metric("Eşleşmedi", unmatched_c, delta_color="inverse")
    else:
        st.info("Bu sayfada bölge yok.")

    # --- Action buttons ---
    st.markdown("---")
    with st.expander("Sayfa İşlemleri", expanded=False):
        _render_page_actions(flyer, week_id)

    if not regions:
        return

    # --- Filter ---
    filter_status = st.multiselect(
        "Durum Filtresi",
        ["matched", "review", "unmatched"],
        default=["review", "unmatched"],
        key="rv_filter",
    )

    filtered = [
        r for r in regions
        if r.get("_match", {}).get("status", "unmatched") in filter_status
    ]

    if not filtered:
        st.info("Filtreye uyan bölge yok.")
        return

    st.markdown(f"**{len(filtered)} / {len(regions)} bölge gösteriliyor**")

    # Get image for crop previews
    image_bytes = _get_image_bytes(flyer)

    # Weekly products for dropdown
    products = get_weekly_products(week_id)
    product_options = {}
    if products:
        for p in products:
            kod = p.get("urun_kodu") or ""
            aciklama = (p.get("urun_aciklamasi") or "")[:50]
            label = f"{kod} — {aciklama}"
            product_options[label] = p

    for region in filtered:
        _render_region_card(region, image_bytes, product_options)


def _render_page_actions(flyer: dict, week_id: int):
    """Render page-level action buttons."""
    flyer_id = flyer["flyer_id"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Bölgeleri Yeniden Oluştur** (OCR'sız)")
        if st.button("Rebuild", key="rv_rebuild"):
            _rebuild_from_cache(flyer, week_id)

    with col2:
        st.markdown("**OCR'dan Yeniden Çalıştır**")
        if st.button("Re-OCR", key="rv_reocr"):
            image_bytes = _get_image_bytes(flyer)
            if not image_bytes:
                st.error("Görsel bulunamadı.")
                return
            products = get_weekly_products(week_id)
            if not products:
                st.error("Ürün listesi bulunamadı.")
                return
            excel_df = pd.DataFrame(products)
            result = process_page(
                flyer_id, image_bytes,
                flyer.get("img_w", 1), flyer.get("img_h", 1),
                excel_df, force_ocr=True,
            )
            st.success(
                f"Re-OCR: {result['words']} kelime, {result['prices']} fiyat, "
                f"{result['regions']} bölge, {result['matched']} eşleşti"
            )
            st.rerun()

    with col3:
        st.markdown("**Sayfayı Sıfırla**")
        if st.button("Reset", key="rv_reset", type="secondary"):
            delete_regions_for_flyer(flyer_id)
            delete_ocr_cache(flyer_id)
            st.success("Sayfa sıfırlandı. Yeniden işleyin.")
            st.rerun()


def _rebuild_from_cache(flyer: dict, week_id: int):
    """Rebuild regions from cached OCR words (no re-OCR)."""
    flyer_id = flyer["flyer_id"]
    img_w = flyer.get("img_w", 1)
    img_h = flyer.get("img_h", 1)

    words = get_ocr_cache(flyer_id)
    if words is None:
        st.error("OCR cache bulunamadı. Önce Re-OCR yapın.")
        return

    products = get_weekly_products(week_id)
    if not products:
        st.error("Ürün listesi bulunamadı.")
        return

    excel_df = pd.DataFrame(products)

    # Price detect → Region build → Match
    prices = find_prices(words, img_w, img_h)
    regions = build_regions(words, prices, img_w, img_h)

    delete_regions_for_flyer(flyer_id)
    saved = batch_insert_regions(flyer_id, regions)

    if not saved:
        st.warning("Bölge oluşturulamadı.")
        return

    match_results = match_regions(saved, excel_df)
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

    st.success(
        f"Rebuild: {len(saved)} bölge, "
        f"{stats['matched']} eşleşti, {stats['review']} incelenmeli"
    )
    st.rerun()


def _render_region_card(region: dict, image_bytes: bytes | None, product_options: dict):
    """Render a single region review card with crop preview."""
    rid = region.get("region_id") or region.get("cluster_id", "?")
    region_text = region.get("region_text") or region.get("ocr_text", "")
    price_value = region.get("price_value", "")
    match = region.get("_match", {})
    match_id = match.get("match_id")
    status = match.get("status", "unmatched")
    confidence = match.get("confidence", 0)
    matched_kod = match.get("urun_kodu") or ""
    matched_desc = match.get("urun_aciklamasi") or ""

    keys = _parse_keys(region.get("keys_json", {}))

    icon = {"matched": "++", "review": "!!", "unmatched": "XX"}.get(status, "..")
    label = f"[{icon}] #{rid} — {price_value} TL — {region_text[:50]}"

    with st.expander(label, expanded=(status != "matched")):
        col_crop, col_info, col_fix = st.columns([1, 1, 1])

        with col_crop:
            if image_bytes:
                crop = _crop_region(image_bytes, region)
                if crop:
                    st.image(crop, use_container_width=True)
                else:
                    st.caption("Crop başarısız")
            else:
                st.caption("Görsel yok")

        with col_info:
            signals = []
            if keys.get("model_codes"):
                signals.append(f"Model: {', '.join(keys['model_codes'][:3])}")
            if keys.get("brands"):
                signals.append(f"Marka: {', '.join(keys['brands'][:2])}")
            if keys.get("code4"):
                signals.append(f"Kod: {', '.join(keys['code4'][:3])}")
            if keys.get("sizes"):
                signals.append(f"Boyut: {', '.join(keys['sizes'][:2])}")

            st.markdown(f"""
**Fiyat:** {price_value or '—'}
**Sinyaller:** {' | '.join(signals) if signals else '—'}
**OCR:** {region_text[:150]}
**Eşleşen:** {matched_kod or '—'} — {matched_desc[:50] or '—'}
**Güven:** %{int(confidence * 100)} [{status}]
            """)

            # Show candidates
            candidates_json = match.get("candidates_json")
            if candidates_json:
                try:
                    cands = json.loads(candidates_json) if isinstance(candidates_json, str) else candidates_json
                    if cands and len(cands) > 1:
                        with st.popover("Top 5 Aday"):
                            for i, c in enumerate(cands[:5]):
                                st.text(f"{i+1}. {c.get('urun_kodu','')} — {c.get('urun_aciklamasi','')[:40]} (skor: {c.get('score',0)})")
                except Exception:
                    pass

        with col_fix:
            if not match_id:
                st.info("Match kaydı yok.")
                return

            st.markdown("**Manuel Düzeltme:**")

            options = ["(Değiştirme)"] + list(product_options.keys())
            selected = st.selectbox("Doğru Ürün", options, key=f"rv_fix_{rid}")

            if st.button("Kaydet", key=f"rv_save_{rid}", type="primary"):
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

            if status != "unmatched":
                if st.button("Eşleşme Yok", key=f"rv_unmatch_{rid}"):
                    update_match(match_id, {
                        "urun_kodu": None,
                        "urun_aciklamasi": None,
                        "confidence": 0,
                        "status": "unmatched",
                    })
                    st.rerun()
