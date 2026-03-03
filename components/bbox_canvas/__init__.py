"""Bbox Canvas — a minimal Streamlit custom component.

Renders an image and lets the user draw a rectangle on it with the mouse.
Returns normalised coordinates ``{x0, y0, x1, y1}`` (0-1 range) to Python.
"""

from pathlib import Path
import streamlit.components.v1 as components

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_component_func = components.declare_component("bbox_canvas", path=str(_FRONTEND_DIR))


def bbox_canvas(image_b64: str, saved_boxes: list | None = None,
                height: int = 800, key: str | None = None):
    """Show an interactive bbox-drawing canvas.

    Parameters
    ----------
    image_b64 : str
        Base-64 encoded PNG image (no ``data:`` prefix).
    saved_boxes : list[dict] | None
        Previously saved boxes ``[{x0, y0, x1, y1, label}, ...]``.
    height : int
        Iframe pixel height.
    key : str | None
        Streamlit widget key (enables multiple instances).

    Returns
    -------
    dict | None
        ``{x0, y0, x1, y1}`` when the user confirms a selection, else *None*.
    """
    return _component_func(
        image_b64=image_b64,
        saved_boxes=saved_boxes or [],
        height=height,
        key=key,
        default=None,
    )
