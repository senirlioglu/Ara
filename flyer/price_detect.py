"""Price detection from OCR words.

Two price patterns:
  1. Large prices: 42.999, 1.299, 12.999  (dot-separated thousands)
  2. Small prices: 799, 119, 299, 459      (2-4 digit, contextually validated)

Small prices require contextual validation:
  - Must be near ₺/TL text, or within a price-like neighborhood
  - Must be >= 49
"""

from __future__ import annotations

import re
from typing import Optional

# Pattern 1: Turkish thousand-separated prices (42.999, 1.299,00)
RE_LARGE_PRICE = re.compile(r"\b(\d{1,3}(?:\.\d{3})+)(?:,\d{2})?\b")

# Pattern 2: Small integer prices (799, 119, 49)
RE_SMALL_PRICE = re.compile(r"^\d{2,4}$")

# TL/₺ indicator words (for contextual validation of small prices)
TL_INDICATORS = {"TL", "₺", "LIRA"}

# Min price threshold
MIN_SMALL_PRICE = 49


def _word_center(w: dict) -> tuple[float, float]:
    return (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2


def _distance(a: dict, b: dict) -> float:
    ax, ay = _word_center(a)
    bx, by = _word_center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def find_prices(
    words: list[dict],
    img_w: int,
    img_h: int,
    tl_proximity: float = 0.08,
) -> list[dict]:
    """Detect price words from OCR output.

    Args:
        words: [{text, x0, y0, x1, y1}, ...] in pixel coords.
        img_w, img_h: Image dimensions in pixels.
        tl_proximity: Max distance (fraction of image diagonal) to TL indicator
                      for small-price contextual validation.

    Returns:
        [{text, value, x0, y0, x1, y1}, ...]
        value is the raw price string (e.g. "42.999" or "799").
    """
    diag = (img_w ** 2 + img_h ** 2) ** 0.5
    tl_radius = tl_proximity * diag

    # Pre-locate TL indicator words
    tl_words = [w for w in words if w["text"].upper().strip(".,") in TL_INDICATORS]

    # Also locate large-price words (they form a "price neighborhood")
    large_price_words: list[dict] = []
    prices: list[dict] = []

    # Pass 1: Large prices (always valid)
    for w in words:
        text = w["text"].strip()
        m = RE_LARGE_PRICE.search(text)
        if m:
            prices.append({
                "text": text,
                "value": m.group(0),
                "x0": w["x0"],
                "y0": w["y0"],
                "x1": w["x1"],
                "y1": w["y1"],
            })
            large_price_words.append(w)

    # Pass 2: Small prices (contextually validated)
    for w in words:
        text = w["text"].strip().rstrip(".,")
        if not RE_SMALL_PRICE.match(text):
            continue

        try:
            val = int(text)
        except ValueError:
            continue

        if val < MIN_SMALL_PRICE:
            continue

        # Skip if already captured as part of a large price
        already = any(
            p["x0"] == w["x0"] and p["y0"] == w["y0"]
            for p in prices
        )
        if already:
            continue

        # Contextual validation: near a TL indicator or near another large price
        near_tl = any(_distance(w, tw) < tl_radius for tw in tl_words)
        near_price = any(_distance(w, pw) < tl_radius for pw in large_price_words)

        if near_tl or near_price:
            prices.append({
                "text": text,
                "value": text,
                "x0": w["x0"],
                "y0": w["y0"],
                "x1": w["x1"],
                "y1": w["y1"],
            })

    return prices


def parse_price_value(price_str: str) -> Optional[float]:
    """Parse Turkish price string to numeric value.

    '42.999' → 42999.0, '1.299,00' → 1299.0, '799' → 799.0
    """
    if not price_str:
        return None
    s = re.sub(r"[TL₺\s]", "", price_str.strip())
    s = re.sub(r",\d{2}$", "", s)
    s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None
