"""Viewer UI — store staff flyer viewer with clickable hotspot overlays.

Click region hotspot → show matched product info → run_search(urun_kodu).
"""

from __future__ import annotations

import base64
import json

import streamlit as st
import streamlit.components.v1 as components

from flyer.storage_supabase import (
    get_weeks,
    get_flyers_for_week,
    get_regions_with_matches,
    get_supabase,
)


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


def _fetch_image_bytes(url: str) -> bytes | None:
    if not url:
        return None
    try:
        import httpx
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def viewer_page():
    """Main flyer viewer for store staff."""
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem 1rem;
        border-radius: 0 0 20px 20px;
        margin: -1rem -1rem 1.2rem -1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    ">
        <h1 style="color: white; font-size: 1.6rem; font-weight: 700; margin: 0;">
            Haftalik Afisler
        </h1>
        <p style="color: rgba(255,255,255,0.85); font-size: 0.85rem; margin: 0.4rem 0 0 0;">
            Afisteki urune dokunarak stok bilgisini gorun
        </p>
    </div>
    """, unsafe_allow_html=True)

    # --- Check if user picked a hotspot ---
    params = st.query_params
    pick_region_id = params.get("pick_region")
    if pick_region_id:
        _handle_pick(int(pick_region_id))
        return

    # Legacy support for old pick_cluster param
    pick_cluster_id = params.get("pick_cluster")
    if pick_cluster_id:
        _handle_pick_legacy(int(pick_cluster_id))
        return

    # --- Week + Flyer selection ---
    weeks = get_weeks(limit=20)
    if not weeks:
        st.info("Henuz yuklenmus afis bulunmuyor.")
        return

    week_map = {f"Hafta {w['week_date']}": w["week_id"] for w in weeks}
    selected_week_label = st.selectbox("Hafta Secin", list(week_map.keys()))
    week_id = week_map[selected_week_label]

    try:
        flyers = get_flyers_for_week(week_id)
    except Exception as e:
        st.error(f"Afiş verileri yüklenirken hata oluştu: {e}")
        return
    if not flyers:
        st.info("Bu haftada afis yok.")
        return

    flyer_labels = _build_flyer_label_map(flyers)
    selected_label = st.selectbox("Afis Secin", list(flyer_labels.keys()))
    flyer = flyer_labels[selected_label]
    flyer_id = flyer["flyer_id"]

    # --- Get image bytes ---
    flyer_cache = st.session_state.get("flyer_cache", {})
    image_bytes = flyer_cache.get(flyer_id)

    if not image_bytes:
        image_url = flyer.get("image_url", "")
        if image_url:
            image_bytes = _fetch_image_bytes(image_url)

    if not image_bytes:
        st.error("Gorsel yuklenemedi.")
        return

    # --- Get regions with matches ---
    regions = get_regions_with_matches(flyer_id)
    matched_regions = [
        r for r in regions
        if r.get("_match", {}).get("status") == "matched"
    ]

    if not matched_regions:
        st.warning("Bu sayfada henuz tiklanabilir alan tanimlanmamis.")
        st.image(image_bytes, use_container_width=True)
        return

    # --- Render overlay ---
    html = _build_overlay_html(image_bytes, matched_regions)
    components.html(html, height=1200, scrolling=True)
    st.caption(f"{len(matched_regions)} tiklanabilir urun alani mevcut.")


def _build_overlay_html(image_bytes: bytes, regions: list[dict]) -> str:
    """Build HTML with clickable hotspot overlays."""
    img_b64 = base64.b64encode(image_bytes).decode()

    if image_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    else:
        mime = "image/jpeg"

    hotspot_divs = []
    for r in regions:
        x0 = r.get("x0", 0) * 100
        y0 = r.get("y0", 0) * 100
        w = (r.get("x1", 0) - r.get("x0", 0)) * 100
        h = (r.get("y1", 0) - r.get("y0", 0)) * 100
        region_id = r.get("region_id", 0)
        price = r.get("price_value", "")

        match = r.get("_match", {})
        desc = (match.get("urun_aciklamasi") or "")[:60]
        fiyat = match.get("afis_fiyat") or price
        tooltip = desc
        if fiyat:
            tooltip += f" - {fiyat} TL"

        hotspot_divs.append(f"""
        <div class="hotspot"
             title="{tooltip}"
             style="left:{x0:.2f}%; top:{y0:.2f}%; width:{w:.2f}%; height:{h:.2f}%;"
             onclick="pickRegion({region_id})">
            <span class="price-tag">{price}</span>
        </div>
        """)

    return f"""
    <!DOCTYPE html><html><head><style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    .wrap {{ position:relative; display:inline-block; width:100%; line-height:0; }}
    .wrap img {{ width:100%; height:auto; display:block; }}
    .hotspot {{
        position:absolute;
        border:2px solid rgba(102,126,234,0.5);
        border-radius:8px;
        background:rgba(102,126,234,0.08);
        cursor:pointer;
        transition:all .2s;
        z-index:10;
    }}
    .hotspot:hover {{
        background:rgba(102,126,234,0.25);
        border-color:rgba(102,126,234,1);
        box-shadow:0 0 12px rgba(102,126,234,0.4);
    }}
    .price-tag {{
        position:absolute;
        bottom:2px; right:4px;
        font-size:10px;
        color:white;
        background:rgba(102,126,234,0.7);
        padding:1px 5px;
        border-radius:4px;
        pointer-events:none;
    }}
    </style></head><body>
    <div class="wrap">
        <img src="data:{mime};base64,{img_b64}" />
        {"".join(hotspot_divs)}
    </div>
    <script>
    function pickRegion(rid) {{
        var url = new URL(window.parent.location.href);
        url.searchParams.set('pick_region', rid);
        url.searchParams.set('mode', 'flyer');
        window.parent.location.href = url.toString();
    }}
    </script>
    </body></html>
    """


def _handle_pick(region_id: int):
    """Handle region hotspot click — show product info + trigger search."""
    client = get_supabase()
    if not client:
        st.error("Veritabani baglantisi yok")
        return

    result = (
        client.table("flyer_matches")
        .select("*")
        .eq("region_id", region_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        st.error("Urun bilgisi bulunamadi")
        return

    match = result.data[0]
    urun_kodu = match.get("urun_kodu") or ""
    urun_aciklamasi = match.get("urun_aciklamasi") or ""
    afis_fiyat = match.get("afis_fiyat") or ""
    search_term = urun_kodu

    # Also get price from region
    region_result = (
        client.table("flyer_regions")
        .select("price_value")
        .eq("region_id", region_id)
        .limit(1)
        .execute()
    )
    detected_price = ""
    if region_result.data:
        detected_price = region_result.data[0].get("price_value", "")

    # Product info card
    st.markdown(f"""
    <div style="
        background: white;
        border: 2px solid #667eea;
        border-radius: 16px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    ">
        <div style="font-weight: 700; font-size: 1.1rem; color: #1e3a5f; margin-bottom: 0.5rem;">
            {urun_aciklamasi}
        </div>
        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
            {"<span style='background: linear-gradient(135deg,#00b894,#00cec9); color:white; padding:6px 16px; border-radius:20px; font-weight:700;'>Afis Fiyat: " + afis_fiyat + "</span>" if afis_fiyat else ""}
            {"<span style='background: #ff7675; color:white; padding:6px 16px; border-radius:20px; font-weight:700;'>OCR Fiyat: " + detected_price + "</span>" if detected_price else ""}
            {"<span style='background: #f0f1f6; color:#555; padding:6px 16px; border-radius:20px; font-size:0.85rem;'>Kod: " + urun_kodu + "</span>" if urun_kodu else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Afise Don"):
        st.query_params.pop("pick_region", None)
        st.rerun()

    if search_term:
        st.markdown("---")
        st.subheader("Stok Sonuclari")
        from urun_ara_app import ara_urun, goster_sonuclar
        with st.spinner("Araniyor..."):
            df = ara_urun(search_term)
            goster_sonuclar(df, search_term)
    else:
        st.warning("Bu urun icin arama terimi tanimlanmamis.")


def _handle_pick_legacy(cluster_id: int):
    """Legacy support: handle old pick_cluster param by redirecting."""
    st.warning("Eski cluster sistemi. Yeni sistem icin tekrar yukleme yapın.")
    if st.button("Afise Don"):
        st.query_params.pop("pick_cluster", None)
        st.rerun()
