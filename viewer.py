import base64
import json

import streamlit.components.v1 as components


def render_viewer(png_bytes: bytes, mappings: list[dict], img_w: int, img_h: int, height: int = 700):
    img_b64 = base64.b64encode(png_bytes).decode("utf-8")
    mappings_json = json.dumps(mappings)

    html = f"""
    <div id='viewer-wrap' style='position:relative; display:inline-block;'>
      <img id='base-image' src='data:image/png;base64,{img_b64}' style='max-width:100%; height:auto; display:block;' />
      <div id='overlay' style='position:absolute; left:0; top:0; right:0; bottom:0;'></div>
    </div>
    <script src="https://unpkg.com/streamlit-component-lib/dist/streamlit-component-lib.js"></script>
    <script>
      const mappings = {mappings_json};
      const overlay = document.getElementById('overlay');
      mappings.forEach((m) => {{
        const x0 = Math.min(m.x0, m.x1) * 100;
        const y0 = Math.min(m.y0, m.y1) * 100;
        const x1 = Math.max(m.x0, m.x1) * 100;
        const y1 = Math.max(m.y0, m.y1) * 100;
        const box = document.createElement('div');
        box.style.position = 'absolute';
        box.style.left = x0 + '%';
        box.style.top = y0 + '%';
        box.style.width = (x1-x0) + '%';
        box.style.height = (y1-y0) + '%';
        box.style.border = '2px solid rgba(255,0,0,0.7)';
        box.style.background = 'rgba(255,0,0,0.15)';
        box.style.cursor = 'pointer';
        box.title = m.urun_kodu + ' - ' + m.urun_aciklamasi;
        box.onclick = () => Streamlit.setComponentValue(m.id);
        overlay.appendChild(box);
      }});
    </script>
    """
    return components.html(html, height=height, scrolling=True)
