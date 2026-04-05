"""Client-side product search — no OCR, pure text matching.

Products are loaded once from the backend and cached in session_state.
Search runs entirely in Python (no API call per keystroke).

Performance: products are pre-indexed on first call so _norm() runs once
per product per week load, not once per product per search query.
"""

from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

_TR_MAP = str.maketrans("İŞĞÖÜÇıişğöüç", "ISGOUCiisgouc")


def _norm(s: str) -> str:
    s = s.upper().translate(_TR_MAP)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_search_index(products: list[dict]) -> list[dict]:
    """Pre-compute normalized text and tokens for each product.

    Call once when products are loaded (week load / resume).
    Returns a new list with _norm_text and _norm_tokens fields added.
    """
    indexed = []
    for p in products:
        kod = p.get("urun_kod") or ""
        ad = p.get("urun_ad") or ""
        norm_text = _norm(f"{kod} {ad}")
        indexed.append({
            **p,
            "_norm_text": norm_text,
            "_norm_tokens": set(norm_text.split()),
            "_kod": kod,
        })
    return indexed


def search_products(
    query: str,
    products: list[dict],
    limit: int = 20,
) -> list[dict]:
    """Fast client-side search over product list.

    products: [{urun_kod, urun_ad, _norm_text?, _norm_tokens?}, ...]
    If products are pre-indexed (have _norm_text), skips per-product normalization.
    Returns [{urun_kod, urun_ad, score}, ...] sorted by score desc.
    """
    if not query or not products:
        return []

    q = query.strip()
    q_norm = _norm(q)
    q_is_digit = q.isdigit()
    q_tokens = q_norm.split() if not q_is_digit else []

    scored = []
    for p in products:
        kod = p.get("_kod") or p.get("urun_kod") or ""
        score = 0.0

        if q_is_digit:
            if kod.startswith(q):
                score += 200
            elif q in kod:
                score += 100
        else:
            # Use pre-indexed normalized text if available
            p_norm = p.get("_norm_text")
            if p_norm is None:
                ad = p.get("urun_ad") or ""
                p_norm = _norm(f"{kod} {ad}")

            if q_norm in p_norm:
                score += 150

            # Token match using pre-indexed set when available
            p_tokens = p.get("_norm_tokens")
            if p_tokens is not None:
                for token in q_tokens:
                    if token in p_tokens:
                        score += 30
                    elif any(token in pt for pt in p_tokens):
                        score += 15
            else:
                for token in q_tokens:
                    if token in p_norm:
                        score += 30

            if fuzz and score > 0:
                ratio = fuzz.token_set_ratio(q_norm, p_norm)
                score += ratio * 0.3

        if score > 0:
            scored.append({**p, "score": round(score, 1)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
