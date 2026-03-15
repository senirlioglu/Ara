"""Flyer Mapping Tool — manual bbox selection + OCR suggestions.

Run:  streamlit run app.py
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pdf_render import render_pdf_bytes_to_pages
from vision_ocr import init_gcp_credentials, ocr_crop, make_ocr_cache_key
from suggest_match import top_k_candidates
from storage import init_db, save_mapping, list_mappings, delete_mapping
from viewer import render_viewer, run_search

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Flyer Mapping Tool", layout="wide")
init_db()

try:
    cred_path = init_gcp_credentials()
    if cred_path:
        log.info("GCP creds ready")
except Exception as e:
    log.warning("GCP creds init skipped: %s", e)


# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "pages": [],
    "excel_df": None,
    "week_id": datetime.now().strftime("%Y-%m-%d"),
    "selected_page_idx": 0,
    "last_bbox": None,
    "last_ocr_text": None,
    "ocr_cache": {},
    "manual_mode": False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

CANVAS_HTML = (Path(__file__).resolve().parent / "components" / "canvas.html").read_text()


def _load_week(excel_file, pdf_files, zoom):
    """Parse Excel + render all PDF pages into session state."""
    if excel_file:
        try:
            df = pd.read_excel(excel_file)
            # Normalize column names
            col_map = {}
            for c in df.columns:
                cu = str(c).strip().upper()
                if "KOD" in cu:
                    col_map[c] = "urun_kodu"
                elif "AÇIKLAMA" in cu or "ACIKLAMA" in cu:
                    col_map[c] = "urun_aciklamasi"
                elif "FİYAT" in cu or "FIYAT" in cu:
                    col_map[c] = "afis_fiyat"
            if col_map:
                df = df.rename(columns=col_map)
            st.session_state["excel_df"] = df
        except Exception as e:
            st.error(f"Excel okuma hatası: {e}")
            return

    if pdf_files:
        all_pages = []
        for f in pdf_files:
            raw = f.read()
            rendered = render_pdf_bytes_to_pages(raw, zoom=zoom)
            for p in rendered:
                all_pages.append({
                    "flyer_id": str(uuid.uuid4())[:8],
                    "flyer_filename": f.name,
                    "page_no": p["page_no"],
                    "png_bytes": p["png_bytes"],
                    "w": p["w"],
                    "h": p["h"],
                })
        st.session_state["pages"] = all_pages

    # Reset selection state
    st.session_state["last_bbox"] = None
    st.session_state["last_ocr_text"] = None
    st.session_state["manual_mode"] = False


def _render_canvas(page: dict):
    """Render the page image with bbox drawing canvas."""
    b64 = base64.b64encode(page["png_bytes"]).decode()
    img_src = f"data:image/png;base64,{b64}"

    # Build saved boxes for overlay
    saved = list_mappings(
        st.session_state["week_id"],
        page["flyer_filename"],
        page["page_no"],
    )
    saved_boxes = [
        {
            "x0": m["x0"], "y0": m["y0"], "x1": m["x1"], "y1": m["y1"],
            "label": m.get("urun_kodu") or "?",
        }
        for m in saved
    ]

    html = CANVAS_HTML.replace("__IMG_SRC__", img_src)
    html = html.replace("__SAVED_BOXES__", json.dumps(saved_boxes))

    result = components.html(html, height=820, scrolling=True, key=f"canvas_{page['flyer_id']}")

    # Handle component return value (bbox or null)
    if result and isinstance(result, dict) and "x0" in result:
        st.session_state["last_bbox"] = result
        st.session_state["last_ocr_text"] = None
        st.session_state["manual_mode"] = False
    elif result is None and st.session_state.get("_canvas_cleared"):
        st.session_state["last_bbox"] = None
        st.session_state["last_ocr_text"] = None


def _render_controls(page: dict):
    """Right panel: OCR, suggestions, manual mode, save."""
    bbox = st.session_state["last_bbox"]

    if not bbox:
        st.info("Soldaki resimde kutu çizin, ardından 'Seçimi Kullan' basın.")
        return

    st.markdown(f"**Seçim:** x0={bbox['x0']:.3f} y0={bbox['y0']:.3f} "
                f"x1={bbox['x1']:.3f} y1={bbox['y1']:.3f}")

    if st.button("Seçimi Temizle", key="btn_clear_bbox"):
        st.session_state["last_bbox"] = None
        st.session_state["last_ocr_text"] = None
        st.session_state["manual_mode"] = False
        st.rerun()

    st.markdown("---")

    # --- OCR ---
    ocr_text = st.session_state["last_ocr_text"]

    if st.button("OCR Çalıştır", type="primary", key="btn_ocr"):
        cache_key = make_ocr_cache_key(page["png_bytes"], bbox)
        cached = st.session_state["ocr_cache"].get(cache_key)
        if cached is not None:
            ocr_text = cached
            st.caption("(Cache'den)")
        else:
            with st.spinner("OCR çalışıyor..."):
                try:
                    ocr_text = ocr_crop(page["png_bytes"], bbox, page["w"], page["h"])
                    st.session_state["ocr_cache"][cache_key] = ocr_text
                except Exception as e:
                    st.error(f"OCR hatası: {e}")
                    ocr_text = ""
        st.session_state["last_ocr_text"] = ocr_text

    if ocr_text:
        st.text_area("OCR Metin", ocr_text, height=100, disabled=True, key="ta_ocr")

    # --- Suggestions / Manual Mode ---
    if ocr_text is not None:
        if not st.session_state["manual_mode"]:
            _render_suggestions(page, bbox, ocr_text)
        else:
            _render_manual_mode(page, bbox, ocr_text)


def _render_suggestions(page: dict, bbox: dict, ocr_text: str):
    """Show top-k suggestions and accept/reject buttons."""
    excel_df = st.session_state["excel_df"]
    candidates = []
    if ocr_text and excel_df is not None:
        candidates = top_k_candidates(ocr_text, excel_df, k=5)

    if candidates:
        st.markdown("**Öneriler:**")
        options = [
            f'{c["urun_kodu"]} — {c["urun_aciklamasi"]} (skor: {c["score"]})'
            for c in candidates
        ]
        choice = st.radio("Öneri seç:", options, key="radio_suggest")
        chosen_idx = options.index(choice)
        chosen = candidates[chosen_idx]

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Eşleştir (Öneri ile)", type="primary", key="btn_accept"):
                _save(page, bbox, ocr_text, chosen, source="suggested")
        with col_b:
            if st.button("Yok / Bulamadım", key="btn_reject"):
                st.session_state["manual_mode"] = True
                st.rerun()
    else:
        st.warning("Öneri bulunamadı." if ocr_text else "OCR metni boş.")
        if st.button("Manuel Eşleştirme", key="btn_manual_fallback"):
            st.session_state["manual_mode"] = True
            st.rerun()


def _render_manual_mode(page: dict, bbox: dict, ocr_text: str):
    """Manual matching: Excel dropdown + product code entry."""
    st.markdown("### Manuel Eşleştirme")

    if st.button("Geri Dön (Öneriler)", key="btn_back_suggest"):
        st.session_state["manual_mode"] = False
        st.rerun()

    st.markdown("---")

    # --- Mode B: Excel Manual Selection ---
    st.markdown("**Excel'den Seç:**")
    excel_df = st.session_state["excel_df"]
    if excel_df is not None and not excel_df.empty:
        search_q = st.text_input("Ara (kod veya açıklama):", key="inp_excel_search")

        filtered = excel_df.copy()
        if search_q:
            q = search_q.upper()
            mask = filtered.apply(
                lambda row: q in str(row.get("urun_kodu", "")).upper()
                or q in str(row.get("urun_aciklamasi", "")).upper(),
                axis=1,
            )
            filtered = filtered[mask]

        if not filtered.empty:
            items = []
            for _, row in filtered.head(50).iterrows():
                kod = str(row.get("urun_kodu", "")).strip()
                acik = str(row.get("urun_aciklamasi", "")).strip()
                fiyat = str(row.get("afis_fiyat", "")).strip()
                items.append({
                    "label": f"{kod} — {acik}",
                    "urun_kodu": kod,
                    "urun_aciklamasi": acik,
                    "afis_fiyat": fiyat or None,
                })

            labels = [it["label"] for it in items]
            picked = st.selectbox("Ürün:", labels, key="sel_excel_manual")
            picked_item = items[labels.index(picked)]

            if st.button("Kaydet (Excel'den)", type="primary", key="btn_save_excel"):
                _save(page, bbox, ocr_text, picked_item, source="excel_manual")
        else:
            st.caption("Eşleşen ürün yok.")
    else:
        st.caption("Excel yüklenmedi.")

    st.markdown("---")

    # --- Mode C: Product Code Entry ---
    st.markdown("**Ürün Kodu Gir:**")
    code_input = st.text_input("Ürün Kodu:", key="inp_code_manual")
    desc_input = st.text_input("Açıklama (opsiyonel):", key="inp_desc_manual")

    col_v, col_s = st.columns(2)
    with col_v:
        if st.button("Doğrula (DB)", key="btn_validate"):
            if code_input:
                result = run_search(code_input.strip())
                if result:
                    st.success(f'Bulundu: {result.get("urun_kodu")}')
                    st.session_state["_validated_code"] = True
                else:
                    st.warning("DB'de bulunamadı — yine de kaydedebilirsiniz.")
                    st.session_state["_validated_code"] = False

    with col_s:
        if st.button("Kaydet (Kod ile)", key="btn_save_code"):
            if code_input:
                validated = st.session_state.get("_validated_code", False)
                _save(
                    page, bbox, ocr_text,
                    {
                        "urun_kodu": code_input.strip(),
                        "urun_aciklamasi": desc_input.strip() or None,
                        "afis_fiyat": None,
                    },
                    source="code_manual",
                    status="matched" if validated else "unverified",
                )
            else:
                st.warning("Ürün kodu girin.")


def _save(page: dict, bbox: dict, ocr_text: str, product: dict,
          source: str, status: str = "matched"):
    """Persist a mapping to SQLite."""
    m = {
        "week_id": st.session_state["week_id"],
        "flyer_filename": page["flyer_filename"],
        "page_no": page["page_no"],
        "x0": bbox["x0"],
        "y0": bbox["y0"],
        "x1": bbox["x1"],
        "y1": bbox["y1"],
        "urun_kodu": product.get("urun_kodu"),
        "urun_aciklamasi": product.get("urun_aciklamasi"),
        "afis_fiyat": product.get("afis_fiyat"),
        "ocr_text": ocr_text,
        "source": source,
        "status": status,
        "created_at": datetime.utcnow().isoformat(),
    }
    mid = save_mapping(m)
    st.success(f"Kaydedildi! (ID: {mid}, kaynak: {source})")

    # Reset for next selection
    st.session_state["last_bbox"] = None
    st.session_state["last_ocr_text"] = None
    st.session_state["manual_mode"] = False
    st.rerun()


def _render_mappings_table(page: dict):
    """Show saved mappings for current page with delete buttons."""
    mappings = list_mappings(
        st.session_state["week_id"],
        page["flyer_filename"],
        page["page_no"],
    )
    if not mappings:
        st.caption("Bu sayfa için henüz eşleştirme yok.")
        return

    st.markdown(f"### Kaydedilen Eşleştirmeler ({len(mappings)})")

    # Table
    rows = []
    for m in mappings:
        rows.append({
            "ID": m["mapping_id"],
            "Ürün Kodu": m["urun_kodu"] or "",
            "Açıklama": (m["urun_aciklamasi"] or "")[:50],
            "Fiyat": m["afis_fiyat"] or "",
            "Kaynak": m["source"],
            "Durum": m["status"],
            "BBox": f'({m["x0"]:.2f},{m["y0"]:.2f})-({m["x1"]:.2f},{m["y1"]:.2f})',
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Delete
    del_id = st.number_input("Silinecek ID:", min_value=0, step=1, key="inp_del_id")
    if st.button("Sil", key="btn_del_mapping"):
        if del_id > 0:
            delete_mapping(int(del_id))
            st.success(f"ID {del_id} silindi.")
            st.rerun()


# =========================================================================
# Main flow
# =========================================================================

tab_map, tab_view = st.tabs(["Eşleştir (Admin)", "Görüntüleyici (Viewer)"])

with tab_map:
    st.title("Flyer Mapping Tool")

    # --- Sidebar: Bulk Upload ---
    with st.sidebar:
        st.header("Yükleme")

        week_id = st.text_input(
            "Hafta ID",
            value=st.session_state["week_id"],
            key="inp_week",
        )
        st.session_state["week_id"] = week_id

        excel_file = st.file_uploader(
            "Excel Ürün Listesi",
            type=["xlsx", "xls"],
            key="up_excel",
        )
        pdf_files = st.file_uploader(
            "PDF Dosyaları",
            type=["pdf"],
            accept_multiple_files=True,
            key="up_pdfs",
        )

        zoom = st.slider("Render Zoom", 2.0, 5.0, 3.5, 0.5, key="sl_zoom")

        if st.button("Haftayı Yükle", type="primary", key="btn_load"):
            _load_week(excel_file, pdf_files, zoom)

        if st.session_state["pages"]:
            st.success(f'{len(st.session_state["pages"])} sayfa yüklendi')

        if st.session_state["excel_df"] is not None:
            st.info(f'Excel: {len(st.session_state["excel_df"])} ürün')

    # --- Page selector ---
    pages = st.session_state["pages"]
    if not pages:
        st.info("Sol panelden PDF ve Excel yükleyin, ardından 'Haftayı Yükle' basın.")
    else:
        page_labels = [f'{p["flyer_filename"]} - s{p["page_no"]}' for p in pages]
        sel_idx = st.selectbox(
            "Sayfa Seç",
            range(len(pages)),
            format_func=lambda i: page_labels[i],
            key="sel_page",
        )
        page = pages[sel_idx]

        # Layout: image left, controls right
        col_img, col_ctrl = st.columns([3, 2])

        with col_img:
            _render_canvas(page)

        with col_ctrl:
            _render_controls(page)

        # Saved mappings table
        st.markdown("---")
        _render_mappings_table(page)

with tab_view:
    st.title("Flyer Görüntüleyici")
    pages = st.session_state["pages"]
    if not pages:
        st.info("Önce 'Eşleştir' sekmesinden veri yükleyin.")
    else:
        page_labels_v = [f'{p["flyer_filename"]} - s{p["page_no"]}' for p in pages]
        sel_v = st.selectbox(
            "Sayfa",
            range(len(pages)),
            format_func=lambda i: page_labels_v[i],
            key="sel_page_viewer",
        )
        vpage = pages[sel_v]

        mappings = list_mappings(
            st.session_state["week_id"],
            vpage["flyer_filename"],
            vpage["page_no"],
        )

        if not mappings:
            st.warning("Bu sayfa için henüz eşleştirme yok.")

        clicked_id = render_viewer(
            vpage["png_bytes"], mappings, vpage["w"], vpage["h"],
            component_key="viewer_main",
        )

        if clicked_id:
            hit = next((m for m in mappings if m["mapping_id"] == clicked_id), None)
            if hit:
                st.success(f'Seçilen: {hit["urun_kodu"]} — {hit["urun_aciklamasi"]}')
                result = run_search(hit["urun_kodu"])
                if result:
                    st.json(result)
