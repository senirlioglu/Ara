"""Poster Viewer — Streamlit custom component.

Displays poster pages in a slider with interactive hotspots.
Clicking a hotspot shows product info (code, description, price).
Supports keyboard arrows and touch swipe navigation.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_component_func = components.declare_component("poster_viewer", path=str(_FRONTEND_DIR))


def poster_viewer(
    pages: list[dict],
    *,
    current_index: int = 0,
    click_mode: str = "popup",
    max_display_width: int = 800,
    height: int = 1200,
    key: str = "poster_viewer",
) -> dict | None:
    """Render a poster slider with hotspots.

    Parameters
    ----------
    pages : list[dict]
        Each entry: {"png_bytes": bytes, "label": str, "hotspots": [...]}
    current_index : int
        Which page to show initially.
    click_mode : str
        "popup" = admin preview popup, "search" = send urun_kodu to trigger search.
    max_display_width : int
        Max pixel width for the displayed image.
    height : int
        Component iframe height.
    key : str
        Stable key for the component.

    Returns
    -------
    dict | None
        ``{"type": "hotspot_click", "urun_kodu": "..."}`` in search mode,
        ``{"type": "page_change", "index": N}`` on navigation.
    """
    # Build lightweight page data (b64 images + hotspots)
    cache_key = f"_pv_cache_{key}"
    cached = st.session_state.get(cache_key)

    # Check if pages changed (compare count + first page label)
    pages_sig = (len(pages), pages[0]["label"] if pages else "")
    if cached and cached.get("sig") == pages_sig:
        comp_pages = cached["data"]
    else:
        comp_pages = []
        for pg in pages:
            b64 = _encode_page(pg["png_bytes"], max_display_width)
            comp_pages.append({
                "image_b64": b64,
                "label": pg.get("label", ""),
                "hotspots": pg.get("hotspots", []),
            })
        st.session_state[cache_key] = {"sig": pages_sig, "data": comp_pages}

    return _component_func(
        pages=comp_pages,
        current_index=current_index,
        click_mode=click_mode,
        key=key,
        default=None,
        height=height,
    )


def _encode_page(png_bytes: bytes, max_w: int) -> str:
    """Resize and encode page image to JPEG base64."""
    pil = Image.open(io.BytesIO(png_bytes))
    w, h = pil.size
    dw = min(max_w, w)
    scale = dw / w
    dh = int(h * scale)
    display = pil.resize((dw, dh), Image.BILINEAR)
    if display.mode == "RGBA":
        display = display.convert("RGB")
    buf = io.BytesIO()
    display.save(buf, format="JPEG", quality=72)
    return base64.b64encode(buf.getvalue()).decode()
