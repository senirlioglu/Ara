"""Poster Viewer – Streamlit UI for store staff.

Renders the poster page as an image with clickable hotspot overlays.
When a hotspot is clicked, it triggers the existing product search.
"""

from __future__ import annotations

import base64

import streamlit as st
import streamlit.components.v1 as components

from poster.db import get_posters, get_hotspots_for_page, get_supabase


def _fetch_pdf_bytes(pdf_url: str) -> bytes | None:
    """Download PDF from URL or Supabase Storage."""
    if not pdf_url:
        return None
    try:
        import httpx
        resp = httpx.get(pdf_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _render_poster_with_hotspots(
    png_bytes: bytes,
    hotspots: list[dict],
    container_id: str = "poster-container",
) -> str:
    """Build HTML that overlays clickable hotspot divs on the poster image.

    Hotspots use normalised coords (0..1) → CSS percentage positioning.
    On click, navigates by setting ?pick=<poster_item_id> query param.
    """
    img_b64 = base64.b64encode(png_bytes).decode()

    hotspot_divs = []
    for hs in hotspots:
        x0 = hs.get("x0", 0) * 100
        y0 = hs.get("y0", 0) * 100
        w = (hs.get("x1", 0) - hs.get("x0", 0)) * 100
        h = (hs.get("y1", 0) - hs.get("y0", 0)) * 100
        item_id = hs.get("poster_item_id") or hs.get("id", 0)

        # Tooltip text
        urun_aciklamasi = hs.get("urun_aciklamasi", "") or ""
        afis_fiyat = hs.get("afis_fiyat", "") or ""
        tooltip = urun_aciklamasi[:60]
        if afis_fiyat:
            tooltip += f" – {afis_fiyat}"

        hotspot_divs.append(f"""
        <div class="hotspot"
             data-item-id="{item_id}"
             title="{tooltip}"
             style="
                left: {x0:.2f}%;
                top: {y0:.2f}%;
                width: {w:.2f}%;
                height: {h:.2f}%;
             "
             onclick="pickItem({item_id})">
        </div>
        """)

    hotspots_html = "\n".join(hotspot_divs)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
        #{container_id} {{
            position: relative;
            display: inline-block;
            width: 100%;
            line-height: 0;
        }}
        #{container_id} img {{
            width: 100%;
            height: auto;
            display: block;
        }}
        .hotspot {{
            position: absolute;
            border: 2px solid rgba(102, 126, 234, 0.5);
            border-radius: 8px;
            background: rgba(102, 126, 234, 0.08);
            cursor: pointer;
            transition: all 0.2s ease;
            z-index: 10;
        }}
        .hotspot:hover {{
            background: rgba(102, 126, 234, 0.25);
            border-color: rgba(102, 126, 234, 0.9);
            box-shadow: 0 0 12px rgba(102, 126, 234, 0.4);
        }}
    </style>
    </head>
    <body>
    <div id="{container_id}">
        <img src="data:image/png;base64,{img_b64}" alt="Poster" />
        {hotspots_html}
    </div>
    <script>
    function pickItem(itemId) {{
        // Navigate parent Streamlit app with pick= query param
        var url = new URL(window.parent.location.href);
        url.searchParams.set('pick', itemId);
        url.searchParams.set('mode', 'poster');
        window.parent.location.href = url.toString();
    }}
    </script>
    </body>
    </html>
    """


def poster_viewer_page():
    """Main poster viewer page for store staff."""
    from poster.hotspot_gen import render_page_image

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
            Haftalık Afişler
        </h1>
        <p style="color: rgba(255,255,255,0.85); font-size: 0.85rem; margin: 0.4rem 0 0 0;">
            Afişteki ürüne dokunarak stok bilgisini görün
        </p>
    </div>
    """, unsafe_allow_html=True)

    # --- Check if user picked a hotspot ---
    params = st.query_params
    pick_id = params.get("pick")
    if pick_id:
        _handle_pick(int(pick_id))
        return

    # --- Poster selection ---
    posters = get_posters(limit=20)
    if not posters:
        st.info("Henüz yüklenmiş afiş bulunmuyor.")
        return

    poster_options = {f"{p['title']} ({p['week_date']})": p for p in posters}
    selected_label = st.selectbox("Afiş Seçin", list(poster_options.keys()))
    poster = poster_options[selected_label]
    poster_id = poster["poster_id"]
    page_count = poster.get("page_count", 1) or 1

    # Page selector
    if page_count > 1:
        page_no = st.slider("Sayfa", 1, page_count, 1)
    else:
        page_no = 1

    # Fetch PDF
    pdf_url = poster.get("pdf_url", "")
    pdf_bytes = _fetch_pdf_bytes(pdf_url)
    if not pdf_bytes:
        st.error("PDF dosyası yüklenemedi. Lütfen admin ile iletişime geçin.")
        return

    # Render page image
    try:
        png_bytes = render_page_image(pdf_bytes, page_no, dpi=150)
    except Exception as e:
        st.error(f"Sayfa render hatası: {e}")
        return

    # Get hotspots
    hotspots = get_hotspots_for_page(poster_id, page_no)

    if not hotspots:
        st.warning("Bu sayfada henüz tıklanabilir alan tanımlanmamış.")
        # Still show the image
        st.image(png_bytes, use_container_width=True)
        return

    # Render with hotspot overlays
    html_content = _render_poster_with_hotspots(png_bytes, hotspots)

    # Estimate height based on image aspect ratio
    # Standard A4-ish poster: ~1.4 ratio
    estimated_height = 1200
    components.html(html_content, height=estimated_height, scrolling=True)

    st.caption(f"{len(hotspots)} tıklanabilir ürün alanı mevcut. Ürüne dokunun.")


def _handle_pick(poster_item_id: int):
    """Handle hotspot click – show product info and trigger search."""
    client = get_supabase()
    if not client:
        st.error("Veritabanı bağlantısı yok")
        return

    # Fetch the poster item
    result = (
        client.table("poster_items")
        .select("*")
        .eq("id", poster_item_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        st.error("Ürün bilgisi bulunamadı")
        return

    item = result.data[0]
    urun_aciklamasi = item.get("urun_aciklamasi") or ""
    afis_fiyat = item.get("afis_fiyat") or ""
    search_term = item.get("search_term") or item.get("urun_kodu") or ""
    urun_kodu = item.get("urun_kodu") or ""

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
            {"<span style='background: linear-gradient(135deg,#00b894,#00cec9); color:white; padding:6px 16px; border-radius:20px; font-weight:700;'>Afiş Fiyat: " + afis_fiyat + "</span>" if afis_fiyat else ""}
            {"<span style='background: #f0f1f6; color:#555; padding:6px 16px; border-radius:20px; font-size:0.85rem;'>Kod: " + urun_kodu + "</span>" if urun_kodu else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Back button
    if st.button("← Afişe Dön"):
        # Clear pick param and go back
        st.query_params.pop("pick", None)
        st.rerun()

    # Trigger search using existing ara_urun function
    if search_term:
        st.markdown("---")
        st.subheader("Stok Sonuçları")

        # Import the existing search function from the main app
        from urun_ara_app import ara_urun, goster_sonuclar

        with st.spinner("Aranıyor..."):
            df = ara_urun(search_term)
            goster_sonuclar(df, search_term)
    else:
        st.warning("Bu ürün için arama terimi tanımlanmamış. Admin panelinden eşleştirme yapılmalı.")
