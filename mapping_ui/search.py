"""Client-side product search — no OCR, pure text matching.

Products are loaded once from the backend and cached in session_state.
Search runs entirely in Python (no API call per keystroke).
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


def search_products(
    query: str,
    products: list[dict],
    limit: int = 20,
) -> list[dict]:
    """Fast client-side search over product list.

    products: [{urun_kod, urun_ad}, ...]
    Returns [{urun_kod, urun_ad, score}, ...] sorted by score desc.
    """
    if not query or not products:
        return []

    q = query.strip()
    q_norm = _norm(q)
    q_is_digit = q.isdigit()

    scored = []
    for p in products:
        kod = p.get("urun_kod") or ""
        ad = p.get("urun_ad") or ""
        score = 0.0

        # Code mode: digit query → startswith/contains on urun_kod
        if q_is_digit:
            if kod.startswith(q):
                score += 200
            elif q in kod:
                score += 100
        else:
            # Name mode: normalize and match
            p_norm = _norm(f"{kod} {ad}")
            # Exact substring
            if q_norm in p_norm:
                score += 150
            # Token match
            for token in q_norm.split():
                if token in p_norm:
                    score += 30
            # Fuzzy (if available)
            if fuzz and ad:
                ratio = fuzz.token_set_ratio(q_norm, p_norm)
                score += ratio * 0.3

        if score > 0:
            scored.append({**p, "score": round(score, 1)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
