"""Price-anchored product region builder.

For each detected price, collect nearby OCR words inside a window
to form a product region. Merge overlapping regions by IOU.

The window is asymmetric: extends more ABOVE the price (product name/image)
and less below (delivery text).
"""

from __future__ import annotations

import re
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand whitelist
# ---------------------------------------------------------------------------

BRANDS = {
    "SAMSUNG", "LG", "SONY", "PHILIPS", "VESTEL", "TOSHIBA", "BEKO", "ARCELIK",
    "ARÇELIK", "ONVO", "NORDMENDE", "SEG", "GRUNDIG", "PIRANHA", "XIAOMI",
    "TCL", "HISENSE", "BOSCH", "SIEMENS", "REGAL", "ALTUS", "PROFILO",
    "FAKIR", "ARZUM", "SINBO", "KARACA", "KUMTEL", "LUXELL", "HOMEND",
    "KING", "FANTOM", "DYSON", "TEFAL", "BRAUN", "PANASONIC", "KENWOOD",
    "DELONGHI", "HP", "LENOVO", "APPLE", "HUAWEI", "OPPO", "MONSTER",
    "CASPER", "EXCALIBUR", "MSI", "ASUS", "ACER",
}


# ---------------------------------------------------------------------------
# Key extraction
# ---------------------------------------------------------------------------

def extract_keys(text: str) -> dict:
    """Extract matching keys from region text."""
    upper = text.upper()

    # Model codes: 6+ chars, must contain both letters and digits
    raw = set(re.findall(r"\b[A-Z0-9\-]{6,}\b", upper))
    model_codes = [m for m in raw if re.search(r"[A-Z]", m) and re.search(r"\d", m)]

    # 4-digit short codes
    code4 = list(set(re.findall(r"\b\d{4}\b", upper)))

    # Brands
    brands = [b for b in BRANDS if b in upper]

    # Size tokens
    sizes = re.findall(
        r'\b\d{2,3}\s*(?:"|"|cm|CM|inç|INÇ|inch|INCH|kg|KG|[Ll]t?|mAh|MAH)\b',
        upper, re.IGNORECASE,
    )

    # Prices (already detected, but also capture from text for keys_json)
    prices = re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", text)

    return {
        "model_codes": model_codes,
        "code4": code4,
        "brands": brands,
        "sizes": sizes,
        "prices": prices,
    }


# ---------------------------------------------------------------------------
# Region building
# ---------------------------------------------------------------------------

def _word_in_window(
    word: dict,
    win_x0: float, win_y0: float,
    win_x1: float, win_y1: float,
) -> bool:
    """Check if a word's center falls inside the window."""
    cx = (word["x0"] + word["x1"]) / 2
    cy = (word["y0"] + word["y1"]) / 2
    return win_x0 <= cx <= win_x1 and win_y0 <= cy <= win_y1


def _iou(a: dict, b: dict) -> float:
    """Intersection-over-union of two normalized bbox dicts."""
    ix0 = max(a["x0"], b["x0"])
    iy0 = max(a["y0"], b["y0"])
    ix1 = min(a["x1"], b["x1"])
    iy1 = min(a["y1"], b["y1"])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = max(0, a["x1"] - a["x0"]) * max(0, a["y1"] - a["y0"])
    area_b = max(0, b["x1"] - b["x0"]) * max(0, b["y1"] - b["y0"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def build_regions(
    words: list[dict],
    prices: list[dict],
    img_w: int,
    img_h: int,
    win_left: float = 0.25,
    win_right: float = 0.25,
    win_up: float = 0.18,
    win_down: float = 0.08,
    pad_x_frac: float = 0.015,
    pad_y_frac: float = 0.02,
    min_words: int = 3,
    min_alpha_words: int = 2,
    iou_threshold: float = 0.25,
) -> list[dict]:
    """Build price-anchored product regions.

    For each price bbox, open an asymmetric window and collect words.
    Merge overlapping regions. Filter weak regions.

    Args:
        words: OCR words [{text, x0, y0, x1, y1}, ...] (pixel).
        prices: Detected prices [{text, value, x0, y0, x1, y1}, ...] (pixel).
        img_w, img_h: Image dimensions in pixels.
        win_left/right/up/down: Window extent as fraction of img_w/img_h.
        pad_x_frac, pad_y_frac: Padding as fraction of img_w/img_h.
        min_words: Min total words to form a valid region.
        min_alpha_words: Min alphabetic words (brand/model/description).
        iou_threshold: IOU threshold for merging overlapping regions.

    Returns:
        [{price_value, price_bbox, x0, y0, x1, y1, region_text, keys_json}, ...]
        Coords are normalized (0..1).
    """
    if not words or not prices or img_w <= 0 or img_h <= 0:
        return []

    pad_x = pad_x_frac * img_w
    pad_y = pad_y_frac * img_h

    raw_regions: list[dict] = []

    for price in prices:
        # Price bbox center
        pcx = (price["x0"] + price["x1"]) / 2
        pcy = (price["y0"] + price["y1"]) / 2

        # Asymmetric window (more above, less below)
        win_x0 = pcx - win_left * img_w
        win_x1 = pcx + win_right * img_w
        win_y0 = pcy - win_up * img_h
        win_y1 = pcy + win_down * img_h

        # Clamp to image bounds
        win_x0 = max(0, win_x0)
        win_y0 = max(0, win_y0)
        win_x1 = min(img_w, win_x1)
        win_y1 = min(img_h, win_y1)

        # Collect words in window
        collected = [w for w in words if _word_in_window(w, win_x0, win_y0, win_x1, win_y1)]

        if len(collected) < min_words:
            continue

        # Count alphabetic words (at least 2 letters)
        alpha_count = sum(1 for w in collected if re.search(r"[A-Za-zÇçĞğİıÖöŞşÜü]{2,}", w["text"]))
        if alpha_count < min_alpha_words:
            continue

        # Region bbox = union of collected words + padding
        rx0 = min(w["x0"] for w in collected) - pad_x
        ry0 = min(w["y0"] for w in collected) - pad_y
        rx1 = max(w["x1"] for w in collected) + pad_x
        ry1 = max(w["y1"] for w in collected) + pad_y

        # Clamp
        rx0 = max(0, rx0)
        ry0 = max(0, ry0)
        rx1 = min(img_w, rx1)
        ry1 = min(img_h, ry1)

        # Sort words top-to-bottom, left-to-right
        collected.sort(key=lambda w: (w["y0"], w["x0"]))
        region_text = " ".join(w["text"] for w in collected)

        keys = extract_keys(region_text)

        raw_regions.append({
            "price_value": price["value"],
            "price_bbox": {
                "x0": price["x0"], "y0": price["y0"],
                "x1": price["x1"], "y1": price["y1"],
            },
            # Normalized coords
            "x0": round(rx0 / img_w, 6),
            "y0": round(ry0 / img_h, 6),
            "x1": round(rx1 / img_w, 6),
            "y1": round(ry1 / img_h, 6),
            "region_text": region_text,
            "keys_json": keys,
            "_word_count": len(collected),
        })

    # Merge overlapping regions
    merged = _merge_regions(raw_regions, iou_threshold)

    # Clean internal fields
    for r in merged:
        r.pop("_word_count", None)

    log.info(f"Region builder: {len(prices)} prices → {len(raw_regions)} raw → {len(merged)} merged")
    return merged


def _merge_regions(regions: list[dict], iou_threshold: float) -> list[dict]:
    """Merge overlapping regions by IOU."""
    if not regions:
        return []

    # Sort by area descending (larger regions absorb smaller ones)
    regions = sorted(regions, key=lambda r: (
        (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])
    ), reverse=True)

    merged: list[dict] = []

    for r in regions:
        absorbed = False
        for m in merged:
            if _iou(r, m) > iou_threshold:
                # Expand existing region to contain both
                m["x0"] = min(m["x0"], r["x0"])
                m["y0"] = min(m["y0"], r["y0"])
                m["x1"] = max(m["x1"], r["x1"])
                m["y1"] = max(m["y1"], r["y1"])
                # Combine text (deduplicate)
                if r["region_text"] not in m["region_text"]:
                    m["region_text"] += " " + r["region_text"]
                # Merge keys
                _merge_keys(m["keys_json"], r["keys_json"])
                # Keep higher price if different
                absorbed = True
                break

        if not absorbed:
            merged.append(r)

    return merged


def _merge_keys(target: dict, source: dict):
    """Merge source keys into target (deduplicate lists)."""
    for key in ("model_codes", "code4", "brands", "sizes", "prices"):
        existing = set(target.get(key, []))
        for val in source.get(key, []):
            existing.add(val)
        target[key] = list(existing)
