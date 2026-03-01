"""Product-region detection from OCR blocks.

Pipeline:
  1. filter_noise_candidates()  — drop junk before any clustering
  2. build_product_clusters_price_anchor() — price-anchored regions + DBSCAN fallback
  3. _extract_keys()  — extract model codes, brands, sizes, prices from cluster text

Input: list of {text, x0, y0, x1, y1, level} in pixel coords + image dimensions.
Output: list of cluster dicts with normalized bboxes (0..1) and combined text.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
from sklearn.cluster import DBSCAN


# ---------------------------------------------------------------------------
# Constants
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

# Promo / boilerplate keywords to drop (Turkish flyer noise)
NOISE_KEYWORDS = {
    "ÜCRETSİZ", "UCRETSIZ", "TESLİMAT", "TESLIMAT", "GÜNÜNDE", "GUNUNDE",
    "KAMPANYA", "KAMPANYALI", "FIRSATI", "FIRSAT", "İNDİRİM", "INDIRIM",
    "SEPETTE", "TAKSIT", "AYLIK", "SÜPER", "SUPER", "HEMEN", "ANINDA",
    "KDV DAHİL", "KDV DAHIL", "KARGO", "ÜCRETSIZ KARGO",
    "STOKLARLA SINIRLI", "STOKLA SINIRLI", "SINIRLI", "STOKLARLA",
    "WWW", "HTTP", "COM", "ONLINE", "MAGAZA", "MAĞAZA",
    "HOŞGELDİNİZ", "HOSGELDINIZ",
    "DETAYLI", "BİLGİ", "BILGI",
    "KAÇIRMA", "KACIRMA", "KAÇIRMAYIN", "KACIRMAYIN",
    "GEÇERLİ", "GECERLI",
}

# Regex: text that is only numbers/units/punctuation — not product info
RE_ONLY_UNITS = re.compile(
    r"^[\d\s\*\-.,/x×:]+\s*"
    r"(ML|G|GR|KG|CM|MM|LT|L|W|WATT|V|VOLT|HZ|DB|İNÇ|INÇ|INCH|DPI|RPM|MAH|AH)?"
    r"[\s\*\-.,/]*$",
    re.IGNORECASE,
)

# Price patterns (Turkish format: 12.999 or 1.299,00 or 42.999 TL)
RE_PRICE = re.compile(
    r"\b(\d{1,3}(?:\.\d{3})+(?:,\d{2})?)\b"
)


# ---------------------------------------------------------------------------
# 1) Noise filtering
# ---------------------------------------------------------------------------

def filter_noise_candidates(
    blocks: list[dict],
    img_w: int,
    img_h: int,
    min_chars: int = 8,
    min_words: int = 2,
    min_area_norm: float = 0.0005,
) -> list[dict]:
    """Drop noise blocks BEFORE clustering.

    Filters:
      - Text too short (< min_chars) or fewer than min_words
      - Text matches only units/numbers pattern
      - Text matches known promo/boilerplate keywords
      - Bbox area too small (area_norm < min_area_norm)

    Exception: blocks containing a PRICE pattern pass even if short,
    because price labels are critical for anchoring.

    Returns filtered list (same dict structure, no mutation).
    """
    if img_w <= 0 or img_h <= 0:
        return blocks

    img_area = img_w * img_h
    kept: list[dict] = []

    for b in blocks:
        text = b.get("text", "").strip()
        upper = text.upper()

        # Compute bbox area (normalized)
        bw = max(0, b.get("x1", 0) - b.get("x0", 0))
        bh = max(0, b.get("y1", 0) - b.get("y0", 0))
        area_norm = (bw * bh) / img_area if img_area > 0 else 0

        has_price = bool(RE_PRICE.search(text))

        # --- Filter: tiny bbox ---
        if area_norm < min_area_norm and not has_price:
            continue

        # --- Filter: too short ---
        word_count = len(text.split())
        if len(text) < min_chars and word_count < min_words and not has_price:
            continue

        # --- Filter: only units/numbers ---
        if RE_ONLY_UNITS.match(upper) and not has_price:
            continue

        # --- Filter: pure promo/boilerplate ---
        # If ALL significant words are noise keywords, drop it
        words_upper = [w for w in upper.split() if len(w) >= 3]
        if words_upper:
            noise_count = sum(1 for w in words_upper if w in NOISE_KEYWORDS)
            if noise_count == len(words_upper) and not has_price:
                continue

        kept.append(b)

    return kept


# ---------------------------------------------------------------------------
# 2) Key extraction from cluster text
# ---------------------------------------------------------------------------

def _extract_keys(text: str) -> dict:
    """Extract matching keys from cluster OCR text."""
    upper = text.upper()

    # Model codes: 6+ chars, must mix letters + digits
    raw = set(re.findall(r"\b[A-Z0-9\-]{6,}\b", upper))
    model_codes = [m for m in raw if re.search(r"[A-Z]", m) and re.search(r"\d", m)]

    # 4-digit codes (accessory codes like 9035)
    code4 = list(set(re.findall(r"\b\d{4}\b", upper)))

    # Brands
    brands = [b for b in BRANDS if b in upper]

    # Size tokens (e.g., 70", 55", 43 cm)
    sizes = re.findall(r'\b\d{2,3}\s*(?:"|"|cm|CM|inç|inch|İNÇ)\b', upper, re.IGNORECASE)

    # Price tokens (e.g., 42.999, 1.299,00)
    prices = RE_PRICE.findall(text)

    return {
        "model_codes": model_codes,
        "code4": code4,
        "brands": brands,
        "sizes": sizes,
        "prices": prices,
    }


def _has_product_signal(keys: dict) -> bool:
    """Check if extracted keys carry enough signal for a real product."""
    return bool(
        keys.get("model_codes")
        or keys.get("prices")
        or keys.get("brands")
        or keys.get("code4")
    )


# ---------------------------------------------------------------------------
# 3) Price-anchored product region builder
# ---------------------------------------------------------------------------

def _find_price_blocks(blocks: list[dict]) -> list[dict]:
    """Return blocks that contain a price pattern."""
    return [b for b in blocks if RE_PRICE.search(b.get("text", ""))]


def _block_center(b: dict) -> tuple[float, float]:
    """Return (cx, cy) pixel center of a block."""
    cx = (b.get("x0", 0) + b.get("x1", 0)) / 2
    cy = (b.get("y0", 0) + b.get("y1", 0)) / 2
    return cx, cy


def _distance(a: dict, b: dict) -> float:
    """Euclidean distance between block centers."""
    ax, ay = _block_center(a)
    bx, by = _block_center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def build_product_clusters_price_anchor(
    blocks: list[dict],
    img_w: int,
    img_h: int,
    radius_factor: float = 0.15,
    pad_x: float = 20.0,
    pad_y: float = 20.0,
    eps_factor: float = 0.06,
    min_samples: int = 3,
    max_clusters: int = 30,
    max_retries: int = 3,
) -> list[dict]:
    """Build product clusters using price-anchored regions + DBSCAN fallback.

    Strategy:
      1. Find all blocks containing price patterns.
      2. For each price block, collect nearby blocks within a radius
         (radius = radius_factor * max(img_w, img_h)) to form a product region.
      3. Blocks not assigned to any price region go to DBSCAN fallback.
      4. DBSCAN uses adaptive eps (eps_factor * img_w). If too many clusters,
         auto-increases eps and retries.
      5. Merge overlapping regions.

    Returns:
        list of {x0, y0, x1, y1, ocr_text, keys_json} with normalized coords.
    """
    if not blocks or img_w <= 0 or img_h <= 0:
        return []

    radius = radius_factor * max(img_w, img_h)
    price_blocks = _find_price_blocks(blocks)

    # --- Phase 1: Price-anchored clusters ---
    assigned: set[int] = set()  # indices of blocks assigned to a price region
    price_clusters: list[list[dict]] = []

    for pb in price_blocks:
        region: list[dict] = []
        for i, b in enumerate(blocks):
            if _distance(pb, b) <= radius:
                region.append(b)
                assigned.add(i)
        if region:
            price_clusters.append(region)

    # Merge overlapping price clusters (a block can be near multiple prices)
    price_clusters = _merge_overlapping_clusters(price_clusters)

    # --- Phase 2: DBSCAN fallback for unassigned blocks ---
    remaining = [b for i, b in enumerate(blocks) if i not in assigned]
    dbscan_clusters: list[list[dict]] = []

    if remaining:
        dbscan_clusters = _adaptive_dbscan(
            remaining, img_w, img_h,
            eps_factor=eps_factor,
            min_samples=min_samples,
            max_clusters=max_clusters,
            max_retries=max_retries,
        )

    # --- Phase 3: Build final cluster descriptors ---
    all_groups = price_clusters + dbscan_clusters
    return _groups_to_clusters(all_groups, img_w, img_h, pad_x, pad_y)


def _merge_overlapping_clusters(clusters: list[list[dict]]) -> list[list[dict]]:
    """Merge cluster groups that share any block (by identity)."""
    if not clusters:
        return []

    # Build block→cluster mapping using block id
    block_to_cluster: dict[int, int] = {}
    for ci, group in enumerate(clusters):
        for b in group:
            bid = id(b)
            if bid in block_to_cluster:
                # Merge: redirect all blocks from the other cluster
                other = block_to_cluster[bid]
                if other != ci:
                    for ob in clusters[other]:
                        block_to_cluster[id(ob)] = ci
                    clusters[ci].extend(clusters[other])
                    clusters[other] = []
            else:
                block_to_cluster[bid] = ci

    # Deduplicate blocks within each cluster
    merged = []
    for group in clusters:
        if not group:
            continue
        seen_ids: set[int] = set()
        deduped = []
        for b in group:
            bid = id(b)
            if bid not in seen_ids:
                seen_ids.add(bid)
                deduped.append(b)
        merged.append(deduped)

    return merged


def _adaptive_dbscan(
    blocks: list[dict],
    img_w: int,
    img_h: int,
    eps_factor: float = 0.06,
    min_samples: int = 3,
    max_clusters: int = 30,
    max_retries: int = 3,
) -> list[list[dict]]:
    """Run DBSCAN with adaptive eps. Retries with larger eps if too many clusters."""
    if not blocks:
        return []

    centers = np.array([_block_center(b) for b in blocks])
    eps = eps_factor * img_w

    for attempt in range(max_retries + 1):
        db = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
        labels = db.fit_predict(centers)

        cluster_map: dict[int, list[dict]] = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue
            cluster_map.setdefault(label, []).append(blocks[idx])

        n_clusters = len(cluster_map)
        if n_clusters <= max_clusters or attempt == max_retries:
            break

        # Too many clusters — increase eps by 40%
        eps *= 1.4

    return list(cluster_map.values())


# ---------------------------------------------------------------------------
# 4) Legacy word-level clustering (backward compat for recluster with old cache)
# ---------------------------------------------------------------------------

def cluster_words(
    words: list[dict],
    img_w: int,
    img_h: int,
    eps: float = 80.0,
    min_samples: int = 2,
    pad_x: float = 20.0,
    pad_y: float = 20.0,
) -> list[dict]:
    """Cluster OCR items spatially and return cluster descriptors.

    Works with both old word-level data and new block-level data.

    Args:
        words: [{text, x0, y0, x1, y1, ...}, ...] in pixel coords.
        img_w, img_h: Original image dimensions in pixels.
        eps: DBSCAN epsilon (pixel distance).
        min_samples: DBSCAN min_samples.
        pad_x, pad_y: Padding around cluster bbox (pixels).

    Returns:
        list of {x0, y0, x1, y1, ocr_text, keys_json} with normalized coords.
    """
    if not words or img_w <= 0 or img_h <= 0:
        return []

    # Detect if this is new block-level data
    is_block_level = words and "level" in words[0]

    if is_block_level:
        # Use the new pipeline: filter → price anchor → DBSCAN
        filtered = filter_noise_candidates(words, img_w, img_h)
        return build_product_clusters_price_anchor(
            filtered, img_w, img_h,
            eps_factor=eps / img_w if img_w > 0 else 0.06,
            min_samples=max(2, min_samples),
            pad_x=pad_x,
            pad_y=pad_y,
        )

    # Legacy word-level path
    centers = np.array([
        [(w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2]
        for w in words
    ])

    db = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
    labels = db.fit_predict(centers)

    clusters_map: dict[int, list[dict]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        clusters_map.setdefault(label, []).append(words[idx])

    groups = list(clusters_map.values())
    return _groups_to_clusters(groups, img_w, img_h, pad_x, pad_y)


# ---------------------------------------------------------------------------
# Helpers: convert groups of blocks → cluster descriptors
# ---------------------------------------------------------------------------

def _groups_to_clusters(
    groups: list[list[dict]],
    img_w: int,
    img_h: int,
    pad_x: float = 20.0,
    pad_y: float = 20.0,
) -> list[dict]:
    """Convert groups of block dicts into final cluster descriptors."""
    clusters = []

    for group in groups:
        if not group:
            continue

        # Bounding box = union of all blocks in cluster
        all_x0 = min(b["x0"] for b in group)
        all_y0 = min(b["y0"] for b in group)
        all_x1 = max(b["x1"] for b in group)
        all_y1 = max(b["y1"] for b in group)

        # Add padding and clamp
        all_x0 = max(0, all_x0 - pad_x)
        all_y0 = max(0, all_y0 - pad_y)
        all_x1 = min(img_w, all_x1 + pad_x)
        all_y1 = min(img_h, all_y1 + pad_y)

        # Normalize to 0..1
        nx0 = round(all_x0 / img_w, 6)
        ny0 = round(all_y0 / img_h, 6)
        nx1 = round(all_x1 / img_w, 6)
        ny1 = round(all_y1 / img_h, 6)

        # Sort blocks top-to-bottom, left-to-right for readable text
        group_sorted = sorted(group, key=lambda b: (b["y0"], b["x0"]))
        ocr_text = " ".join(b["text"] for b in group_sorted)

        keys = _extract_keys(ocr_text)

        clusters.append({
            "x0": nx0,
            "y0": ny0,
            "x1": nx1,
            "y1": ny1,
            "ocr_text": ocr_text,
            "keys_json": keys,
        })

    # Post-filter: drop clusters with no product signal and low text
    return [c for c in clusters if _should_keep_cluster(c)]


def _should_keep_cluster(cluster: dict) -> bool:
    """Decide if a cluster should be kept or marked as noise.

    Keep if it has any product signal (price, model, brand, code)
    OR if text is long enough to be meaningful.
    """
    keys = cluster.get("keys_json", {})
    if _has_product_signal(keys):
        return True

    # Keep if text has enough substance (e.g., a product description)
    text = cluster.get("ocr_text", "")
    word_count = len(text.split())
    return word_count >= 4
