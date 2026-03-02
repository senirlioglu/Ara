"""Price-anchored product region builder.

For each detected price, collect nearby OCR words inside an asymmetric window
to form a product region. Apply token-anchor filtering and stopword removal.
Merge overlapping regions by IOU only when price centers are close.

Window geometry (relative to price center):
  x: price_center ± 0.22*W
  y: [price_y0 - 0.22*H, price_y1 + 0.04*H]
"""

from __future__ import annotations

import re
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopwords — noise text that should never be part of a product region
# ---------------------------------------------------------------------------

STOPWORDS = {
    "ÜCRETSİZ", "KURULUM", "MÜŞTERİ", "HİZMETLERİ", "NUMARASI",
    "ÇAĞRI", "MERKEZİ", "TAKSİT", "PEŞİN", "FİYATINA", "KAMPANYA",
    "ALDIN", "PERŞEMBE", "HİZMET", "TL", "₺", "SEPETTE", "FİYATI",
    "KASADA", "HAVALE", "EFT", "KDV", "DAHİL", "SINIRLI", "STOK",
    "ADET", "İNDİRİM", "FIRSAT", "KAMPANYALI", "NET", "GÜNCEL",
    "0850", "DETAY", "DETAYLI", "BİLGİ", "İÇİN",
}

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

# Regex patterns for key extraction
RE_MODEL = re.compile(r"\b[A-Z0-9\-]{6,}\b")
RE_CODE4 = re.compile(r"\b\d{4}\b")


# ---------------------------------------------------------------------------
# Key extraction
# ---------------------------------------------------------------------------

def extract_keys(text: str) -> dict:
    """Extract matching keys from region text."""
    upper = text.upper()

    # Model codes: 6+ chars, must contain both letters and digits
    raw = set(RE_MODEL.findall(upper))
    model_codes = [m for m in raw if re.search(r"[A-Z]", m) and re.search(r"\d", m)]

    # 4-digit short codes
    code4 = list(set(RE_CODE4.findall(upper)))

    # Brands
    brands = [b for b in BRANDS if b in upper]

    # Size tokens
    sizes = re.findall(
        r'\b\d{2,3}\s*(?:"|"|cm|CM|inç|INÇ|inch|INCH|kg|KG|[Ll]t?|mAh|MAH)\b',
        upper, re.IGNORECASE,
    )

    # Prices (also capture from text for keys_json)
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

def _word_center(w: dict) -> tuple[float, float]:
    return (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2


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
    """Intersection-over-union of two bbox dicts (normalized coords)."""
    ix0 = max(a["x0"], b["x0"])
    iy0 = max(a["y0"], b["y0"])
    ix1 = min(a["x1"], b["x1"])
    iy1 = min(a["y1"], b["y1"])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = max(0, a["x1"] - a["x0"]) * max(0, a["y1"] - a["y0"])
    area_b = max(0, b["x1"] - b["x0"]) * max(0, b["y1"] - b["y0"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def _price_center_px(region: dict, img_w: int, img_h: int) -> tuple[float, float]:
    """Get price center in pixel coords from the stored price_bbox."""
    pb = region.get("_price_bbox_px")
    if pb:
        return (pb["x0"] + pb["x1"]) / 2, (pb["y0"] + pb["y1"]) / 2
    return 0, 0


def build_regions(
    words: list[dict],
    prices: list[dict],
    img_w: int,
    img_h: int,
    win_extent: float = 0.22,
    win_up: float = 0.22,
    win_down: float = 0.04,
    pad_x_frac: float = 0.015,
    pad_y_frac: float = 0.02,
    min_words: int = 3,
    min_alpha_words: int = 1,
    iou_threshold: float = 0.25,
    anchor_radius: int = 180,
) -> list[dict]:
    """Build price-anchored product regions.

    For each price bbox, open an asymmetric window, collect words,
    filter stopwords, apply token-anchor filtering, then merge.

    Args:
        words: OCR words [{text, x0, y0, x1, y1}, ...] (pixel).
        prices: Detected prices [{text, value, x0, y0, x1, y1}, ...] (pixel).
        img_w, img_h: Image dimensions in pixels.
        win_extent: Window ±X extent as fraction of img_w (0.22).
        win_up: Window upward extent as fraction of img_h (0.22).
        win_down: Window downward extent as fraction of img_h (0.04).
        pad_x_frac, pad_y_frac: Padding as fraction of img_w/img_h.
        min_words: Min total words to form a valid region.
        min_alpha_words: Min alphabetic words (brand/model/description).
        iou_threshold: IOU threshold for merging overlapping regions.
        anchor_radius: Pixel radius for token-anchor filtering.

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

        # Asymmetric window:
        # x: price_center ± 0.22*W
        # y: [price_y0 - 0.22*H, price_y1 + 0.04*H]
        win_x0 = max(0, pcx - win_extent * img_w)
        win_x1 = min(img_w, pcx + win_extent * img_w)
        win_y0 = max(0, price["y0"] - win_up * img_h)
        win_y1 = min(img_h, price["y1"] + win_down * img_h)

        # Collect words in window (excluding stopwords)
        collected = []
        for w in words:
            if not _word_in_window(w, win_x0, win_y0, win_x1, win_y1):
                continue
            if w["text"].upper().strip(".,;:!?") in STOPWORDS:
                continue
            collected.append(w)

        # ----- Token anchor filtering -----
        # If a model token ([A-Z0-9]{6,} with both letters and digits)
        # or a code4 (\d{4}) is found among collected words,
        # keep only words within anchor_radius of that anchor token.
        all_txt = " ".join(c["text"] for c in collected).upper()

        anchors = []
        for m in RE_MODEL.findall(all_txt):
            if re.search(r"[A-Z]", m) and re.search(r"\d", m):
                anchors.append(m)
        for c in RE_CODE4.findall(all_txt):
            anchors.append(c)

        if anchors:
            # Find the first anchor's bbox
            anchor_tok = anchors[0]
            anchor_word = next(
                (w for w in collected if w["text"].upper() == anchor_tok),
                None,
            )
            if anchor_word:
                acx, acy = _word_center(anchor_word)
                collected = [
                    w for w in collected
                    if abs(_word_center(w)[0] - acx) < anchor_radius
                    and abs(_word_center(w)[1] - acy) < (anchor_radius * 0.78)
                ]

        # Minimum content check
        if len(collected) < min_words:
            continue

        alpha_count = sum(
            1 for w in collected
            if re.search(r"[A-Za-zÇçĞğİıÖöŞşÜü]{2,}", w["text"])
        )
        if alpha_count < min_alpha_words:
            continue

        # Region bbox = union of collected words + padding
        rx0 = max(0, min(w["x0"] for w in collected) - pad_x)
        ry0 = max(0, min(w["y0"] for w in collected) - pad_y)
        rx1 = min(img_w, max(w["x1"] for w in collected) + pad_x)
        ry1 = min(img_h, max(w["y1"] for w in collected) + pad_y)

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
            # Internal: for merge price-center distance check
            "_price_center_px": (pcx, (price["y0"] + price["y1"]) / 2),
        })

    # Merge overlapping regions (only if price centers are close)
    merged = _merge_regions(raw_regions, iou_threshold, img_w, img_h)

    # Clean internal fields
    for r in merged:
        r.pop("_price_center_px", None)

    log.info(
        f"Region builder: {len(prices)} prices → {len(raw_regions)} raw → {len(merged)} merged"
    )
    return merged


def _merge_regions(
    regions: list[dict],
    iou_threshold: float,
    img_w: int,
    img_h: int,
) -> list[dict]:
    """Merge overlapping regions by IOU, but only if price centers are close."""
    if not regions:
        return []

    # Max distance between price centers for merge (fraction of image)
    max_price_dist = 0.15 * ((img_w ** 2 + img_h ** 2) ** 0.5)

    # Sort by area descending (larger regions absorb smaller ones)
    regions = sorted(regions, key=lambda r: (
        (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])
    ), reverse=True)

    merged: list[dict] = []

    for r in regions:
        absorbed = False
        r_pc = r.get("_price_center_px", (0, 0))

        for m in merged:
            if _iou(r, m) > iou_threshold:
                # Check price center distance — don't merge distant prices
                m_pc = m.get("_price_center_px", (0, 0))
                dist = ((r_pc[0] - m_pc[0]) ** 2 + (r_pc[1] - m_pc[1]) ** 2) ** 0.5
                if dist > max_price_dist:
                    continue  # Different product — keep separate

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
