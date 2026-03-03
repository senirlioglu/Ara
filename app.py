import base64
import hashlib
import json
from datetime import datetime
from uuid import uuid4

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pdf_render import render_pdf_bytes_to_pages
from storage import delete_mapping, init_db, list_mappings, save_mapping
from suggest_match import top_k_candidates
from viewer import render_viewer
from vision_ocr import init_gcp_credentials, ocr_crop


st.set_page_config(page_title="Flyer Mapping Tool", layout="wide")


@st.cache_data
def _load_canvas_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def run_search(product_code: str):
    if product_code and product_code.strip().isdigit() and len(product_code.strip()) >= 4:
        return {
            "found": True,
            "urun_kodu": product_code.strip(),
            "urun_aciklamasi": f"DB Canonical Product {product_code.strip()}",
        }
    return {"found": False, "urun_kodu": product_code, "urun_aciklamasi": None}


def make_ocr_cache_key(png_bytes: bytes, bbox: dict):
    rounded = {k: round(float(v), 4) for k, v in bbox.items()}
    payload = png_bytes + json.dumps(rounded, sort_keys=True).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def ensure_session_defaults():
    defaults = {
        "excel_df": None,
        "pages": [],
        "last_bbox": None,
        "last_ocr_text": "",
        "ocr_cache": {},
        "manual_mode": False,
        "selected_page_idx": 0,
        "selected_suggestion_idx": 0,
        "db_check_result": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def save_mapping_from_choice(page, week_id, bbox, source, status, urun_kodu, urun_aciklamasi, afis_fiyat=None, ocr_text=None):
    mapping = {
        "week_id": week_id,
        "flyer_filename": page["flyer_filename"],
        "page_no": int(page["page_no"]),
        "bbox_norm": bbox,
        "urun_kodu": str(urun_kodu),
        "urun_aciklamasi": str(urun_aciklamasi),
        "afis_fiyat": afis_fiyat,
        "ocr_text": ocr_text,
        "source": source,
        "status": status,
        "created_at": datetime.utcnow().isoformat(),
    }
    save_mapping(mapping)


def render_canvas_component(png_bytes: bytes):
    img_b64 = base64.b64encode(png_bytes).decode("utf-8")
    html_template = _load_canvas_template("components/canvas.html")
    html = html_template.replace("__IMAGE_SRC__", f"data:image/png;base64,{img_b64}")
    return components.html(html, height=760, scrolling=True)


def main():
    ensure_session_defaults()
    init_db()
    try:
        init_gcp_credentials()
    except Exception as e:
        st.warning(f"GCP init warning: {e}")

    st.title("Flyer Mapping Tool")

    with st.sidebar:
        st.header("Bulk Upload")
        pdf_files = st.file_uploader("PDF Dosyaları", type=["pdf"], accept_multiple_files=True)
        excel_file = st.file_uploader("Excel", type=["xlsx", "xls"])

        if st.button("Load Week"):
            if excel_file is None:
                st.error("Excel file is required.")
            else:
                df = pd.read_excel(excel_file)
                required_cols = ["ÜRÜN KODU", "ÜRÜN AÇIKLAMASI"]
                missing = [c for c in required_cols if c not in df.columns]
                if missing:
                    st.error(f"Missing required Excel columns: {missing}")
                else:
                    st.session_state["excel_df"] = df
                    pages = []
                    for pdf in pdf_files or []:
                        flyer_id = str(uuid4())
                        for page in render_pdf_bytes_to_pages(pdf.read()):
                            pages.append(
                                {
                                    "flyer_id": flyer_id,
                                    "flyer_filename": pdf.name,
                                    "page_no": page["page_no"],
                                    "png_bytes": page["png_bytes"],
                                    "w": page["w"],
                                    "h": page["h"],
                                }
                            )
                    st.session_state["pages"] = pages
                    st.success(f"Loaded {len(pages)} pages.")

    week_id = st.text_input("week_id", value="2026-03-01")

    tab_map, tab_viewer = st.tabs(["Mapping", "Viewer"])

    with tab_map:
        pages = st.session_state["pages"]
        if not pages:
            st.info("PDF ve Excel yükleyip 'Load Week' tıklayın.")
        else:
            labels = [f"{p['flyer_filename']} - p{p['page_no'] + 1}" for p in pages]
            selected_idx = st.selectbox("Sayfa Seç", range(len(labels)), format_func=lambda i: labels[i])
            st.session_state["selected_page_idx"] = selected_idx
            page = pages[selected_idx]

            col1, col2 = st.columns([3, 2])
            with col1:
                bbox = render_canvas_component(page["png_bytes"])
                if bbox is not None:
                    st.session_state["last_bbox"] = bbox

                if st.session_state["last_bbox"]:
                    st.write("Seçim:", st.session_state["last_bbox"])
                    if st.button("Clear Selection"):
                        st.session_state["last_bbox"] = None
                        st.session_state["last_ocr_text"] = ""
                        st.session_state["manual_mode"] = False
                        st.rerun()

            with col2:
                if st.session_state["last_bbox"]:
                    if st.button("Run OCR"):
                        key = make_ocr_cache_key(page["png_bytes"], st.session_state["last_bbox"])
                        if key in st.session_state["ocr_cache"]:
                            ocr_text = st.session_state["ocr_cache"][key]
                        else:
                            ocr_text = ocr_crop(
                                page["png_bytes"],
                                st.session_state["last_bbox"],
                                page["w"],
                                page["h"],
                            )
                            st.session_state["ocr_cache"][key] = ocr_text
                        st.session_state["last_ocr_text"] = ocr_text
                    st.text_area("OCR Text", value=st.session_state.get("last_ocr_text", ""), height=180)

                excel_df = st.session_state.get("excel_df")
                if excel_df is not None and st.session_state.get("last_ocr_text", ""):
                    st.subheader("Suggestions")
                    suggestions = top_k_candidates(st.session_state["last_ocr_text"], excel_df, k=5)
                    if suggestions:
                        option_labels = [
                            f"{idx+1}) {s['urun_kodu']} — {s['urun_aciklamasi']} (score={s['score']})"
                            for idx, s in enumerate(suggestions)
                        ]
                        selected_suggestion = st.radio("Top 5", range(len(option_labels)), format_func=lambda i: option_labels[i])
                        chosen = suggestions[selected_suggestion]

                        if st.button("Eşleştir (Öneri ile)"):
                            save_mapping_from_choice(
                                page,
                                week_id,
                                st.session_state["last_bbox"],
                                source="suggested",
                                status="matched",
                                urun_kodu=chosen["urun_kodu"],
                                urun_aciklamasi=chosen["urun_aciklamasi"],
                                afis_fiyat=chosen.get("afis_fiyat"),
                                ocr_text=st.session_state.get("last_ocr_text", ""),
                            )
                            st.success("Saved from suggestion.")

                        if st.button("Yok / Bulamadım"):
                            st.session_state["manual_mode"] = True

                if st.session_state.get("manual_mode"):
                    if st.button("Geri Dön (Öneriler)"):
                        st.session_state["manual_mode"] = False

                    if excel_df is not None:
                        st.markdown("### MODE B: Excel Manual Selection")
                        query = st.text_input("Excel Ara", value="", key="excel_query")
                        filtered = excel_df.copy()
                        if query.strip():
                            q = query.strip().lower()
                            filtered = filtered[
                                filtered["ÜRÜN KODU"].astype(str).str.lower().str.contains(q)
                                | filtered["ÜRÜN AÇIKLAMASI"].astype(str).str.lower().str.contains(q)
                            ]
                        records = filtered.head(200).to_dict("records")
                        if records:
                            idx = st.selectbox(
                                "Excel Ürün Seç",
                                range(len(records)),
                                format_func=lambda i: f"{records[i].get('ÜRÜN KODU', '')} — {records[i].get('ÜRÜN AÇIKLAMASI', '')}",
                                key="excel_manual_select",
                            )
                            picked = records[idx]
                            if st.button("Kaydet (Excel’den)") and st.session_state.get("last_bbox"):
                                save_mapping_from_choice(
                                    page,
                                    week_id,
                                    st.session_state["last_bbox"],
                                    source="excel_manual",
                                    status="matched",
                                    urun_kodu=picked.get("ÜRÜN KODU", ""),
                                    urun_aciklamasi=picked.get("ÜRÜN AÇIKLAMASI", ""),
                                    afis_fiyat=picked.get("AFIS_FIYAT", None),
                                    ocr_text=st.session_state.get("last_ocr_text", ""),
                                )
                                st.success("Saved from Excel manual selection.")

                    st.markdown("### MODE C: Product Code Entry")
                    code_input = st.text_input("Ürün Kodu", key="manual_code")
                    if st.button("Doğrula (DB)"):
                        st.session_state["db_check_result"] = run_search(code_input)

                    db_result = st.session_state.get("db_check_result")
                    manual_status = "unverified"
                    manual_desc = ""
                    if db_result:
                        if db_result.get("found"):
                            manual_status = "matched"
                            manual_desc = db_result.get("urun_aciklamasi", "")
                            st.success(f"Bulundu: {manual_desc}")
                        else:
                            st.warning("Kod doğrulanamadı. Unverified olarak kaydedebilirsiniz.")

                    manual_desc_input = st.text_input("Açıklama", value=manual_desc, key="manual_desc")
                    if st.button("Kaydet (Kod ile)") and st.session_state.get("last_bbox"):
                        save_mapping_from_choice(
                            page,
                            week_id,
                            st.session_state["last_bbox"],
                            source="code_manual",
                            status=manual_status,
                            urun_kodu=code_input,
                            urun_aciklamasi=manual_desc_input or "",
                            afis_fiyat=None,
                            ocr_text=st.session_state.get("last_ocr_text", ""),
                        )
                        st.success(f"Saved with status={manual_status}")

            st.markdown("---")
            st.subheader("Saved Mappings (Current Page)")
            mappings = list_mappings(week_id, page["flyer_filename"], page["page_no"])
            if mappings:
                for m in mappings:
                    row = st.columns([7, 1])
                    row[0].write(
                        f"#{m['id']} | {m['urun_kodu']} — {m['urun_aciklamasi']} | {m['source']} | {m['status']} | bbox=({m['x0']:.3f},{m['y0']:.3f},{m['x1']:.3f},{m['y1']:.3f})"
                    )
                    if row[1].button("Delete", key=f"del_{m['id']}"):
                        delete_mapping(m["id"])
                        st.rerun()
            else:
                st.caption("Bu sayfada kayıt yok.")

    with tab_viewer:
        pages = st.session_state["pages"]
        if not pages:
            st.info("Viewer için önce veri yükleyin.")
        else:
            labels = [f"{p['flyer_filename']} - p{p['page_no'] + 1}" for p in pages]
            selected_idx = st.selectbox("Viewer Page", range(len(labels)), format_func=lambda i: labels[i], key="viewer_page")
            page = pages[selected_idx]
            mappings = list_mappings(week_id, page["flyer_filename"], page["page_no"])
            st.caption(f"Hotspots: {len(mappings)}")
            selected_mapping_id = render_viewer(page["png_bytes"], mappings, page["w"], page["h"])
            if selected_mapping_id:
                picked = next((m for m in mappings if int(m["id"]) == int(selected_mapping_id)), None)
                if picked:
                    st.write(f"Seçilen: {picked['urun_kodu']} — {picked['urun_aciklamasi']}")
                    st.json(run_search(picked["urun_kodu"]))


if __name__ == "__main__":
    main()
