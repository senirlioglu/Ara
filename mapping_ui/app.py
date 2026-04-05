"""Mapping Engine — Streamlit Thin Client.

This UI is a *shell*: all heavy lifting (PDF rendering, storage,
product import) is handled by the FastAPI backend.  The UI only:
  1. Fetches page images + product list from the backend (cached).
  2. Draws an interactive canvas for bbox selection (JS component).
  3. Sends mapping CRUD calls to the backend.
  4. Provides client-side product search (no API call per keystroke).
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import api_client as api
from .search import search_products

# ── Page config ──
st.set_page_config(page_title="Mapping Engine", layout="wide")

# ── Canvas component (declare once) ──
_CANVAS_HTML = Path(__file__).parent / "components" / "canvas.html"
_canvas_component = components.declare_component(
    "mapping_canvas",
    path=str(_CANVAS_HTML.parent),
)


def _canvas(image_url: str, saved_boxes: list[dict], active_bbox: dict | None, key: str):
    """Render the bbox-drawing canvas component."""
    return _canvas_component(
        image_url=image_url,
        saved_boxes=saved_boxes or [],
        active_bbox=active_bbox,
        key=key,
        default=None,
    )


# ══════════════════════════════════════════════════════════════════
#  Sidebar — Week selector + Upload controls
# ══════════════════════════════════════════════════════════════════

def _sidebar():
    with st.sidebar:
        st.title("Mapping Engine")

        # Week ID input
        week_id = st.text_input(
            "Hafta ID",
            value=st.session_state.get("week_id", ""),
            placeholder="örn. 2024-W10",
        )
        if week_id:
            st.session_state["week_id"] = week_id

        if not week_id:
            st.info("Hafta ID girin.")
            return

        # ── Status ──
        try:
            status = api.get_week_status(week_id)
            rend = status.get("render_status", {})
            prod = status.get("product_status", {})
            st.caption(
                f"Sayfalar: {rend.get('ready_pages', 0)}/{rend.get('total_pages', 0)}  ·  "
                f"Ürünler: {prod.get('count', 0)}"
            )
        except Exception:
            st.caption("Durum alınamadı")

        st.divider()

        # ── PDF Upload ──
        st.subheader("PDF Yükle")
        flyer_id = st.text_input("Flyer ID", placeholder="örn. migros-01")
        pdf_file = st.file_uploader("PDF dosyası", type=["pdf"], key="pdf_up")
        if st.button("PDF Yükle", disabled=not (flyer_id and pdf_file)):
            with st.spinner("PDF yükleniyor ve render ediliyor..."):
                try:
                    result = api.upload_pdf(
                        week_id, flyer_id, pdf_file.name, pdf_file.getvalue(),
                    )
                    st.success(f"{result.get('pages_rendered', '?')} sayfa render edildi.")
                    # Clear page cache so new pages appear
                    api.get_pages.clear()
                except Exception as e:
                    st.error(f"PDF yükleme hatası: {e}")

        st.divider()

        # ── Excel Upload ──
        st.subheader("Excel Yükle")
        excel_file = st.file_uploader("Excel dosyası", type=["xlsx", "xls"], key="xl_up")
        if st.button("Excel Yükle", disabled=not excel_file):
            with st.spinner("Ürünler yükleniyor..."):
                try:
                    result = api.upload_excel(
                        week_id, excel_file.name, excel_file.getvalue(),
                    )
                    st.success(f"{result.get('imported', '?')} ürün yüklendi.")
                    api.get_products.clear()
                except Exception as e:
                    st.error(f"Excel yükleme hatası: {e}")


# ══════════════════════════════════════════════════════════════════
#  Main mapping view
# ══════════════════════════════════════════════════════════════════

def _mapping_view():
    week_id = st.session_state.get("week_id")
    if not week_id:
        st.info("Sol panelden hafta ID girin.")
        return

    # ── Load pages ──
    try:
        pages = api.get_pages(week_id)
    except Exception as e:
        st.error(f"Sayfalar yüklenemedi: {e}")
        return

    if not pages:
        st.warning("Bu hafta için sayfa bulunamadı. Önce PDF yükleyin.")
        return

    # ── Load products (one-shot, cached) ──
    try:
        products = api.get_products(week_id)
    except Exception:
        products = []

    # ── Page selector ──
    page_options = [
        f"{p['flyer_id']} — Sayfa {p['page_no']}"
        for p in pages
        if p.get("image_url")
    ]
    ready_pages = [p for p in pages if p.get("image_url")]

    if not ready_pages:
        st.warning("Render edilmiş sayfa yok.")
        return

    col_nav, col_info = st.columns([3, 1])
    with col_nav:
        sel_idx = st.selectbox(
            "Sayfa",
            range(len(page_options)),
            format_func=lambda i: page_options[i],
            key="page_sel",
        )
    page = ready_pages[sel_idx]
    flyer_id = page["flyer_id"]
    page_no = page["page_no"]
    image_url = api.image_url(page["image_url"])

    with col_info:
        st.caption(f"Flyer: {flyer_id} | Sayfa: {page_no}")

    # ── Page change detection ──
    page_key = f"{flyer_id}_{page_no}"
    prev_page_key = st.session_state.get("_mt_page_key")
    if prev_page_key != page_key:
        st.session_state["_mt_page_key"] = page_key
        st.session_state.pop("_mt_active_bbox", None)

    # ── Load mappings for this page ──
    try:
        mappings = api.get_mappings(week_id, flyer_id, page_no)
    except Exception:
        mappings = []

    saved_boxes = [
        {
            "x0": m["bbox"]["x0"], "y0": m["bbox"]["y0"],
            "x1": m["bbox"]["x1"], "y1": m["bbox"]["y1"],
            "label": m.get("urun_kod") or "",
        }
        for m in mappings
    ]

    # ── Two-column layout: Canvas | Controls ──
    col_canvas, col_right = st.columns([3, 2])

    with col_canvas:
        active_bbox = st.session_state.get("_mt_active_bbox")
        canvas_key = f"bbox_{flyer_id}_p{page_no}"

        result = _canvas(
            image_url=image_url,
            saved_boxes=saved_boxes,
            active_bbox=active_bbox,
            key=canvas_key,
        )

        # Process canvas result
        if result and isinstance(result, dict) and result.get("x0") is not None:
            bbox = result
            if bbox != st.session_state.get("_mt_active_bbox"):
                st.session_state["_mt_active_bbox"] = bbox
                st.rerun()
        elif result is None and active_bbox is None:
            bbox = None
        else:
            bbox = active_bbox

    with col_right:
        _mapping_controls(week_id, flyer_id, page_no, bbox, products, mappings)


# ══════════════════════════════════════════════════════════════════
#  Right panel — product search + mapping controls + mapping list
# ══════════════════════════════════════════════════════════════════

def _mapping_controls(
    week_id: str,
    flyer_id: str,
    page_no: int,
    bbox: dict | None,
    products: list[dict],
    mappings: list[dict],
):
    if bbox:
        st.success(
            f"Seçili kutu: ({bbox['x0']:.3f}, {bbox['y0']:.3f}) → "
            f"({bbox['x1']:.3f}, {bbox['y1']:.3f})"
        )

        # ── Product search ──
        st.subheader("Ürün Ara")
        query = st.text_input(
            "Ürün kodu veya adı",
            key="prod_search",
            placeholder="Kod veya isim yazın...",
        )

        if query:
            results = search_products(query, products, limit=15)
            if results:
                for i, p in enumerate(results):
                    kod = p["urun_kod"]
                    ad = p.get("urun_ad") or ""
                    score = p.get("score", 0)
                    label = f"{kod} — {ad}" if ad else kod

                    if st.button(
                        label,
                        key=f"pick_{i}_{kod}",
                        help=f"Skor: {score}",
                        use_container_width=True,
                    ):
                        _save_mapping(week_id, flyer_id, page_no, bbox, kod, ad)
            else:
                st.caption("Sonuç bulunamadı")

        st.divider()

        # ── Manual entry ──
        st.subheader("Manuel Giriş")
        manual_kod = st.text_input("Ürün Kodu", key="manual_kod")
        manual_ad = st.text_input("Ürün Adı (opsiyonel)", key="manual_ad")
        if st.button("Kaydet", disabled=not manual_kod, key="btn_manual_save"):
            _save_mapping(
                week_id, flyer_id, page_no, bbox,
                manual_kod.strip(), manual_ad.strip() or None, source="manual",
            )

    else:
        st.info("Sayfada bir kutu çizin.")

    # ── Existing mappings list ──
    st.divider()
    st.subheader(f"Eşleştirmeler ({len(mappings)})")

    if not mappings:
        st.caption("Bu sayfada eşleştirme yok.")
        return

    for m in mappings:
        mb = m["bbox"]
        label = m.get("urun_kod") or "?"
        ad = m.get("urun_ad") or ""
        display = f"**{label}** — {ad}" if ad else f"**{label}**"

        col_txt, col_del = st.columns([4, 1])
        with col_txt:
            st.markdown(
                f"{display}  \n"
                f"<small style='color:gray'>"
                f"({mb['x0']:.3f},{mb['y0']:.3f})→({mb['x1']:.3f},{mb['y1']:.3f}) "
                f"| {m.get('source', '')}</small>",
                unsafe_allow_html=True,
            )
        with col_del:
            if st.button("Sil", key=f"del_{m['id']}"):
                try:
                    api.delete_mapping(week_id, m["id"])
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def _save_mapping(
    week_id: str, flyer_id: str, page_no: int,
    bbox: dict, urun_kod: str, urun_ad: str | None = None,
    source: str = "excel",
):
    """Save mapping via API and rerun."""
    try:
        api.save_mapping(
            week_id, flyer_id, page_no,
            bbox=bbox,
            urun_kod=urun_kod,
            urun_ad=urun_ad,
            source=source,
        )
        st.session_state.pop("_mt_active_bbox", None)
        st.session_state.pop("prod_search", None)
        st.session_state.pop("manual_kod", None)
        st.session_state.pop("manual_ad", None)
        st.rerun()
    except Exception as e:
        st.error(f"Kaydetme hatası: {e}")


# ══════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════

def main():
    _sidebar()
    _mapping_view()


if __name__ == "__main__":
    main()
