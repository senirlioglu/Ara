"""Store-facing viewer — hotspot overlay on flyer page images."""

from __future__ import annotations

import base64
import json
import streamlit as st
import streamlit.components.v1 as components


def render_viewer(
    png_bytes: bytes,
    mappings: list[dict],
    img_w: int,
    img_h: int,
    component_key: str = "viewer",
) -> int | None:
    """Render flyer image with clickable hotspot overlays.

    Returns:
        mapping_id of clicked hotspot, or None.
    """
    b64 = base64.b64encode(png_bytes).decode()
    img_src = f"data:image/png;base64,{b64}"

    # Build hotspot divs
    hotspot_divs = ""
    for m in mappings:
        x0p = m["x0"] * 100
        y0p = m["y0"] * 100
        wp = (m["x1"] - m["x0"]) * 100
        hp = (m["y1"] - m["y0"]) * 100
        mid = m["mapping_id"]
        label = m.get("urun_kodu") or "?"
        desc = (m.get("urun_aciklamasi") or "")[:40]

        hotspot_divs += f"""
        <div class="hotspot" data-mid="{mid}"
             style="left:{x0p:.2f}%;top:{y0p:.2f}%;width:{wp:.2f}%;height:{hp:.2f}%"
             title="{label} — {desc}">
          <span class="hs-label">{label}</span>
        </div>"""

    html = f"""
    <style>
      #vwrap {{ position:relative; display:inline-block; }}
      #vwrap img {{ display:block; max-width:100%; height:auto; }}
      .hotspot {{
        position:absolute; border:2px solid rgba(30,58,95,0.8);
        background:rgba(30,58,95,0.12); cursor:pointer;
        transition: background 0.15s;
      }}
      .hotspot:hover {{ background:rgba(30,58,95,0.30); }}
      .hs-label {{
        position:absolute; bottom:0; left:0;
        background:rgba(30,58,95,0.85); color:#fff;
        font-size:11px; padding:1px 5px; white-space:nowrap;
      }}
    </style>
    <div id="vwrap">
      <img src="{img_src}" />
      {hotspot_divs}
    </div>
    <script>
    document.querySelectorAll('.hotspot').forEach(function(el) {{
      el.addEventListener('click', function() {{
        var mid = parseInt(this.getAttribute('data-mid'));
        window.parent.postMessage({{
          type: "streamlit:setComponentValue",
          value: mid
        }}, "*");
      }});
    }});
    // Set frame height
    setTimeout(function() {{
      var h = document.body.scrollHeight + 10;
      window.parent.postMessage({{
        type: "streamlit:setFrameHeight",
        height: h
      }}, "*");
    }}, 300);
    </script>
    """

    clicked = components.html(html, height=800, scrolling=True, key=component_key)
    return clicked if isinstance(clicked, int) else None


def run_search(product_code: str) -> dict | None:
    """Placeholder for product DB search. Replace with real implementation."""
    if not product_code:
        return None
    return {
        "urun_kodu": product_code,
        "message": f"Arama: {product_code} (DB baglantisi eklenecek)",
    }
