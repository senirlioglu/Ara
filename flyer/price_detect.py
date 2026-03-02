"""Price detection from OCR words.

Two price patterns:
  1. Large prices: 42.999, 1.299, 12.999  (dot-separated thousands)
  2. Small prices: 799, 119, 299, 459      (2-4 digit, contextually validated)

Small prices require contextual validation:
  - Range 99..9999
  - Reject if near inch (") or units (cm/ml/kg/l)
  - Reject if part of phone pattern (444 xx xx)
  - Prefer proximity to TL/₺ indicator or another large price
"""

from __future__ import annotations

import re
from typing import Optional

# Pattern 1: Turkish thousand-separated prices (42.999, 1.299,00)
RE_LARGE_PRICE = re.compile(r"\b(\d{1,3}(?:\.\d{3})+)(?:,\d{2})?\b")

# Pattern 2: Small integer prices (799, 119, 49)
RE_SMALL_PRICE = re.compile(r"^\d{2,4}$")

# Phone patterns to reject
RE_PHONE_444 = re.compile(r"\b444\s?\d{2}\s?\d{2}\b")
RE_PHONE_0850 = re.compile(r"\b0850\b")

# TL/₺ indicator words (for contextual validation of small prices)
TL_INDICATORS = {"TL", "₺", "LIRA"}

# Unit words near which a number is NOT a price
UNIT_INDICATORS = {'"', "CM", "ML", "KG", "LT", "L", "MM", "GR", "İNÇ", "INÇ", "INCH"}

# Min/max price threshold for small prices
MIN_SMALL_PRICE = 99
MAX_SMALL_PRICE = 9999


def _word_center(w: dict) -> tuple[float, float]:
    return (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2


def find_prices(
    words: list[dict],
    img_w: int,
    img_h: int,
) -> list[dict]:
    """Detect price words from OCR output.

    Args:
        words: [{text, x0, y0, x1, y1}, ...] in pixel coords.
        img_w, img_h: Image dimensions in pixels.

    Returns:
        [{text, value, x0, y0, x1, y1}, ...]
        value is the raw price string (e.g. "42.999" or "799").
    """

    # Pre-locate TL indicator words
    tl_words = [w for w in words if w["text"].upper().strip(".,") in TL_INDICATORS]

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

    # Pass 2: Small prices (contextually validated)
    for w in words:
        text = w["text"].strip().rstrip(".,")
        if not RE_SMALL_PRICE.match(text):
            continue

        try:
            val = int(text)
        except ValueError:
            continue

        if val < MIN_SMALL_PRICE or val > MAX_SMALL_PRICE:
            continue

        # Skip if already captured as part of a large price
        already = any(
            p["x0"] == w["x0"] and p["y0"] == w["y0"]
            for p in prices
        )
        if already:
            continue

        # Gather nearby words (within 160px x, 80px y) for contextual validation
        cx, cy = _word_center(w)
        near_texts = []
        for u in words:
            ucx, ucy = _word_center(u)
            if abs(ucx - cx) < 160 and abs(ucy - cy) < 80:
                near_texts.append(u["text"].upper().strip(".,"))

        near_str = " ".join(near_texts)

        # Reject: near inch mark (")
        if any('"' in nt or '"' in nt or '"' in nt for nt in near_texts):
            continue

        # Reject: near unit indicators (cm, ml, kg, l, mm, gr)
        if any(nt in UNIT_INDICATORS for nt in near_texts):
            continue

        # Reject: part of phone pattern (444 xx xx, 0850)
        if RE_PHONE_444.search(near_str) or RE_PHONE_0850.search(near_str):
            continue

        # Validate: near a TL indicator or near another large price
        near_tl = any(nt in TL_INDICATORS for nt in near_texts)
        near_large = any(
            abs(_word_center(p)[0] - cx) < 160 and abs(_word_center(p)[1] - cy) < 80
            for p in prices
        )

        if near_tl or near_large:
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
