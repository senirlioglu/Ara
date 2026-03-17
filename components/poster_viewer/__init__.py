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
    report_page_changes: bool = False,
    max_display_width: int = 800,
    height: int = 1200,
    key: str = "poster_viewer",
) -> dict | None:
    """Render a poster slider with hotspots.

    Parameters
    ----------
    pages : list[dict]
        Each entry: {"label": str, "hotspots": [...]} and optionally
        ``"png_bytes"`` when the page image is already available.
    current_index : int
        Which page to show initially.
    click_mode : str
        "popup" = admin preview popup, "search" = send urun_kodu to trigger search.
    report_page_changes : bool
        When True, page navigation emits ``page_change`` events so Streamlit can
        lazily load nearby pages.
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
    cached = st.session_state.get(cache_key, {})
    comp_pages = []
    next_cache = {}

    for idx, pg in enumerate(pages):
        png_bytes = pg.get("png_bytes") or b""
        page_sig = (
            pg.get("label", ""),
            len(pg.get("hotspots", [])),
            len(png_bytes),
        )
        cached_page = cached.get(idx)

        if png_bytes and cached_page and cached_page.get("sig") == page_sig:
            image_b64 = cached_page["image_b64"]
        elif png_bytes:
            image_b64 = _encode_page(png_bytes, max_display_width)
        else:
            image_b64 = ""

        comp_pages.append({
            "image_b64": image_b64,
            "label": pg.get("label", ""),
            "hotspots": pg.get("hotspots", []),
        })
        next_cache[idx] = {
            "sig": page_sig,
            "image_b64": image_b64,
        }

    st.session_state[cache_key] = next_cache

    return _component_func(
        pages=comp_pages,
        current_index=current_index,
        click_mode=click_mode,
        report_page_changes=report_page_changes,
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
