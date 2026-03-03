"""Bbox Canvas — Streamlit custom component (declare_component).

Renders a PDF page image and lets the user draw a rectangle with the mouse.
Returns normalised coordinates {x0, y0, x1, y1} (0‑1 range) to Python.

The component is declared once; Streamlit manages its iframe lifecycle.
The key must be STABLE across reruns (same page → same key) so the
iframe is reused rather than torn down and recreated.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_component_func = components.declare_component("bbox_canvas", path=str(_FRONTEND_DIR))


def bbox_canvas(
    page_png_bytes: bytes,
    *,
    saved_boxes: list[dict] | None = None,
    active_bbox: dict | None = None,
    max_display_width: int = 700,
    key: str,
) -> dict | None:
    """Interactive bbox-drawing canvas.

    Parameters
    ----------
    page_png_bytes : bytes
        Raw PNG bytes of the page (full resolution, as rendered by pdf_render).
    saved_boxes : list[dict] | None
        DB-saved boxes ``[{x0, y0, x1, y1, label}, ...]`` shown as green overlay.
    active_bbox : dict | None
        Currently active (red) selection to restore after a Streamlit rerun.
    max_display_width : int
        Maximum display width in pixels.  The image is resized for the
        component but the *original* bytes are kept for OCR.
    key : str
        **Must be deterministic and stable** across reruns for the same page,
        e.g. ``f"bbox_{filename}_{page_no}"``.  Changing this destroys the
        iframe and resets all JS state.

    Returns
    -------
    dict | None
        ``{x0, y0, x1, y1}`` (normalised 0-1) when the user clicks
        "Seçimi Kullan", else the previously sent value (Streamlit caches
        the last ``setComponentValue``).
    """
    # ── b64 cache: avoid re-encoding on every rerun ──
    cache_key = f"_bbox_b64_{key}"
    if cache_key not in st.session_state:
        pil = Image.open(io.BytesIO(page_png_bytes))
        w, h = pil.size
        dw = min(max_display_width, w)
        scale = dw / w
        dh = int(h * scale)
        display = pil.resize((dw, dh), Image.LANCZOS)
        buf = io.BytesIO()
        display.save(buf, format="PNG", optimize=True)
        st.session_state[cache_key] = base64.b64encode(buf.getvalue()).decode()

    img_b64 = st.session_state[cache_key]

    return _component_func(
        image_b64=img_b64,
        saved_boxes=saved_boxes or [],
        active_bbox=active_bbox,
        key=key,
        default=None,
    )
