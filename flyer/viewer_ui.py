"""Viewer UI — show flyer image with clickable hotspot overlays.

Click hotspot → run_search(urun_kodu) for stock lookup.
"""

from __future__ import annotations

import base64

import streamlit as st
import streamlit.components.v1 as components

from flyer.db import (
    get_weeks,
    get_flyers_for_week,
    get_clusters_with_matches,
    get_supabase,
)


def _fetch_image_bytes(url: str) -> bytes | None:
    """Download image from URL."""
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
    pick_cluster_id = params.get("pick_cluster")
    if pick_cluster_id:
        _handle_pick(int(pick_cluster_id))
        return

    # --- Week + Flyer selection ---
    weeks = get_weeks(limit=20)
    if not weeks:
        st.info("Henuz yuklenmus afis bulunmuyor.")
        return

    week_map = {f"Hafta {w['week_date']}": w["week_id"] for w in weeks}
    selected_week_label = st.selectbox("Hafta Secin", list(week_map.keys()))
    week_id = week_map[selected_week_label]

    flyers = get_flyers_for_week(week_id)
    if not flyers:
        st.info("Bu haftada afis yok.")
        return

    flyer_map = {f["filename"]: f for f in flyers}
    selected_fname = st.selectbox("Afis Secin", list(flyer_map.keys()))
    flyer = flyer_map[selected_fname]
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

    # --- Get clusters with matches ---
    clusters = get_clusters_with_matches(flyer_id)
    matched_clusters = [
        c for c in clusters
        if c.get("_match", {}).get("status") == "matched"
    ]

    if not matched_clusters:
        st.warning("Bu afiste henuz tiklanabilir alan tanimlanmamis.")
        st.image(image_bytes, use_container_width=True)
        return

    # --- Render overlay ---
    html = _build_overlay_html(image_bytes, matched_clusters)
    components.html(html, height=1200, scrolling=True)
    st.caption(f"{len(matched_clusters)} tiklanabilir urun alani mevcut.")


def _build_overlay_html(image_bytes: bytes, clusters: list[dict]) -> str:
    """Build HTML with clickable hotspot overlays."""
    img_b64 = base64.b64encode(image_bytes).decode()

    # Detect image type
    if image_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    else:
        mime = "image/jpeg"

    hotspot_divs = []
    for cl in clusters:
        x0 = cl.get("x0", 0) * 100
        y0 = cl.get("y0", 0) * 100
        w = (cl.get("x1", 0) - cl.get("x0", 0)) * 100
        h = (cl.get("y1", 0) - cl.get("y0", 0)) * 100
        cluster_id = cl.get("cluster_id", 0)

        match = cl.get("_match", {})
        desc = (match.get("urun_aciklamasi") or "")[:60]
        fiyat = match.get("afis_fiyat") or ""
        tooltip = desc
        if fiyat:
            tooltip += f" - {fiyat}"

        hotspot_divs.append(f"""
        <div class="hotspot"
             title="{tooltip}"
             style="left:{x0:.2f}%; top:{y0:.2f}%; width:{w:.2f}%; height:{h:.2f}%;"
             onclick="pickCluster({cluster_id})">
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
    </style></head><body>
    <div class="wrap">
        <img src="data:{mime};base64,{img_b64}" />
        {"".join(hotspot_divs)}
    </div>
    <script>
    function pickCluster(cid) {{
        var url = new URL(window.parent.location.href);
        url.searchParams.set('pick_cluster', cid);
        url.searchParams.set('mode', 'flyer');
        window.parent.location.href = url.toString();
    }}
    </script>
    </body></html>
    """


def _handle_pick(cluster_id: int):
    """Handle hotspot click — show product info + trigger search."""
    client = get_supabase()
    if not client:
        st.error("Veritabani baglantisi yok")
        return

    # Get match for this cluster
    result = (
        client.table("flyer_matches")
        .select("*")
        .eq("cluster_id", cluster_id)
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
            {"<span style='background: #f0f1f6; color:#555; padding:6px 16px; border-radius:20px; font-size:0.85rem;'>Kod: " + urun_kodu + "</span>" if urun_kodu else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Back button
    if st.button("Afise Don"):
        st.query_params.pop("pick_cluster", None)
        st.rerun()

    # Trigger search
    if search_term:
        st.markdown("---")
        st.subheader("Stok Sonuclari")
        from urun_ara_app import ara_urun, goster_sonuclar
        with st.spinner("Araniyor..."):
            df = ara_urun(search_term)
            goster_sonuclar(df, search_term)
    else:
        st.warning("Bu urun icin arama terimi tanimlanmamis.")
